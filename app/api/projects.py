# -*- coding: utf-8 -*-
import os
import shutil
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.database import get_db
from app.api.auth import get_current_user
from app.models.schemas import Project, Chat, Team

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _sanitize_text(text: str) -> str:
    """清洗输入：去除 HTML 标签，防止 XSS"""
    if not text:
        return text
    # 去除 HTML 标签
    cleaned = re.sub(r'<[^>]+>', '', text)
    return cleaned


class CreateProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


def _check_project_limit(team_id: int, db: Session):
    """检查免费版项目数量限制"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if team and team.plan == "trial":
        count = db.query(Project).filter(Project.team_id == team_id).count()
        if count >= 3:
            raise HTTPException(status_code=403, detail="免费版最多创建 3 个项目，请升级套餐")


@router.get("")
def list_projects(user=Depends(get_current_user), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.team_id == user.team_id).order_by(Project.created_at.desc()).all()
    return {"projects": [{"id": p.id, "name": p.name, "status": p.status, "stage": p.stage, "created_at": p.created_at} for p in projects]}


@router.post("")
def create_project_route(body: CreateProjectBody, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _check_project_limit(user.team_id, db)
    name = _sanitize_text(body.name)
    description = _sanitize_text(body.description)
    p = Project(team_id=user.team_id, user_id=user.id, name=name, description=description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"project": {"id": p.id, "name": p.name, "status": p.status, "created_at": p.created_at}}


@router.get("/{project_id}")
def get_project_route(project_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"error": "项目不存在"}
    chats = db.query(Chat).filter(Chat.project_id == project_id).order_by(Chat.created_at).all()
    return {"project": {"id": p.id, "name": p.name, "status": p.status, "stage": p.stage, "prd": p.prd, "requirement": p.requirement}, "chats": [{"role": c.role, "content": c.content} for c in chats]}


@router.delete("/{project_id}")
def delete_project_route(project_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"error": "项目不存在"}
    db.query(Chat).filter(Chat.project_id == project_id).delete()
    db.delete(p)
    db.commit()

    from app.config import settings
    project_path = os.path.join(settings.projects_dir, project_id)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    return {"success": True}


@router.get("/{project_id}/files")
def list_files_route(project_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"files": []}
    from app.config import settings
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
def read_file_route(project_id: str, path: str = "", user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if not p:
        return {"error": "项目不存在"}
    from app.config import settings
    from core.deployer import read_file
    content = read_file(project_id, path)
    return {"path": path, "content": content}


@router.post("/{project_id}/stop")
def stop_project_route(project_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.team_id == user.team_id).first()
    if p:
        p.status = "stopped"
        p.stage = "已停止"
        db.commit()
    return {"success": True}
