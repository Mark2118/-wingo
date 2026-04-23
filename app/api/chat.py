# -*- coding: utf-8 -*-
import asyncio
import json
import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, decode_token
from app.models.schemas import Project, Chat, User
from core.pipeline import run_pipeline

router = APIRouter(prefix="/api", tags=["chat"])

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"


class ChatBody(BaseModel):
    text: str
    project_id: str = ""


def _get_user_from_token(token: str, db: Session):
    try:
        user_id = decode_token(token)
        return db.query(User).filter(User.id == user_id, User.status == "active").first()
    except Exception:
        return None


@router.post("/chat")
async def chat_message(body: ChatBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pid = body.project_id
    if not pid:
        # 免费版项目数量限制
        from app.models.schemas import Team
        team = db.query(Team).filter(Team.id == user.team_id).first()
        if team and team.plan == "trial":
            project_count = db.query(Project).filter(Project.team_id == user.team_id).count()
            if project_count >= 3:
                return {"error": "免费版最多创建 3 个项目，请升级套餐"}
        p = Project(team_id=user.team_id, user_id=user.id, name=body.text[:30], description=body.text)
        db.add(p)
        db.commit()
        db.refresh(p)
        pid = p.id

    chat = Chat(project_id=pid, role="user", content=body.text)
    db.add(chat)
    db.commit()
    return {"project_id": pid, "text": body.text}


@router.get("/stream")
async def stream_prd(
    project_id: str,
    requirement: str,
    token: str = Query(""),
    db: Session = Depends(get_db)
):
    user = _get_user_from_token(token, db)
    if not user:
        return {"error": "Unauthorized"}

    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"error": "项目不存在"}

    async def event_generator():
        prd_text = ""
        try:
            prompt = (
                "你是一位资深产品经理。请根据以下需求生成结构化的PRD文档。"
                "包含：背景、目标、用户故事、功能需求、非功能需求、验收标准。\n\n"
                f"需求：{requirement}"
            )
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                prd_text += chunk
                                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                            if data.get("done"):
                                break
                        except:
                            pass

            # Save PRD to project
            from app.database import SessionLocal
            db2 = SessionLocal()
            try:
                p2 = db2.query(Project).filter(Project.id == project_id).first()
                if p2:
                    p2.prd = prd_text
                    p2.status = "prd_ready"
                    db2.commit()
            finally:
                db2.close()

            chat = Chat(project_id=project_id, role="assistant", content=f"📋 PRD已生成\n\n{prd_text[:500]}...")
            db.add(chat)
            db.commit()

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Auto launch pipeline
            asyncio.create_task(_auto_pipeline(project_id, requirement))

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _auto_pipeline(project_id: str, requirement: str):
    from app.main import app

    _ws_connections = app.state.ws_connections
    _running_tasks = app.state.running_tasks

    async def on_log(stage: str, message: str):
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            p = db.query(Project).filter(Project.id == project_id).first()
            if p:
                p.stage = stage
                p.status = "running" if stage != "已完成" else "deployed"
                db.commit()
        finally:
            db.close()

        conns = _ws_connections.get(project_id, set())
        dead = set()
        for ws in conns:
            try:
                await ws.send_json({"stage": stage, "message": message})
            except:
                dead.add(ws)
        for ws in dead:
            conns.discard(ws)

    task = asyncio.create_task(run_pipeline(project_id, requirement, on_log))
    _running_tasks[project_id] = task
    try:
        await task
    except asyncio.CancelledError:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            p = db.query(Project).filter(Project.id == project_id).first()
            if p:
                p.status = "stopped"
                p.stage = "已停止"
                db.commit()
        finally:
            db.close()
    finally:
        _running_tasks.pop(project_id, None)
