# -*- coding: utf-8 -*-
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.db import create_project, get_project, update_project, save_chat, get_chats
from core.ai_engine import stream_chat
from core.pipeline import run_pipeline

router = APIRouter(prefix="/api", tags=["chat"])


class ChatBody(BaseModel):
    text: str
    project_id: str = ""


@router.post("/chat")
async def chat_message(body: ChatBody):
    """接收用户消息，创建/获取项目，保存聊天记录"""
    pid = body.project_id
    if not pid:
        p = create_project(body.text[:30], body.text)
        pid = p["id"]

    save_chat(pid, "user", body.text)
    return {"project_id": pid, "text": body.text}


@router.get("/stream")
async def stream_prd(project_id: str, requirement: str):
    """SSE流式生成PRD，生成完后自动启动Pipeline"""
    p = get_project(project_id)
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
                    # 保存PRD
                    update_project(project_id, prd=prd_text, status="prd_ready")
                    save_chat(project_id, "assistant", f"📋 PRD已生成\n\n{prd_text[:500]}...")
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

                    # 自动启动Pipeline（fire-and-forget）
                    asyncio.create_task(_auto_pipeline(project_id, requirement))

                elif chunk["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': chunk['content']})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _auto_pipeline(project_id: str, requirement: str):
    """自动执行Pipeline，通过WebSocket推送进度"""
    from app.main import app

    _ws_connections = app.state.ws_connections
    _running_tasks = app.state.running_tasks

    async def on_log(stage: str, message: str):
        # 推送WebSocket
        conns = _ws_connections.get(project_id, set())
        dead = set()
        for ws in conns:
            try:
                await ws.send_json({"stage": stage, "message": message})
            except:
                dead.add(ws)
        for ws in dead:
            conns.discard(ws)

        # 更新数据库状态
        update_project(project_id, stage=stage, status="running" if stage != "已完成" else "deployed")

    task = asyncio.create_task(run_pipeline(project_id, requirement, on_log))
    _running_tasks[project_id] = task
    try:
        await task
    except asyncio.CancelledError:
        update_project(project_id, status="stopped", stage="已停止")
    finally:
        _running_tasks.pop(project_id, None)
