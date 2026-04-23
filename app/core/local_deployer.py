# -*- coding: utf-8 -*-
"""本地部署器 — Mac Docker 本地部署，零 SSH，零香港"""

import os
import subprocess
import hashlib
import socket

BASE_PORT = 8000
DEPLOY_DIR = os.path.expanduser("~/taizi/deployed-apps")


def _check_port_available(port: int) -> bool:
    """检测本地端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            return result != 0
    except Exception:
        return False


def allocate_port(project_id: str) -> int:
    """为项目分配一个本地可用端口"""
    h = int(hashlib.md5(project_id.encode()).hexdigest(), 16)
    port = BASE_PORT + (h % 1000)
    for _ in range(200):
        if _check_port_available(port):
            return port
        port += 1
    raise RuntimeError(f"找不到可用端口（已尝试 {BASE_PORT}-{port}）")


def sync_project(project_id: str, local_path: str) -> dict:
    """同步项目到本地部署目录"""
    import shutil
    dst = os.path.join(DEPLOY_DIR, project_id)
    os.makedirs(dst, exist_ok=True)
    # 清空旧内容
    for item in os.listdir(dst):
        item_path = os.path.join(dst, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    # 复制新内容
    for item in os.listdir(local_path):
        s = os.path.join(local_path, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    return {"success": True, "mode": "local", "remote_dir": dst}


def build_and_run(project_id: str, port: int) -> dict:
    """Docker 构建并运行"""
    remote_dir = os.path.join(DEPLOY_DIR, project_id)
    container_name = f"wingo-app-{project_id}"

    # 先停止并删除旧容器
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True, text=True, timeout=30
    )

    build_cmd = [
        "docker", "build", "-t", container_name, remote_dir
    ]
    r = subprocess.run(build_cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"Docker 构建失败: {r.stderr[:300]}",
            "stdout": r.stdout,
            "stderr": r.stderr,
            "url": f"http://127.0.0.1:{port}/",
        }

    run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:80",
        "--restart", "unless-stopped",
        container_name,
    ]
    r2 = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
    if r2.returncode != 0:
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"Docker 运行失败: {r2.stderr[:300]}",
            "stdout": r2.stdout,
            "stderr": r2.stderr,
            "url": f"http://127.0.0.1:{port}/",
        }

    # 健康检查
    import time
    time.sleep(2)
    health_ok = False
    health_output = ""
    for i in range(5):
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="HEAD")
            req.add_header("User-Agent", "WinGo-HealthCheck")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 301, 302):
                    health_ok = True
                    break
        except Exception as e:
            health_output += f" 尝试{i+1}: {str(e)[:50]}\n"
        time.sleep(2)

    if not health_ok:
        # 获取容器日志
        lr = subprocess.run(
            ["docker", "logs", "--tail", "20", container_name],
            capture_output=True, text=True, timeout=10
        )
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"容器启动但健康检查失败\n{health_output}日志:\n{lr.stdout or ''}{lr.stderr or ''}",
            "stdout": r.stdout,
            "stderr": r.stderr,
            "url": f"http://127.0.0.1:{port}/",
        }

    url = f"http://127.0.0.1:{port}/"

    # Caddy 反向代理 + 子域名
    domain = f"{project_id}.wingo.icu"
    try:
        from core.caddy_proxy import add_route
        caddy_ok = add_route(domain, port)
        public_url = f"http://{domain}/"
        note = f"Docker 构建并通过健康检查。Caddy: {'OK' if caddy_ok else 'FAIL'}。公网: {public_url}"
    except Exception as e:
        public_url = url
        note = f"Docker 构建并通过健康检查。Caddy 配置异常: {e}"

    return {
        "success": True,
        "port": port,
        "container": container_name,
        "note": note,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "url": url,
        "domain_url": public_url,
    }


def get_deploy_info(project_id: str) -> dict:
    """获取部署信息"""
    port = allocate_port(project_id)
    url = f"http://127.0.0.1:{port}/"
    return {
        "url": url,
        "port": port,
        "is_local": True,
    }
