# -*- coding: utf-8 -*-
import sqlite3
import json
import uuid
from datetime import datetime
from core.config import PROJECT_ROOT

DB_PATH = f"{PROJECT_ROOT}/wingo_ai.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'created',
            stage TEXT DEFAULT '需求分析',
            files TEXT DEFAULT '[]',
            project_type TEXT DEFAULT 'Python',
            prd TEXT,
            test_result TEXT,
            deploy_result TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    # 迁移：旧表可能没有prd字段，自动添加
    try:
        cur.execute("ALTER TABLE projects ADD COLUMN prd TEXT")
    except sqlite3.OperationalError:
        pass  # 已存在
    # 迁移：添加 deploy_url 字段
    try:
        cur.execute("ALTER TABLE projects ADD COLUMN deploy_url TEXT")
    except sqlite3.OperationalError:
        pass
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    ''')
    # 阶段耗时统计表（用于ETA估算）
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stage_timing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT NOT NULL,
            project_type TEXT,
            elapsed_ms INTEGER NOT NULL,
            created_at TEXT
        )
    ''')
    # PRD资源库表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS prd_templates (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            usage_count INTEGER DEFAULT 0,
            is_seed INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS prd_history (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT,
            status TEXT DEFAULT 'draft',
            deploy_url TEXT,
            capability_combo TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


def create_project(name: str, description: str = "") -> dict:
    pid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO projects (id, name, description, status, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pid, name, description, "created", "需求分析", now, now)
    )
    conn.commit()
    conn.close()
    return {"id": pid, "name": name, "status": "created"}


def get_project(pid: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def list_projects() -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_project(pid: str, **kwargs) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    fields.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(pid)
    cur.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def save_chat(project_id: str, role: str, content: str):
    cid = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats (id, project_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (cid, project_id, role, content, now)
    )
    conn.commit()
    conn.close()


def get_chats(project_id: str) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chats WHERE project_id = ? ORDER BY created_at ASC", (project_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_project(pid: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chats WHERE project_id = ?", (pid,))
    cur.execute("DELETE FROM projects WHERE id = ?", (pid,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def clear_chats(project_id: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chats WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()
    return True


# ── 阶段耗时统计（ETA 估算） ──
def record_stage_timing(stage: str, elapsed_ms: int, project_type: str = ""):
    """记录某个阶段的实际耗时"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO stage_timing (stage, project_type, elapsed_ms, created_at) VALUES (?, ?, ?, ?)",
        (stage, project_type, elapsed_ms, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_stage_eta(stage: str, project_type: str = "", limit: int = 10) -> int:
    """查询某阶段的历史平均耗时（毫秒），返回0表示无数据"""
    conn = get_conn()
    cur = conn.cursor()
    # 优先匹配同类型项目，fallback到全部
    cur.execute(
        "SELECT AVG(elapsed_ms) FROM stage_timing WHERE stage = ? AND project_type = ? ORDER BY created_at DESC LIMIT ?",
        (stage, project_type, limit)
    )
    row = cur.fetchone()
    avg = row[0] if row and row[0] else None
    if avg is None:
        # fallback: 不区分项目类型
        cur.execute(
            "SELECT AVG(elapsed_ms) FROM stage_timing WHERE stage = ? ORDER BY created_at DESC LIMIT ?",
            (stage, limit)
        )
        row = cur.fetchone()
        avg = row[0] if row and row[0] else 0
    conn.close()
    return int(avg)


# ── PRD 资源库操作 ──

def save_prd_template(category: str, title: str, content: str, tags: list = None, is_seed: int = 0) -> str:
    """保存PRD模板到库"""
    tid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO prd_templates (id, category, title, content, tags, is_seed, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tid, category, title, content, json.dumps(tags or []), is_seed, now, now)
    )
    conn.commit()
    conn.close()
    return tid


def list_prd_templates(category: str = None) -> list:
    """列出PRD模板，可按行业筛选"""
    conn = get_conn()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT * FROM prd_templates WHERE category = ? ORDER BY usage_count DESC, created_at DESC", (category,))
    else:
        cur.execute("SELECT * FROM prd_templates ORDER BY usage_count DESC, created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prd_template(tid: str) -> dict:
    """获取单个PRD模板详情"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prd_templates WHERE id = ?", (tid,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def increment_template_usage(tid: str):
    """增加模板使用次数"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE prd_templates SET usage_count = usage_count + 1 WHERE id = ?", (tid,))
    conn.commit()
    conn.close()


def search_prd_templates(keyword: str) -> list:
    """搜索PRD模板"""
    conn = get_conn()
    cur = conn.cursor()
    like = f"%{keyword}%"
    cur.execute(
        "SELECT * FROM prd_templates WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? ORDER BY usage_count DESC",
        (like, like, like)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_prd_history(project_id: str, title: str, content: str, category: str = None, deploy_url: str = None, capability_combo: str = None, status: str = 'draft') -> str:
    """保存PRD历史记录"""
    hid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO prd_history (id, project_id, title, content, category, deploy_url, capability_combo, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, project_id, title, content, category, deploy_url, capability_combo, status, now)
    )
    conn.commit()
    conn.close()
    return hid


def list_prd_history(category: str = None, limit: int = 50) -> list:
    """列出PRD历史记录"""
    conn = get_conn()
    cur = conn.cursor()
    if category:
        cur.execute(
            "SELECT * FROM prd_history WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit)
        )
    else:
        cur.execute("SELECT * FROM prd_history ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prd_history(hid: str) -> dict:
    """获取单个PRD历史记录"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prd_history WHERE id = ?", (hid,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
