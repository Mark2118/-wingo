# -*- coding: utf-8 -*-
"""部署器 v2 — 支持本地模式（WinGo与部署同机）和SSH远程模式

本地模式：WinGo主系统直接运行在香港服务器，用本地podman命令部署
SSH模式：WinGo在Mac，通过SSH到香港服务器部署（保留兼容）
"""

import os
import subprocess
import hashlib

HK_HOST = "8.217.147.240"
HK_USER = "root"
BASE_PORT = 3000

# 检测当前是否在目标服务器上运行（本地模式）
def _is_local_mode() -> bool:
    """检测WinGo是否运行在部署目标服务器上"""
    # 方法1：检查是否有本地podman且能执行
    try:
        r = subprocess.run(["podman", "version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    # 方法2：检查hostname是否匹配
    try:
        hostname = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        if HK_HOST in hostname.stdout:
            return True
    except Exception:
        pass
    return False

_IS_LOCAL = _is_local_mode()

# SSH密钥候选
_SSH_KEY_CANDIDATES = [
    os.path.expanduser("~/.ssh/taizi_ed25519"),
    os.path.expanduser("~/.ssh/id_ed25519"),
    os.path.expanduser("~/.ssh/id_rsa"),
]

def _find_ssh_key() -> str:
    for k in _SSH_KEY_CANDIDATES:
        if os.path.isfile(k) and os.access(k, os.R_OK):
            return k
    raise FileNotFoundError("未找到可用SSH私钥")


def _exec(cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """统一执行命令：本地直接执行，远程走SSH"""
    if _IS_LOCAL:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    # SSH远程模式
    key = _find_ssh_key()
    ssh_cmd = [
        "ssh", "-i", key, "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10", f"{HK_USER}@{HK_HOST}",
        " ".join(cmd) if isinstance(cmd, list) else cmd,
    ]
    return subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)


def _check_port_available(port: int) -> bool:
    r = _exec(["ss", "-tlnp", "|", "grep", f"':{port} '", "||", "echo", "FREE"], timeout=15)
    return "FREE" in (r.stdout or "")


def allocate_port(project_id: str) -> int:
    h = int(hashlib.md5(project_id.encode()).hexdigest(), 16)
    port = BASE_PORT + (h % 1000)
    for _ in range(50):
        if _check_port_available(port):
            return port
        port += 1
    raise RuntimeError(f"找不到可用端口（已尝试 {BASE_PORT}-{port}）")


def sync_project(project_id: str, local_path: str) -> dict:
    """同步项目目录到部署目标"""
    import tarfile, io
    remote_dir = f"/opt/wingo-apps/{project_id}"
    
    if _IS_LOCAL:
        # 本地模式：直接复制
        import shutil
        dst = f"/opt/wingo-apps/{project_id}"
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(local_path):
            s = os.path.join(local_path, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        return {"success": True, "mode": "local", "remote_dir": dst}
    
    # SSH远程模式：tar+管道
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        tar.add(local_path, arcname=".")
    tar_data = tar_buffer.getvalue()
    
    key = _find_ssh_key()
    ssh = subprocess.Popen(
        ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no",
         f"{HK_USER}@{HK_HOST}", f"mkdir -p {remote_dir} && tar xzf - -C {remote_dir}"],
        stdin=subprocess.PIPE,
    )
    stdout, stderr = ssh.communicate(tar_data)
    if ssh.returncode != 0:
        return {"success": False, "mode": "ssh", "error": f"SSH同步失败: {stderr or 'unknown error'}"}
    return {"success": True, "mode": "ssh", "remote_dir": remote_dir}


def remove_nginx_config(project_id: str) -> dict:
    """删除项目的 nginx 动态配置"""
    conf_path = f"/etc/nginx/conf.d/dynamic/{project_id}.conf"
    r = _exec(["rm", "-f", conf_path], timeout=10)
    return {"success": r.returncode == 0}


def configure_nginx(project_id: str, port: int) -> dict:
    """在香港 nginx 添加/更新项目 location 反代配置"""
    conf_path = f"/etc/nginx/conf.d/dynamic/{project_id}.conf"
    location_block = f"""location /app/{project_id}/ {{
    proxy_pass http://localhost:{port}/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;
    proxy_read_timeout 60s;
}}"""
    # 写配置
    write_cmd = ["bash", "-c", f"cat > {conf_path} << 'EOF'\n{location_block}\nEOF"]
    r = _exec(write_cmd, timeout=10)
    if r.returncode != 0:
        return {"success": False, "error": f"写nginx配置失败: {r.stderr}"}
    # 测试语法
    t = _exec(["nginx", "-t"], timeout=10)
    if t.returncode != 0:
        _exec(["rm", "-f", conf_path], timeout=5)
        return {"success": False, "error": f"nginx语法错误，已回滚: {t.stderr}"}
    # 重载
    rel = _exec(["nginx", "-s", "reload"], timeout=10)
    if rel.returncode != 0:
        return {"success": False, "error": f"nginx重载失败: {rel.stderr}"}
    return {"success": True}


def build_and_run(project_id: str, port: int) -> dict:
    """构建并运行客户产品容器，并在目标服务器本地做健康检查"""
    remote_dir = f"/opt/wingo-apps/{project_id}"
    container_name = f"wingo-app-{project_id}"
    
    # 先清理旧 nginx 配置（避免端口冲突或残留）
    remove_nginx_config(project_id)
    
    build_cmd = [
        "cd", remote_dir, "&&",
        "podman", "build", "-t", container_name, ".", "2>&1", "&&",
        "podman", "run", "-d", "--name", container_name,
        "-p", f"{port}:80", "--replace", container_name, "2>&1",
    ]
    
    r = _exec(build_cmd, timeout=120)
    if r.returncode != 0:
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"构建失败: {r.stderr[:300]}",
            "stdout": r.stdout,
            "stderr": r.stderr,
            "url": f"https://homework.wingo.icu/app/{project_id}/",
        }
    
    # 容器启动后，在目标服务器本地做健康检查（绕过安全组和DNS）
    import time
    time.sleep(3)
    health_ok = False
    health_output = ""
    for i in range(5):
        hr = _exec(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://localhost:{port}/"], timeout=10)
        status = (hr.stdout or "").strip()
        if status in ("200", "301", "302"):
            health_ok = True
            break
        health_output += f" 尝试{i+1}: {status}\n"
        time.sleep(2)
    
    if not health_ok:
        # 获取容器日志帮助诊断
        lr = _exec(["podman", "logs", "--tail", "20", container_name], timeout=10)
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"容器启动但健康检查失败\n{health_output}容器日志:\n{lr.stdout or ''}{lr.stderr or ''}",
            "stdout": r.stdout,
            "stderr": r.stderr,
            "url": f"https://homework.wingo.icu/app/{project_id}/",
        }
    
    # 自动配置 nginx
    nginx_result = configure_nginx(project_id, port)
    if not nginx_result["success"]:
        return {
            "success": False,
            "port": port,
            "container": container_name,
            "note": f"容器健康但nginx配置失败: {nginx_result.get('error', '')}",
            "stdout": r.stdout,
            "stderr": r.stderr,
            "url": f"https://homework.wingo.icu/app/{project_id}/",
        }
    
    url = f"https://homework.wingo.icu/app/{project_id}/"
    return {
        "success": True,
        "port": port,
        "container": container_name,
        "note": "构建并通过健康检查，nginx已配置",
        "stdout": r.stdout,
        "stderr": r.stderr,
        "url": url,
    }


def get_deploy_info(project_id: str) -> dict:
    """获取部署信息（URL等）"""
    port = allocate_port(project_id)
    url = f"https://homework.wingo.icu/app/{project_id}/"
    return {
        "url": url,
        "port": port,
        "is_local": _IS_LOCAL,
    }
