# -*- coding: utf-8 -*-
"""通用能力层 — 兵来将挡，水来土掩

系统一次性建好能力接口，所有项目复用。
项目代码通过 HTTP 调用，不关心背后实现。
"""

import base64
from core.ai_engine import vision_chat, generate_sync, web_search, image_generate, speech_generate, music_generate


class CapabilityError(Exception):
    pass


# ── 能力注册表 ──
_CAPABILITIES = {}


def register(name: str, handler):
    _CAPABILITIES[name] = handler


def list_capabilities():
    return [{"name": n, "description": d.__doc__} for n, d in _CAPABILITIES.items()]


async def call(name: str, **kwargs):
    if name not in _CAPABILITIES:
        raise CapabilityError(f"未知能力: {name}")
    # 智能映射：前端统一传 {input: text}，后端映射到 handler 需要的参数名
    if 'input' in kwargs:
        input_val = kwargs.pop('input')
        param_map = {
            'vision.recognize': 'prompt',
            'storage.save': 'key',
            'storage.load': 'key',
            'generate.text': 'prompt',
                        'search.web': 'query',
            'image.generate': 'prompt',
            'tts.generate': 'text',
            'music.generate': 'prompt',
        }
        target = param_map.get(name, 'input')
        if target not in kwargs:
            kwargs[target] = input_val
        # 如果用户已经显式传了 target 参数，则忽略 input（不塞回 kwargs）
    return await _CAPABILITIES[name](**kwargs)


# ── 1. 视觉识别（Vision/OCR） ──
async def vision_recognize(image_base64: str = None, prompt: str = None):
    """识别图片中的文字、公式、手写内容。"""
    if not image_base64:
        return {"error": "视觉识别需要上传图片。请点击输入框旁的 📎 附件按钮上传图片，或直接将图片粘贴到输入框。"}
    default_prompt = "请识别图片中的所有内容。如果是数学作业，按格式输出：\n题目：xxx\n学生答案：xxx\n"
    result = await vision_chat(
        image_base64,
        prompt or default_prompt,
    )
    return {"text": result}


register("vision.recognize", vision_recognize)


# ── 2. 数据存储（Storage） ──
async def storage_save(key: str = None, data: dict = None):
    """保存项目数据到系统数据库。"""
    import json
    if not key:
        raise CapabilityError("缺少 key 参数，请提供要保存的数据键名")
    if data is None:
        data = {}
    from core.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO capabilities_data (key, data, updated_at) VALUES (?, ?, datetime('now'))",
        (key, json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    return {"saved": True}


async def storage_load(key: str = None):
    """从系统数据库加载项目数据。"""
    if not key:
        raise CapabilityError("缺少 key 参数，请提供要读取的数据键名")
    from core.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT data FROM capabilities_data WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        import json
        try:
            return {"data": json.loads(row[0])}
        except Exception:
            return {"data": row[0]}
    return {"data": None}


register("storage.save", storage_save)
register("storage.load", storage_load)


# ── 3. 智能生成（Generate） ──
async def generate_text(prompt: str, system: str = None):
    """调用 AI 生成文本，项目代码不必关心用哪个 provider。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    result = await generate_sync(messages, task_type="fast")
    return {"text": result}


register("generate.text", generate_text)


# ── 初始化数据库表（capabilities_data） ──
def init_capabilities_table():
    from core.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS capabilities_data (
            key TEXT PRIMARY KEY,
            data TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ── 5. 联网搜索（Search）──
async def search_web(query: str, region: str = None, safesearch: str = None, timelimit: str = None):
    """联网搜索，返回结构化结果。

    region: 地区代码，如 "cn-zh", "us-en"
    safesearch: on | moderate | off
    timelimit: d(天) | w(周) | m(月) | y(年)
    """
    result = await web_search(query, region=region, safesearch=safesearch, timelimit=timelimit)
    return {
        "query": result.get("query"),
        "summary": result.get("summary", ""),
        "results": result.get("results", []),
        "tool": result.get("tool"),
        "tool_args": result.get("tool_args"),
    }


register("search.web", search_web)


# ── 6. 图像生成（Image）──
async def image_generate_cap(prompt: str, aspect_ratio: str = "1:1", n: int = 1):
    """文生图，返回图片URL列表。"""
    urls = await image_generate(prompt, aspect_ratio, n)
    return {"urls": urls}


register("image.generate", image_generate_cap)


# ── 7. 语音合成（TTS）──
async def tts_generate(
    text: str,
    voice_id: str = "male-qn-qingse",
    speed: float = 1.0,
    vol: float = 1.0,
    pitch: int = 0,
    emotion: str = None,
    language_boost: str = None,
):
    """文本转语音，返回音频二进制数据（base64编码）。使用 speech-2.8-hd 模型。"""
    audio_bytes = await speech_generate(
        text, voice_id, speed=speed, vol=vol, pitch=pitch,
        emotion=emotion, language_boost=language_boost,
    )
    return {"audio_base64": base64.b64encode(audio_bytes).decode(), "format": "mp3"}


register("tts.generate", tts_generate)


# ── 8. 音乐生成（Music）──
async def music_generate_cap(prompt: str, lyrics: str = "", audio_duration: int = 30):
    """音乐生成，返回音频二进制数据（base64编码）。使用 music-2.6 模型。"""
    audio_bytes = await music_generate(prompt, lyrics, audio_duration)
    return {"audio_base64": base64.b64encode(audio_bytes).decode(), "format": "mp3"}


register("music.generate", music_generate_cap)
