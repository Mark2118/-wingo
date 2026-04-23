# -*- coding: utf-8 -*-
"""Caddy 反向代理管理 — Mac 本地子域名路由"""
import os
import re
import subprocess
import time

CADDYFILE = os.path.expanduser("~/taizi/Caddyfile")
CADDY_CONTAINER = "wingo-caddy"


def ensure_caddy_running():
    """确保 Caddy 容器在运行"""
    r = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CADDY_CONTAINER}"],
        capture_output=True, text=True
    )
    if r.stdout.strip():
        return True

    if not os.path.exists(CADDYFILE):
        with open(CADDYFILE, "w") as f:
            f.write('{\n    auto_https off\n}\n\n:80 {\n    respond "Caddy OK" 200\n}\n')

    subprocess.run([
        "docker", "run", "-d", "--name", CADDY_CONTAINER,
        "--network", "host",
        "-v", f"{CADDYFILE}:/etc/caddy/Caddyfile",
        "-v", "caddy_data:/data",
        "-v", "caddy_config:/config",
        "--restart", "unless-stopped",
        "caddy:alpine"
    ], capture_output=True, text=True, timeout=30)

    time.sleep(2)
    return True


def _read_caddyfile():
    if not os.path.exists(CADDYFILE):
        return ""
    with open(CADDYFILE, "r", encoding="utf-8") as f:
        return f.read()


def _write_caddyfile(content):
    with open(CADDYFILE, "w", encoding="utf-8") as f:
        f.write(content)


def _reload_caddy():
    r = subprocess.run(
        ["docker", "exec", CADDY_CONTAINER, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
        capture_output=True, text=True, timeout=10
    )
    return r.returncode == 0


def add_route(domain: str, port: int):
    """添加/更新一个子域名路由"""
    ensure_caddy_running()
    content = _read_caddyfile()
    block = f'http://{domain} {{\n    reverse_proxy host.docker.internal:{port}\n}}\n'

    if f"{domain} {{" in content:
        pattern = re.compile(rf'{re.escape(domain)} \{{[^}}]*\}}\n?', re.DOTALL)
        content = pattern.sub(block, content)
    else:
        content = content.rstrip() + "\n\n" + block

    _write_caddyfile(content)
    return _reload_caddy()


def remove_route(domain: str):
    """删除一个子域名路由"""
    ensure_caddy_running()
    content = _read_caddyfile()
    pattern = re.compile(rf'{re.escape(domain)} \{{[^}}]*\}}\n?', re.DOTALL)
    content = pattern.sub("", content)
    _write_caddyfile(content)
    return _reload_caddy()
