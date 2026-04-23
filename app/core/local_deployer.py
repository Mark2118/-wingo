# -*- coding: utf-8 -*-
"""轻量级本地部署器 — 子进程直连，零 Docker，零镜像"""

import os
import sys
import json
import socket
import signal
import hashlib
import subprocess
import shutil

BASE_PORT = 8000
DEPLOY_DIR = os.path.expanduser("~/taizi/deployed-apps")
PROC_DIR = os.path.expanduser("~/.wingo/processes")
os.makedirs(PROC_DIR, exist_ok=True)


def _check_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) != 0
    except Exception:
        return False


def allocate_port(project_id: str) -> int:
    h = int(hashlib.md5(project_id.encode()).hexdigest(), 16)
    port = BASE_PORT + (h % 1000)
    for _ in range(200):
        if _check_port_available(port):
            return port
        port += 1
    raise RuntimeError(f"找不到可用端口（已尝试 {BASE_PORT}-{port}）")


def sync_project(project_id: str, local_path: str) -> dict:
    """同步项目到本地部署目录"""
    dst = os.path.join(DEPLOY_DIR, project_id)
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(dst):
        item_path = os.path.join(dst, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    for item in os.listdir(local_path):
        s = os.path.join(local_path, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    return {"success": True, "mode": "local", "remote_dir": dst}


def _detect_project_type(project_path: str) -> str:
    """检测项目类型"""
    if os.path.exists(os.path.join(project_path, "main.py")):
        return "Python"
    if os.path.exists(os.path.join(project_path, "index.html")):
        return "HTML"
    for f in os.listdir(project_path):
        if f.endswith(".py"):
            return "Python"
        if f.endswith(".html"):
            return "HTML"
    return "HTML"


def _save_proc(project_id: str, port: int, pid: int, cmd: list, project_type: str):
    info = {"project_id": project_id, "port": port, "pid": pid, "cmd": cmd, "type": project_type}
    with open(os.path.join(PROC_DIR, f"{project_id}.json"), "w") as f:
        json.dump(info, f)


def _load_proc(project_id: str):
    path = os.path.join(PROC_DIR, f"{project_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _kill_proc(project_id: str):
    """停止项目的运行进程"""
    info = _load_proc(project_id)
    if info and info.get("pid"):
        try:
            os.kill(info["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass
    # 清理端口占用（强制）
    info2 = _load_proc(project_id)
    if info2 and info2.get("port"):
        port = info2["port"]
        try:
            r = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5
            )
            if r.stdout.strip():
                for pid_str in r.stdout.strip().split("\n"):
                    try:
                        os.kill(int(pid_str.strip()), signal.SIGKILL)
                    except Exception:
                        pass
        except Exception:
            pass
    proc_file = os.path.join(PROC_DIR, f"{project_id}.json")
    if os.path.exists(proc_file):
        os.remove(proc_file)


def start_and_run(project_id: str, port: int) -> dict:
    """直接子进程启动项目，零 Docker"""
    project_path = os.path.join(DEPLOY_DIR, project_id)
    if not os.path.exists(project_path):
        return {"success": False, "port": port, "note": f"项目目录不存在: {project_path}"}

    project_type = _detect_project_type(project_path)

    # 先杀掉旧的
    _kill_proc(project_id)

    import time
    for _ in range(10):
        if _check_port_available(port):
            break
        time.sleep(0.2)

    # 准备启动命令
    if project_type == "Python":
        main_file = os.path.join(project_path, "main.py")
        if not os.path.exists(main_file):
            py_files = [f for f in os.listdir(project_path) if f.endswith(".py")]
            if py_files:
                main_file = os.path.join(project_path, py_files[0])
        # 优先 uvicorn（如果是 FastAPI/Flask）
        if os.path.exists(os.path.join(project_path, "requirements.txt")):
            with open(os.path.join(project_path, "requirements.txt")) as f:
                reqs = f.read()
            if "fastapi" in reqs.lower():
                cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
            elif "flask" in reqs.lower():
                cmd = [sys.executable, "-m", "flask", "--app", os.path.basename(main_file), "run", "--host=0.0.0.0", f"--port={port}"]
            else:
                cmd = [sys.executable, main_file]
        else:
            with open(main_file, "r", encoding="utf-8") as f:
                code = f.read()
            if "fastapi" in code.lower() or "from fastapi" in code.lower():
                cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
            elif "flask" in code.lower():
                cmd = [sys.executable, "-m", "flask", "--app", os.path.basename(main_file), "run", "--host=0.0.0.0", f"--port={port}"]
            else:
                cmd = [sys.executable, main_file]
    else:
        # HTML 项目：用 http.server
        cmd = [sys.executable, "-m", "http.server", str(port)]

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=project_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        return {"success": False, "port": port, "note": f"启动失败: {e}"}

    pid = proc.pid
    _save_proc(project_id, port, pid, cmd, project_type)

    # 健康检查
    time.sleep(1)
    health_ok = False
    health_output = ""
    for i in range(8):
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="HEAD")
            req.add_header("User-Agent", "WinGo-HealthCheck")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 301, 302, 404):
                    health_ok = True
                    break
        except Exception as e:
            health_output += f" 尝试{i+1}: {str(e)[:50]}\n"
        # 检查进程是否还活着
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            return {
                "success": False,
                "port": port,
                "pid": pid,
                "note": f"进程已退出（code={proc.returncode}）\nSTDOUT:\n{stdout.decode()[-500:]}\nSTDERR:\n{stderr.decode()[-500:]}",
                "url": f"http://127.0.0.1:{port}/",
            }
        time.sleep(1)

    if not health_ok:
        try:
            proc.terminate()
        except Exception:
            pass
        return {
            "success": False,
            "port": port,
            "pid": pid,
            "note": f"启动但健康检查失败\n{health_output}",
            "url": f"http://127.0.0.1:{port}/",
        }

    url = f"http://127.0.0.1:{port}/"

    # Caddy 反向代理
    domain = f"{project_id}.wingo.icu"
    try:
        from core.caddy_proxy import add_route
        caddy_ok = add_route(domain, port)
        public_url = f"http://{domain}/"
        note = f"子进程启动成功 (PID={pid})。Caddy: {'OK' if caddy_ok else 'FAIL'}。公网: {public_url}"
    except Exception as e:
        public_url = url
        note = f"子进程启动成功 (PID={pid})。Caddy 配置异常: {e}"

    return {
        "success": True,
        "port": port,
        "pid": pid,
        "note": note,
        "url": url,
        "domain_url": public_url,
    }


def stop_project(project_id: str) -> dict:
    """停止项目"""
    _kill_proc(project_id)
    return {"success": True, "note": f"项目 {project_id} 已停止"}


def get_deploy_info(project_id: str) -> dict:
    """获取部署信息"""
    port = allocate_port(project_id)
    url = f"http://127.0.0.1:{port}/"
    info = _load_proc(project_id)
    return {
        "url": url,
        "port": port,
        "is_local": True,
        "pid": info.get("pid") if info else None,
        "running": info is not None,
    }
