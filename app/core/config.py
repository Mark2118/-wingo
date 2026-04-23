# -*- coding: utf-8 -*-
"""生产级太子配置 - Mac备份节点"""
import os
from dotenv import load_dotenv
load_dotenv()

# 节点拓扑
NODES = {
    "hk-gateway": {
        "host": "8.217.147.240",
        "ssh_host": "8.217.147.240",
        "ssh_port": 22,
        "ssh_user": "root",
        "role": "前线将军-执行节点-冷备",
    },
    "mac-suzhou": {
        "host": os.getenv("MAC_HOST", "127.0.0.1"),
        "ssh_host": os.getenv("MAC_SSH_HOST", "127.0.0.1"),
        "ssh_port": int(os.getenv("MAC_SSH_PORT", "22")),
        "ssh_user": os.getenv("MAC_SSH_USER", "wingosz"),
        "role": "中枢-皇帝-决策记忆源点",
    },
    "ghost-taizi": {
        "host": "101.200.53.200",
        "ssh_host": "101.200.53.200",
        "ssh_port": 22,
        "ssh_user": "admin",
        "role": "幽灵太子-故障接管",
        "monitor": False,
    },
    "gongbu1-win": {
        "host": "100.92.188.101",
        "ssh_host": "100.92.188.101",
        "ssh_port": 22,
        "ssh_user": "73661",
        "role": "工部1-Windows执行",
        "monitor": False,
    },
    "opc-hk-cloud": {
        "host": "100.66.221.85",
        "ssh_host": "100.66.221.85",
        "ssh_port": 22,
        "ssh_user": "root",
        "role": "香港云-nginx网关-执行节点",
    },
    "dell": {
        "host": "100.118.62.87",
        "ssh_host": "100.118.62.87",
        "ssh_port": 22,
        "ssh_user": "lianweiguang0822",
        "role": "Dell-Windows执行节点",
    },
}

# SSH密钥路径（Mac本地）
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/Users/wingosz/.ssh/taizi_ed25519")

# 数据库：Mac本地PostgreSQL
POSTGRESQL = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "wingo_opc_production"),
    "user": os.getenv("DB_USER", "wingo"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# 飞书
FEISHU = {
    "app_id": os.getenv("FEISHU_APP_ID", ""),
    "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
    "encrypt_key": os.getenv("FEISHU_ENCRYPT_KEY", ""),
}

# MiniMax
MINIMAX = {
    "api_key": os.getenv("MINIMAX_KEY", os.getenv("TTS_MINIMAX_API_KEY", os.getenv("IMAGE_MINIMAX_API_KEY", ""))),
    "base_url": os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
    "model": os.getenv("MINIMAX_MODEL", "MiniMax-M2.7-highspeed"),
    "max_tokens": int(os.getenv("MINIMAX_MAX_TOKENS", "2048")),
    "temperature": float(os.getenv("MINIMAX_TEMPERATURE", "0.7")),
}

# n8n（Mac本地无n8n，指向香港）
N8N_URL = os.getenv("N8N_URL", "http://8.217.147.240:5678")

# 太子服务
TAIZI_PORT = int(os.getenv("TAIZI_PORT", "38888"))
TAIZI_HOST = os.getenv("TAIZI_HOST", "0.0.0.0")

# Kimi CLI 绝对路径（Mac 本地安装位置；SSH non-login shell 时 PATH 不完整，必须写死）
KIMI_CLI_MAC_PATH = "/Users/wingosz/.local/bin/kimi-cli"

# GitHub
GITHUB = {
    "token": os.getenv("GITHUB_TOKEN", ""),
    "owner": os.getenv("GITHUB_OWNER", "wingosz"),
    "repo": os.getenv("GITHUB_REPO", "taizi"),
}

# 公网备用入口
BACKUP_BASE_URL = "https://wingoszmac-mini.tail4e781c.ts.net"

# 危险命令黑名单
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "format",
    "mkfs.",
    ":(){:|:&};:",
    "> /dev/sda",
    "dd if=/dev/zero of=/dev/sda",
    "shutdown",
    "reboot",
    "poweroff",
    "init 0",
    "drop database",
    "drop table",
]


# --- WinGo AI Commander 兼容配置 ---
import os
# 新系统根目录（core/config.py 位于 app/core/，向上两级到项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS_DIR = os.path.join(PROJECT_ROOT, 'projects')
os.makedirs(PROJECTS_DIR, exist_ok=True)

KIMI = {
    'api_key': os.getenv('KIMI_API_KEY', ''),
    'base_url': 'https://api.moonshot.cn/v1',
    'model': 'kimi-latest',
    'max_tokens': 4096,
    'temperature': 0.7,
}

OLLAMA = {
    'base_url': 'http://127.0.0.1:11434',
    'model': 'qwen2.5-coder:7b',
}

PORT = int(os.getenv('PORT', '38888'))
HOST = os.getenv('HOST', '0.0.0.0')
PUBLIC_URL = os.getenv('PUBLIC_URL', 'https://wingo.icu')
