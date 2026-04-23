# -*- coding: utf-8 -*-
"""飞书企业应用机器人 — 对话式发射台

用户在企业飞书群里@机器人说话，自动触发 WinGo 的写需求/发射/查状态。
"""

import os
import json
import re
import base64
import hashlib
import struct
import httpx
from datetime import datetime, timedelta
from Crypto.Cipher import AES

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")

# 04 OpenClaw 的飞书 sender_id（union_id 或 open_id），用于自动识别并记录其发言
OPENCLAW_SENDER_ID = os.getenv("OPENCLAW_SENDER_ID", "")

_token_cache = {"token": "", "expire": 0}


def _decrypt_feishu(encrypt: str) -> dict:
    """飞书 AES-256-CBC 解密。encrypt_key 的 MD5 前16字节作为 key。"""
    if not FEISHU_ENCRYPT_KEY:
        try:
            return json.loads(encrypt)
        except Exception:
            return {}
    try:
        key = hashlib.md5(FEISHU_ENCRYPT_KEY.encode()).digest()[:16]
        cipher_text = base64.b64decode(encrypt)
        iv = key[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plain = cipher.decrypt(cipher_text)
        # 去掉 PKCS7 padding
        pad_len = plain[-1]
        if pad_len > 16:
            pad_len = 0
        plain = plain[:-pad_len] if pad_len > 0 else plain
        # 格式: random(16) + content_len(4) + content + app_id
        content_len = struct.unpack(">I", plain[16:20])[0]
        content = plain[20:20 + content_len].decode("utf-8")
        return json.loads(content)
    except Exception as e:
        # 调试日志
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "feishu_decrypt.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{datetime.now().isoformat()} DECRYPT ERROR: {e}\nencrypt prefix: {encrypt[:80]}\n")
        return {}


async def get_tenant_token() -> str:
    """获取飞书 tenant_access_token，带缓存。"""
    global _token_cache
    if _token_cache["token"] and datetime.now().timestamp() < _token_cache["expire"]:
        return _token_cache["token"]

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return ""

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        )
        data = r.json()
        token = data.get("tenant_access_token", "")
        expire = data.get("expire", 7200)
        if token:
            _token_cache["token"] = token
            _token_cache["expire"] = datetime.now().timestamp() + expire - 300
        return token


async def send_message(chat_id: str, text: str):
    """发送文本消息到飞书群聊。"""
    token = await get_tenant_token()
    if not token or not chat_id:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return r.status_code == 200


async def reply_message(message_id: str, text: str):
    """回复某条消息（线程回复）。"""
    token = await get_tenant_token()
    if not token or not message_id:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": json.dumps({"text": text}, ensure_ascii=False),
                "msg_type": "text",
            },
        )
        if r.status_code != 200:
            log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "feishu.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} REPLY_FAIL: status={r.status_code}, body={r.text[:200]}\n")
        return r.status_code == 200


def _parse_mention_text(raw_content: str) -> str:
    """去掉 @机器人 的 mention，提取纯文本。"""
    try:
        data = json.loads(raw_content)
        text = data.get("text", "")
        # 去掉飞书的 @user 格式 <at id="xxx"></at>
        text = re.sub(r'<at[^>]*></at>', '', text).strip()
        return text
    except Exception:
        return ""


def parse_intent(text: str) -> dict:
    """解析用户消息意图。

    Returns:
        {"action": "launch"|"需求"|"看板"|"状态"|"04"|"help"|"unknown", "content": str}
    """
    t = text.lower()

    # 发射类
    if any(k in t for k in ["发射", "启动", "跑", "开始", "launch", "start"]):
        return {"action": "launch", "content": text}

    # 系统状态查询
    if any(k in t for k in ["状态", "status", "健康", "health"]):
        return {"action": "状态", "content": text}

    # 看板查询
    if any(k in t for k in ["看板", "进度", "kanban", "board"]):
        return {"action": "看板", "content": text}

    # 04/OpenClaw 相关查询
    if any(k in t for k in ["04", "openclaw", "推广", "营销", "销售"]):
        return {"action": "04", "content": text}

    # 需求/新建任务
    if any(k in t for k in ["我要", "新建", "写", "需求", "任务", "做一个", "需要"]):
        return {"action": "需求", "content": text}

    # 帮助
    if any(k in t for k in ["帮助", "help", "怎么用", "指令"]):
        return {"action": "help", "content": text}

    return {"action": "unknown", "content": text}


async def handle_event(raw_payload: dict) -> dict:
    """处理飞书事件回调。支持解密和 Verification Token 校验。"""
    # 调试日志
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "feishu.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{datetime.now().isoformat()} RAW: {json.dumps(raw_payload, ensure_ascii=False)[:500]}\n")

    # 1. 解密（如果开了 Encrypt Key）
    encrypt = raw_payload.get("encrypt")
    if encrypt:
        payload = _decrypt_feishu(encrypt)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} DECRYPTED: {json.dumps(payload, ensure_ascii=False)[:500]}\n")
    else:
        payload = raw_payload

    # 2. Verification Token 校验（兼容 challenge 顶层 token 和 V2.0 header token）
    token = payload.get("token") or payload.get("header", {}).get("token", "")
    if FEISHU_VERIFY_TOKEN and token != FEISHU_VERIFY_TOKEN:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} TOKEN MISMATCH: got={token}\n")
        return {}

    # 3. URL 验证挑战
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # 4. 消息事件
    event_type = payload.get("header", {}).get("event_type", "")
    if event_type != "im.message.receive_v1":
        return {}

    event = payload.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})

    chat_id = message.get("chat_id", "")
    message_id = message.get("message_id", "")
    msg_type = message.get("message_type", "")
    content = message.get("content", "")
    chat_type = message.get("chat_type", "")

    # 只处理文本消息
    if msg_type != "text":
        return {}

    text = _parse_mention_text(content)
    if not text:
        return {}

    # ── 识别发送者 ──
    sender_id_obj = sender.get("sender_id", {})
    union_id = sender_id_obj.get("union_id", "")
    open_id = sender_id_obj.get("open_id", "")
    sender_type = sender.get("sender_type", "")

    # ── 04 OpenClaw 自动记录 ──
    # 如果配置了 OPENCLAW_SENDER_ID，且发送者匹配 → 自动写入 memory
    if OPENCLAW_SENDER_ID and (union_id == OPENCLAW_SENDER_ID or open_id == OPENCLAW_SENDER_ID):
        from core.memory import save_memory
        save_memory(category="04协作", content=text, source="04", project_id="mingjing")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} OPENCLAW_RECORDED: {text[:100]}\n")
        # 不给 04 回复，避免循环对话
        return {}

    # ── 检查是否 @太子（群聊需要，私聊不需要）──
    mentions = message.get("mentions", [])
    is_mention_taizi = (chat_type == "p2p") or len(mentions) > 0
    if not is_mention_taizi:
        return {}

    intent = parse_intent(text)
    action = intent["action"]

    # 路由处理
    if action == "help":
        reply = (
            "🚀 WinGo 发射台指令：\n"
            "• 我要xxx / 需求xxx → 写入需求池\n"
            "• 发射 [项目ID] → 启动 Pipeline\n"
            "• 看板 / 状态 → 查三列状态\n"
            "• 04 / 推广 → 查 OpenClaw 动态\n"
            "• 帮助 → 显示本条\n\n"
            "💡 04 在群里，直接 @OpenClaw 即可下指令"
        )
        await reply_message(message_id, reply)

    elif action == "状态":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://127.0.0.1:38888/api/health")
                data = r.json()
                status = data.get("status", "unknown")
                mem = data.get("memory_mb", 0)
                n8n = data.get("n8n", "unknown")
                maic = data.get("openmaic", "unknown")
                reply = f"🟢 wingo: {status}\n💾 内存: {mem}MB\n🤖 n8n: {n8n}\n📚 OpenMAIC: {maic}"
        except Exception as e:
            reply = f"🔴 wingo 健康检查失败: {str(e)[:30]}"
        await reply_message(message_id, reply)

    elif action == "看板":
        from core.memory import search_memory
        entries = search_memory(project_id="mingjing")
        tasks = [e for e in entries if e.get("status")]
        lines = ["📋 mingjing 看板："]
        srcLabel = {"01": "01", "02": "02", "03": "03", "04": "04"}
        for st in ["待办", "进行中", "已完成"]:
            sub = [t for t in tasks if t.get("status") == st]
            lines.append(f"\n【{st}】{len(sub)}条")
            for t in sub:
                src = srcLabel.get(t.get("source"), "01")
                lines.append(f"  [{src}] {t.get('content', '')[:30]}")
        reply = "\n".join(lines) if tasks else "看板暂无任务。"
        await reply_message(message_id, reply)

    elif action == "04":
        from core.memory import search_memory
        entries = search_memory(source="04", project_id="mingjing", limit=10)
        if not entries:
            reply = "📢 04 (OpenClaw) 暂无协作记录。\n\n💡 提示：直接在群里 @OpenClaw 即可给它下指令，太子会自动记录它的回复。"
        else:
            lines = ["📢 04 (OpenClaw) 最近动态："]
            for e in entries[:5]:
                content = e.get("content", "")[:50]
                time = e.get("time", "未知")
                lines.append(f"  {time} {content}")
            reply = "\n".join(lines)
        await reply_message(message_id, reply)

    elif action == "需求":
        from core.memory import save_memory
        result = save_memory(
            category="需求",
            content=intent["content"],
            project_id="mingjing",
            source="01",  # 飞书操作默认算 01（人类发起）
        )
        reply = f"✅ 需求已记录\nID: {result.get('id', 'N/A')}\n内容: {intent['content'][:50]}"
        await reply_message(message_id, reply)

    elif action == "launch":
        # 飞书二次确认发射：提取项目ID，调用本地 API 真正发射
        import httpx
        content = intent["content"]
        # 尝试提取项目ID（"发射 xxx" 或 "发射 [xxx]"）
        pid = ""
        m = re.search(r'发射\s+([a-f0-9]+)', content)
        if m:
            pid = m.group(1)
        if not pid:
            reply = "🚀 发射指令格式：发射 [项目ID]\n例：发射 b8a6978f"
            await reply_message(message_id, reply)
            return {}

        # 先记录请求
        from core.memory import save_memory
        save_memory(category="发射请求", content=content, project_id=pid, source="01")

        # 调用本地 API 触发发射（source=feishu 通过安全校验）
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "http://127.0.0.1:38888/api/launch",
                    json={"project_id": pid, "prd": "", "source": "feishu"},
                )
                data = r.json()
                if data.get("error"):
                    reply = f"🚀 发射请求已记录\n项目: {pid}\n状态: {data['error']}"
                else:
                    reply = f"🚀 发射确认通过！\n项目: {pid}\nPipeline 已启动，回 Mac 前端看进度。"
        except Exception as e:
            reply = f"🚀 发射请求已记录\n项目: {pid}\n但启动失败: {str(e)[:50]}"
        await reply_message(message_id, reply)

    else:
        # 太子 AI 对话模式
        from core.ai_engine import generate_sync
        try:
            reply = await generate_sync(
                [
                    {"role": "system", "content": "你是『太子』，WinGo 系统的 AI 助手。你说话直接、带点个性，不装腔作势。你知道系统里有三个节点：01-Mac（中枢/调度）、02-Windows（工部/STEAM+财商）、03-移动指挥所（前线/SSH连01操作全局）。03 不直连 02，所有操作通过 01 中转。你能帮用户操作看板、记录需求、查状态。如果用户的话明显是闲聊，你就正常聊；如果涉及系统操作，你简要说明怎么操作就行。"},
                    {"role": "user", "content": text},
                ],
                provider="minimax",
                task_type="light",
            )
        except Exception as e:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} AI_ERROR: {type(e).__name__}: {str(e)[:200]}\n")
            reply = "太子脑子卡了一下，你再说一遍？"
        ok = await reply_message(message_id, reply)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} REPLY: ok={ok}, msg={reply[:50]}\n")

    return {}
