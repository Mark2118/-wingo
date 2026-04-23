# -*- coding: utf-8 -*-
import os
import subprocess
from typing import Tuple
from core.config import DANGEROUS_COMMANDS, PROJECTS_DIR


class DeployError(Exception):
    pass


def check_safe(cmd: str) -> Tuple[bool, str]:
    for d in DANGEROUS_COMMANDS:
        if d.lower() in cmd.lower():
            return False, f"危险命令被拦截: {d}"
    return True, "OK"


def run_command(cmd: str, cwd: str = None, timeout: int = 120) -> dict:
    safe_ok, safe_msg = check_safe(cmd)
    if not safe_ok:
        return {"success": False, "stdout": "", "stderr": safe_msg, "exit_code": -1}

    project_cwd = cwd or PROJECTS_DIR
    os.makedirs(project_cwd, exist_ok=True)

    # 确保使用 taizi venv 的 Python
    env = os.environ.copy()
    venv_bin = os.path.join(os.path.dirname(PROJECTS_DIR), ".venv", "bin")
    env["PATH"] = venv_bin + ":" + env.get("PATH", "")

    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=project_cwd, env=env,
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "命令执行超时", "exit_code": -1}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "exit_code": -1}


def write_file(project_id: str, filename: str, content: str) -> str:
    """写入项目文件，返回绝对路径"""
    project_path = os.path.normpath(os.path.join(PROJECTS_DIR, project_id))
    filepath = os.path.normpath(os.path.join(project_path, filename))
    if not filepath.startswith(project_path):
        raise ValueError("非法文件路径")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def read_file(project_id: str, filename: str) -> str:
    project_path = os.path.join(PROJECTS_DIR, project_id)
    filepath = os.path.normpath(os.path.join(project_path, filename))
    if not filepath.startswith(os.path.normpath(project_path)):
        return ""
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def list_files(project_id: str) -> list:
    project_path = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        return []
    files = []
    for root, _, names in os.walk(project_path):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, project_path)
            files.append({"path": rel, "size": os.path.getsize(full)})
    return files
