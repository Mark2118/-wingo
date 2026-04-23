# -*- coding: utf-8 -*-
"""记忆持久化模块 — 项目级 brain + 全局日志 + 对话存档 + 多源搜索

2T 本地盘，放开手脚存。AGENTS.md 只是人类可读的索引，
详细记忆全部进文件系统，随时翻、随时查、不丢。"""

import os
import json
import subprocess
import threading
import glob
import random
from datetime import datetime

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# ── 员工/节点定义 ──
SOURCES = {
    "you": {"name": "👑 版主", "role": "皇帝", "desc": "人类决策者，发指令拍板"},
    "01": {"name": "01-AI指挥官", "role": "版主", "desc": "AI调度中枢+全自动执行"},
    "02": {"name": "02-Windows工部", "role": "工部", "desc": "STEAM课程+财商课程开发"},
    "03": {"name": "03-移动指挥所", "role": "前线", "desc": "移动设备+SSH接入01操作全局"},
    "04": {"name": "04-OpenClaw营销", "role": "外交", "desc": "月之暗面云端服务，负责销售推广客户沟通"},
}

# ── WinGo BBS 精华区标识 ──
# 精华 = 大家确定的事情，category="精华" 即可
# 红线：所有讨论必须在 WinGo 架构内，不允许跑出架构


def _git_backup_async(category: str):
    """后台异步 git 备份记忆目录，不阻塞主流程。"""

    def _do():
        try:
            subprocess.run(
                ["git", "add", "memory/"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                timeout=10,
            )
            r = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0:
                return
            msg = f"memory: {category} @ {datetime.now().strftime('%H:%M')}"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=PROJECT_ROOT,
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                timeout=15,
            )
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def save_memory(
    category: str, content: str, project_id: str = None, source: str = "01", status: str = None, parent_id: str = None
) -> dict:
    """保存记忆到：1) 项目 brain 目录  2) 全局日志

    Args:
        category: 记忆类别（精华 = 已确定要执行的事项）
        content:  记忆内容
        project_id: 关联项目 ID
        source: 来源节点（01=Mac, 02=Windows, 03=移动）
        status: 任务状态（todo/in_progress/done）
        parent_id: 回复的目标帖子 ID（为空则是主贴）

    Returns:
        {"saved_to": [文件路径列表], "id": 唯一ID}
    """
    now = datetime.now().isoformat(timespec="minutes")
    entry_id = f"{now.replace(':', '').replace('-', '')}-{source}-{random.randint(1000,9999)}"
    result = {"saved_to": [], "id": entry_id}

    src_info = SOURCES.get(source, {})
    src_tag = f"[{source}-{src_info.get('name', '?')}]"
    status_tag = f" [{status}]" if status else ""
    reply_tag = f" [回复 {parent_id}]" if parent_id else ""

    # ── 1. 项目级 brain 目录 ──
    if project_id:
        brain_dir = os.path.join(MEMORY_DIR, "projects", project_id)
        _ensure_dir(brain_dir)
        brain_file = os.path.join(brain_dir, f"{category}.md")
        with open(brain_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {now} {src_tag}{status_tag}{reply_tag}\n\n{content}\n")
        result["saved_to"].append(brain_file)

    # ── 2. 全局日志（jsonl，机器可读）──
    today = datetime.now().strftime("%Y-%m-%d")
    global_dir = os.path.join(MEMORY_DIR, "global", today)
    _ensure_dir(global_dir)
    global_file = os.path.join(global_dir, "memory.jsonl")
    entry = {
        "id": entry_id,
        "time": now,
        "category": category,
        "content": content,
        "project_id": project_id,
        "source": source,
        "status": status or "",
        "parent_id": parent_id or "",
    }
    with open(global_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    result["saved_to"].append(global_file)

    # ── 3. 自动 git 备份 ──
    _git_backup_async(category)

    return result


def archive_chat(project_id: str, role: str, content: str, source: str = "01"):
    """存档单条对话到项目对话档案。"""
    if not project_id:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    chat_dir = os.path.join(MEMORY_DIR, "chats", project_id)
    _ensure_dir(chat_dir)
    chat_file = os.path.join(chat_dir, f"{today}.jsonl")
    with open(chat_file, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "time": datetime.now().isoformat(),
                    "role": role,
                    "content": content,
                    "source": source,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def get_project_brain(project_id: str, category: str = None) -> str:
    """读取项目 brain 内容。"""
    brain_dir = os.path.join(MEMORY_DIR, "projects", project_id)
    if not os.path.exists(brain_dir):
        return ""

    if category:
        fpath = os.path.join(brain_dir, f"{category}.md")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    parts = []
    for fname in sorted(os.listdir(brain_dir)):
        if fname.endswith(".md"):
            with open(os.path.join(brain_dir, fname), "r", encoding="utf-8") as f:
                parts.append(f"# {fname[:-3]}\n\n{f.read()}")
    return "\n\n".join(parts)


def search_memory(query: str = "", source: str = "", project_id: str = "", category: str = "", limit: int = 50):
    """搜索全局记忆日志。支持关键词、来源、项目、分类、板块筛选。
    返回结果按话题串分组：主贴在前，回帖紧跟。

    Returns:
        [{time, category, content, project_id, source, parent_id, replies: [...]}, ...]
    """
    all_entries = []
    query_lower = query.lower() if query else ""

    global_root = os.path.join(MEMORY_DIR, "global")
    if not os.path.exists(global_root):
        return []

    for jsonl_path in sorted(glob.glob(os.path.join(global_root, "*/memory.jsonl")), reverse=True):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if source and entry.get("source") != source:
                        continue
                    if project_id and entry.get("project_id") != project_id:
                        continue
                    if category and entry.get("category") != category:
                        continue
                    if query_lower:
                        text = f"{entry.get('category', '')} {entry.get('content', '')}".lower()
                        if query_lower not in text:
                            continue

                    all_entries.append(entry)
        except Exception:
            continue

    # 按话题串分组：parent_id 为空的是主贴，有值的是回帖
    threads = {}  # parent_id -> list of replies
    roots = []
    for e in all_entries:
        pid = e.get("parent_id", "")
        if pid:
            threads.setdefault(pid, []).append(e)
        else:
            roots.append(e)

    # 给主贴附加 replies，限制总数
    results = []
    for r in roots:
        r["replies"] = threads.get(r.get("id", ""), [])
        results.append(r)
        if len(results) >= limit:
            break
        # 主贴的回帖也计入 limit
        for reply in threads.get(r.get("id", ""), []):
            if len(results) >= limit:
                break
            results.append(reply)

    # 没有主贴的孤回帖（回复了一个不存在或被过滤掉的帖子），也显示出来
    root_ids = {rr.get("id", "") for rr in roots}
    orphaned = [e for e in all_entries if e.get("parent_id") and e.get("parent_id") not in root_ids]
    for e in orphaned:
        e["replies"] = []
        results.append(e)
        if len(results) >= limit:
            break

    return results


def list_categories():
    """返回全局日志中所有不重复的 category 列表（按出现次数降序）。"""
    cats = {}
    global_root = os.path.join(MEMORY_DIR, "global")
    if not os.path.exists(global_root):
        return []
    for jsonl_path in glob.glob(os.path.join(global_root, "*/memory.jsonl")):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cat = entry.get("category", "未分类")
                    cats[cat] = cats.get(cat, 0) + 1
        except Exception:
            continue
    return sorted(cats.items(), key=lambda x: x[1], reverse=True)


def update_memory_status(entry_id: str, new_status: str) -> bool:
    """更新全局日志中某条记录的状态。遍历所有 jsonl 文件，找到匹配 id 后更新并重写文件，同时记录变更日志到项目 brain。"""
    global_root = os.path.join(MEMORY_DIR, "global")
    if not os.path.exists(global_root):
        return False
    for jsonl_path in glob.glob(os.path.join(global_root, "*/memory.jsonl")):
        old_status = ""
        content = ""
        project_id = ""
        updated = False
        lines = []
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        lines.append(line)
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        lines.append(line)
                        continue
                    if entry.get("id") == entry_id:
                        old_status = entry.get("status", "")
                        content = entry.get("content", "")
                        project_id = entry.get("project_id", "")
                        entry["status"] = new_status
                        updated = True
                    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
            if updated:
                with open(jsonl_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                # 写变更日志到项目 brain
                if project_id:
                    brain_dir = os.path.join(MEMORY_DIR, "projects", project_id)
                    _ensure_dir(brain_dir)
                    brain_file = os.path.join(brain_dir, "看板.md")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    with open(brain_file, "a", encoding="utf-8") as f:
                        f.write(f"\n## {now} · 状态变更\n\n任务：{content}\n{old_status or '（无）'} → {new_status}\n")
                _git_backup_async("status-update")
                return True
        except Exception:
            continue
    return False


def delete_memory(entry_id: str) -> bool:
    """从全局日志中删除某条记录。"""
    global_root = os.path.join(MEMORY_DIR, "global")
    if not os.path.exists(global_root):
        return False
    for jsonl_path in glob.glob(os.path.join(global_root, "*/memory.jsonl")):
        updated = False
        lines = []
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        lines.append(line)
                        continue
                    if entry.get("id") == entry_id:
                        updated = True
                        continue
                    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
            if updated:
                with open(jsonl_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                _git_backup_async("delete")
                return True
        except Exception:
            continue
    return False


def get_sources():
    """返回所有来源节点定义。"""
    return SOURCES



