# -*- coding: utf-8 -*-
import asyncio
import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, decode_token
from app.models.schemas import Project, Chat
from core.ai_engine import stream_chat
from core.pipeline import run_pipeline

router = APIRouter(prefix="/api", tags=["chat"])


class ChatBody(BaseModel):
    text: str
    project_id: str = ""


def _get_user_from_token(token: str, db: Session):
    try:
        user_id = decode_token(token)
        from app.models.schemas import User
        return db.query(User).filter(User.id == user_id, User.status == "active").first()
    except Exception:
        return None


@router.post("/chat")
async def chat_message(body: ChatBody, user=Depends(get_current_user), db: Session = Depends(get_db)):
    pid = body.project_id
    if not pid:
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
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # SSE does not support headers, allow token from query param
    if token:
        u = _get_user_from_token(token, db)
        if u:
            user = u
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"error": "项目不存在"}

    messages = [
        {
            "role": "system",
            "content": "你是一位资深产品经理。请根据用户需求生成结构化的PRD文档。"
                       "包含：背景、目标、用户故事、功能需求、非功能需求、验收标准。"
                       "用Markdown格式输出。",
        },
        {"role": "user", "content": f"项目ID: {project_id}\n需求: {requirement}"},
    ]

    async def event_generator():
        prd_text = ""
        try:
            async for chunk in stream_chat(messages, task_type="heavy"):
                if chunk["type"] == "chunk":
                    prd_text += chunk["content"]
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk['content']})}\n\n"
                elif chunk["type"] == "done":
                    p.prd = prd_text
                    p.status = "prd_ready"
                    db.commit()

                    chat = Chat(project_id=project_id, role="assistant", content=f"📋 PRD已生成\n\n{prd_text[:500]}...")
                    db.add(chat)
                    db.commit()

                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    asyncio.create_task(_auto_pipeline(project_id, requirement))

                elif chunk["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': chunk['content']})}\n\n"
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
