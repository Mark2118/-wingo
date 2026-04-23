# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter
from pydantic import BaseModel
from core.db import create_project, get_project, list_projects, update_project, delete_project, get_chats
from app.config import settings

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = "未命名项目"
    description: str = ""


@router.get("")
def list_projects_route():
    return {"projects": list_projects()}


@router.post("")
def create_project_route(body: ProjectCreate):
    p = create_project(body.name, body.description)
    return {"project": p}


@router.get("/{project_id}")
def get_project_route(project_id: str):
    p = get_project(project_id)
    if not p:
        return {"error": "项目不存在"}
    return p


@router.delete("/{project_id}")
def delete_project_route(project_id: str):
    import shutil
    project_path = os.path.join(settings.projects_dir, project_id)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    delete_project(project_id)
    return {"success": True}


@router.get("/{project_id}/files")
def list_files_route(project_id: str):
    project_path = os.path.join(settings.projects_dir, project_id)
    if not os.path.exists(project_path):
        return {"files": []}
    files = []
    for root, _, filenames in os.walk(project_path):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), project_path)
            files.append(rel)
    return {"files": files}


@router.get("/{project_id}/file")
def read_file_route(project_id: str, path: str = ""):
    from core.deployer import read_file
    content = read_file(project_id, path)
    return {"path": path, "content": content}


@router.get("/{project_id}/chats")
def get_chats_route(project_id: str):
    return {"chats": get_chats(project_id)}


@router.post("/{project_id}/stop")
def stop_project_route(project_id: str):
    update_project(project_id, status="stopped", stage="已停止")
    return {"success": True}
