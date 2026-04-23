# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse
from app.config import settings
from core.db import get_project

router = APIRouter(tags=["preview"])


@router.post("/api/projects/{project_id}/preview")
def api_start_preview(project_id: str):
    p = get_project(project_id)
    if not p:
        return {"error": "项目不存在"}
    return {"url": f"/preview/{project_id}/"}


@router.get("/preview/{project_id}")
@router.get("/preview/{project_id}/{path:path}")
def preview_project(project_id: str, path: str = ""):
    project_path = os.path.join(settings.projects_dir, project_id)
    if not os.path.exists(project_path):
        return HTMLResponse("<h1>项目不存在</h1>", status_code=404)

    if path == "" or path.endswith("/"):
        target = os.path.join(project_path, "index.html")
        if not os.path.exists(target):
            for f in os.listdir(project_path):
                if f.endswith(".html"):
                    target = os.path.join(project_path, f)
                    break
    else:
        target = os.path.join(project_path, path)

    target = os.path.normpath(target)
    if not target.startswith(os.path.normpath(project_path)):
        return HTMLResponse("<h1>非法路径</h1>", status_code=403)

    if not os.path.exists(target) or not os.path.isfile(target):
        return HTMLResponse("<h1>文件不存在</h1>", status_code=404)

    if target.endswith(".html"):
        with open(target, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    return StreamingResponse(open(target, "rb"))
