# -*- coding: utf-8 -*-
"""适配层：让老系统的 core.db 接口在新系统（SQLAlchemy/PostgreSQL）上工作"""
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.schemas import Project, Chat, Order, Subscription, Team, User
from datetime import datetime


def get_conn():
    """兼容旧接口，返回一个可执行的会话"""
    return SessionLocal()


def _row_to_dict(project: Project) -> dict:
    if not project:
        return None
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "stage": project.stage or "",
        "files": "[]",
        "project_type": "Python",
        "prd": project.prd or "",
        "test_result": "",
        "deploy_result": "",
        "deploy_url": project.deploy_url or "",
        "created_at": project.created_at.isoformat() if project.created_at else "",
        "updated_at": project.updated_at.isoformat() if project.updated_at else "",
    }


# ── 项目操作（映射到新系统 Project 表）──

def get_project(pid: str) -> dict:
    db: Session = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        return _row_to_dict(p)
    finally:
        db.close()


def update_project(pid: str, **kwargs) -> bool:
    db: Session = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        if not p:
            return False
        for k, v in kwargs.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.updated_at = datetime.now()
        db.commit()
        return True
    finally:
        db.close()


def create_project(name: str, description: str = "") -> dict:
    import uuid
    db: Session = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        p = Project(id=pid, name=name, description=description, status="created", stage="需求分析")
        db.add(p)
        db.commit()
        db.refresh(p)
        return _row_to_dict(p)
    finally:
        db.close()


def list_projects() -> list:
    db: Session = SessionLocal()
    try:
        rows = db.query(Project).order_by(Project.created_at.desc()).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


def delete_project(pid: str) -> bool:
    db: Session = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        if not p:
            return False
        db.query(Chat).filter(Chat.project_id == pid).delete()
        db.delete(p)
        db.commit()
        return True
    finally:
        db.close()


# ── 聊天记录（映射到新系统 Chat 表）──

def save_chat(project_id: str, role: str, content: str):
    db: Session = SessionLocal()
    try:
        c = Chat(project_id=project_id, role=role, content=content)
        db.add(c)
        db.commit()
    finally:
        db.close()


def get_chats(project_id: str) -> list:
    db: Session = SessionLocal()
    try:
        rows = db.query(Chat).filter(Chat.project_id == project_id).order_by(Chat.created_at.asc()).all()
        return [{"id": str(r.id), "project_id": r.project_id, "role": r.role, "content": r.content, "created_at": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    finally:
        db.close()


# ── 阶段耗时统计（映射到新系统，暂用内存/简单实现）──
# 新系统 schema 里没有 stage_timing 表，先用 projects 表的 stage 字段兼容

def record_stage_timing(stage: str, elapsed_ms: int, project_type: str = ""):
    """兼容接口：新系统暂无独立 stage_timing 表，暂空实现"""
    pass


def get_stage_eta(stage: str, project_type: str = "", limit: int = 10) -> int:
    """兼容接口：返回 0 表示无历史数据"""
    return 0


# ── PRD 历史（兼容接口，暂空实现）──
# 新系统 schema 里没有 prd_history / prd_templates 表

def save_prd_history(project_id: str, title: str, content: str, category: str = None, deploy_url: str = None, capability_combo: str = None, status: str = 'draft') -> str:
    """兼容接口：把 PRD 保存到项目表的 prd 字段"""
    db: Session = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.prd = content
            db.commit()
        return project_id
    finally:
        db.close()


def list_prd_history(category: str = None, limit: int = 50) -> list:
    return []


def get_prd_history(hid: str) -> dict:
    return None


def save_prd_template(category: str, title: str, content: str, tags: list = None, is_seed: int = 0) -> str:
    return ""


def list_prd_templates(category: str = None) -> list:
    return []


def get_prd_template(tid: str) -> dict:
    return None


def increment_template_usage(tid: str):
    pass


def search_prd_templates(keyword: str) -> list:
    return []


# ── 兼容旧 init_db ──

def init_db():
    """兼容接口：新系统的数据库由 app.database.init_database() 初始化"""
    pass
