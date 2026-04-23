# -*- coding: utf-8 -*-
import os
import subprocess
import signal
import socket
from core.config import PROJECTS_DIR

_preview_processes = {}
_next_port = 39000


def _get_next_port():
    global _next_port
    while True:
        port = _next_port
        _next_port += 1
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port


def start_preview(project_id: str, project_type: str) -> dict:
    project_path = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        return {"error": "项目不存在"}

    stop_preview(project_id)

    if project_type == "HTML":
        index_path = os.path.join(project_path, "index.html")
        if not os.path.exists(index_path):
            for f in os.listdir(project_path):
                if f.endswith(".html"):
                    index_path = os.path.join(project_path, f)
                    break
        if not os.path.exists(index_path):
            return {"error": "没有找到HTML入口文件"}
        return {"type": "html", "url": f"/preview/{project_id}"}
    else:
        port = _get_next_port()
        main_py = os.path.join(project_path, "main.py")
        if not os.path.exists(main_py):
            return {"error": "没有找到 main.py"}

        proc = subprocess.Popen(
            ["python3", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=project_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _preview_processes[project_id] = {"pid": proc.pid, "port": port, "type": "python"}
        return {"type": "python", "url": f"http://127.0.0.1:{port}"}


def stop_preview(project_id: str):
    if project_id in _preview_processes:
        info = _preview_processes[project_id]
        try:
            os.kill(info["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        del _preview_processes[project_id]


def get_preview_status(project_id: str) -> dict:
    if project_id not in _preview_processes:
        return {"running": False}
    info = _preview_processes[project_id]
    try:
        os.kill(info["pid"], 0)
        return {"running": True, "url": f"http://127.0.0.1:{info['port']}", "port": info["port"]}
    except ProcessLookupError:
        del _preview_processes[project_id]
        return {"running": False}
