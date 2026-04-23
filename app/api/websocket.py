# -*- coding: utf-8 -*-
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.schemas import Project

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{project_id}")
async def ws_pipeline(websocket: WebSocket, project_id: str):
    await websocket.accept()

    _ws_connections = websocket.app.state.ws_connections
    _running_tasks = websocket.app.state.running_tasks

    if project_id not in _ws_connections:
        _ws_connections[project_id] = set()
    _ws_connections[project_id].add(websocket)

    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            await websocket.send_json({"stage": p.stage or "等待中", "message": "已连接"})
    finally:
        db.close()

    try:
        while True:
            data = await websocket.receive_text()
            if data.strip() == "STOP":
                db = SessionLocal()
                try:
                    p = db.query(Project).filter(Project.id == project_id).first()
                    if p:
                        p.status = "stopped"
                        p.stage = "已停止"
                        db.commit()
                finally:
                    db.close()
                task = _running_tasks.pop(project_id, None)
                if task and not task.done():
                    task.cancel()
                await websocket.send_json({"stage": "已停止", "message": "已停止"})
    except WebSocketDisconnect:
        pass
    finally:
        if project_id in _ws_connections:
            _ws_connections[project_id].discard(websocket)
