# -*- coding: utf-8 -*-
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.db import get_project, update_project

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{project_id}")
async def ws_pipeline(websocket: WebSocket, project_id: str):
    await websocket.accept()

    _ws_connections = websocket.app.state.ws_connections
    _running_tasks = websocket.app.state.running_tasks

    if project_id not in _ws_connections:
        _ws_connections[project_id] = set()
    _ws_connections[project_id].add(websocket)

    p = get_project(project_id)
    if p:
        await websocket.send_json(
            {"stage": p.get("stage", "等待中"), "message": "已连接"}
        )

    try:
        while True:
            data = await websocket.receive_text()
            if data.strip() == "STOP":
                update_project(project_id, status="stopped", stage="已停止")
                task = _running_tasks.pop(project_id, None)
                if task and not task.done():
                    task.cancel()
                await websocket.send_json({"stage": "已停止", "message": "已停止"})
    except WebSocketDisconnect:
        pass
    finally:
        if project_id in _ws_connections:
            _ws_connections[project_id].discard(websocket)
