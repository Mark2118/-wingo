# -*- coding: utf-8 -*-
"""AI 引擎 v2 — 融合老太子 LLM Gateway 路由层

路由策略（搬运自 llm_gateway.py）：
  - 小活/快响：Ollama（本地，免费，毫秒级）→ MiniMax（云端，15s）
  - 大活/精准：Kimi 级联（Mac Daemon → CLI → API → MiniMax 兜底）
  - 意图解析：generate_json，带 think 清洗 + 正则 JSON 提取
  - 图片识别：vision_chat，支持 base64 图片输入（MiniMax/Kimi）
"""

import json
import httpx
import subprocess
import os
import re
import logging
import asyncio
from typing import List
from core.config import MINIMAX, KIMI, OLLAMA

logger = logging.getLogger("ai_engine")


class AIError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════
#  男女组合分工 — PyAgent ♀ 轻活  +  Kimi CLI ♂ 重活
# ═══════════════════════════════════════════════════════════════

# 轻活（PyAgent — 本地秒级执行）
_LIGHT_TASK_KEYWORDS = [
    "读取", "写入", "查看", "列出", "运行", "执行", "计算",
    "查询", "检查", "验证", "测试", "部署", "转换", "解析",
    "读取文件", "写文件", "ls", "cat", "python", "shell",
    "curl", "http", "json", "csv", "统计", "求和", "排序",
    "文件", "目录", "文件夹", "复制", "移动", "删除",
    "代码", "脚本", "格式化", "压缩", "解压", "编码", "解码",
]

# 重活（Kimi CLI — 深度推理，分钟级）
_HEAVY_TASK_KEYWORDS = [
    "架构", "设计", "多文件", "项目", "系统", "框架", "完整", "全栈",
    "交付", "生成", "创建", "开发", "实现", "编写", "重构",
    "PRD", "需求分析", "产品需求", "方案", "规划", "蓝图",
    "优化", "改进", "升级", "迁移", "集成", "模块", "组件",
    "AI", "模型", "算法", "推荐", "预测", "分析", "报告",
    "网站", "网页", "前端", "后端", "API", "数据库", "服务",
]


def _routing(text: str) -> str:
    """
    男女组合路由 — 判断任务是轻活还是重活。
    返回: 'light' | 'heavy' | 'fast'
    """
    t = text.lower()

    # 先判断重活（优先级高，重活关键词更明确）
    heavy_score = sum(2 if k in t else 0 for k in _HEAVY_TASK_KEYWORDS)
    light_score = sum(1 if k in t else 0 for k in _LIGHT_TASK_KEYWORDS)

    if heavy_score >= 2:
        return "heavy"
    if light_score >= 1 and heavy_score == 0:
        return "light"
    # 默认走轻量 fast 路线（Ollama → MiniMax → PyAgent 兜底）
    return "fast"


def _provider_priority(task_type: str = "fast") -> List[str]:
    """返回 provider 尝试顺序。"""
    if task_type == "heavy":
        # 重活：MiniMax 优先（API 稳定可靠）→ Kimi 级联兜底
        providers = []
        if MINIMAX.get("api_key"):
            providers.append("minimax")
        if KIMI.get("api_key"):
            providers.append("kimi_api")
        if _kimi_cli_available():
            providers.append("kimi_cli")
        # 本地 Ollama 兜底
        if OLLAMA.get("base_url"):
            providers.append("ollama")
        return providers if providers else ["minimax"]
    if task_type == "light":
        # 轻活：PyAgent 优先（女的干轻活）→ Ollama → MiniMax 兜底
        providers = ["pyagent"]
        if OLLAMA.get("base_url"):
            providers.append("ollama")
        if MINIMAX.get("api_key"):
            providers.append("minimax")
        if KIMI.get("api_key"):
            providers.append("kimi")
        return providers
    # fast: 通用快速路线
    providers = []
    if OLLAMA.get("base_url"):
        providers.append("ollama")
    if MINIMAX.get("api_key"):
        providers.append("minimax")
    if KIMI.get("api_key"):
        providers.append("kimi")
    providers.append("kimi_cli")
    # 去重
    seen = set()
    return [p for p in providers if not (p in seen or seen.add(p))]


# ── Provider 调用 ──

async def _call_ollama(messages: list, model: str = None, timeout: float = 12.0):
    """Ollama /api/chat 流式。"""
    model = model or OLLAMA.get("model", "qwen2.5-coder:7b")
    payload = {"model": model, "messages": messages, "stream": True}
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST", f"{OLLAMA['base_url']}/api/chat", json=payload, timeout=timeout
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("done"):
                        yield {"type": "done"}
                        return
                    text = obj.get("message", {}).get("content", "")
                    if text:
                        yield {"type": "chunk", "content": text}
                except Exception:
                    pass


async def _call_minimax(messages: list, timeout: float = 15.0):
    """MiniMax 流式。"""
    headers = {
        "Authorization": f"Bearer {MINIMAX['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MINIMAX["model"],
        "messages": messages,
        "stream": True,
        "max_tokens": MINIMAX.get("max_tokens", 2048),
        "temperature": MINIMAX.get("temperature", 0.3),
    }
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST", f"{MINIMAX['base_url']}/chat/completions",
            headers=headers, json=payload, timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    yield {"type": "done"}
                    return
                try:
                    obj = json.loads(data)
                    text = obj["choices"][0].get("delta", {}).get("content", "")
                    if text:
                        yield {"type": "chunk", "content": text}
                except Exception:
                    pass


async def _call_kimi_api(messages: list, timeout: float = 300.0):
    """Kimi API (Moonshot) 流式。"""
    key = KIMI.get("api_key", "")
    if not key:
        raise AIError("KIMI API key 未配置")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": KIMI.get("model", "kimi-k2-0711-preview"),
        "messages": messages,
        "stream": True,
        "max_tokens": KIMI.get("max_tokens", 4096),
        "temperature": KIMI.get("temperature", 0.3),
    }
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST", "https://api.moonshot.cn/v1/chat/completions",
            headers=headers, json=payload, timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    yield {"type": "done"}
                    return
                try:
                    obj = json.loads(data)
                    text = obj["choices"][0].get("delta", {}).get("content", "")
                    if text:
                        yield {"type": "chunk", "content": text}
                except Exception:
                    pass


# ── Kimi CLI（非流式） ──

_KIMI_CLI_PATH = None


def _resolve_kimi_cli() -> str:
    global _KIMI_CLI_PATH
    if _KIMI_CLI_PATH is not None:
        return _KIMI_CLI_PATH
    import shutil
    path = shutil.which("kimi-cli")
    if path:
        _KIMI_CLI_PATH = path
        return path
    for p in [
        "/Users/wingosz/.local/bin/kimi-cli",
        "C:\\Users\\73661\\.local\\bin\\kimi-cli.exe",
        "/usr/local/bin/kimi-cli",
    ]:
        if os.path.isfile(p):
            _KIMI_CLI_PATH = p
            return p
    _KIMI_CLI_PATH = ""
    return ""


def _kimi_cli_available() -> bool:
    return bool(_resolve_kimi_cli())


async def _generate_kimi_cli(messages: list, timeout: float = 300.0) -> str:
    """Kimi CLI 非流式，返回完整文本。"""
    cli = _resolve_kimi_cli()
    if not cli:
        raise AIError("kimi-cli 未安装")

    prompt_parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            prompt_parts.append(f"[系统指令]\n{content}")
        elif role == "user":
            prompt_parts.append(f"[用户]\n{content}")
        else:
            prompt_parts.append(content)
    prompt = "\n\n".join(prompt_parts)

    cmd = [cli, "--print", "--output-format", "stream-json", "-p", prompt]
    work_dir = "/tmp"

    def _run():
        before = set(os.listdir(work_dir)) if os.path.isdir(work_dir) else set()
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=work_dir
        )
        after = set(os.listdir(work_dir)) if os.path.isdir(work_dir) else set()
        new_files = after - before
        code_files = []
        for f in sorted(new_files):
            fp = os.path.join(work_dir, f)
            if os.path.isfile(fp) and f.endswith((".html", ".css", ".js", ".py", ".md", ".txt", ".json")):
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    code_files.append(f"=== FILE: {f} ===\n{content}\n=== END ===")
                except Exception:
                    pass
        if code_files:
            return "\n\n".join(code_files)
        return _extract_kimi_cli_json(proc.stdout)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)


def _extract_kimi_cli_json(output: str) -> str:
    results = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("To resume"):
            continue
        try:
            obj = json.loads(line)
            if obj.get("role") == "assistant":
                for item in obj.get("content", []):
                    if item.get("type") == "text":
                        results.append(item.get("text", ""))
        except json.JSONDecodeError:
            continue
    return "\n".join(results) if results else output


# ── Kimi Mac Daemon ──

KIMI_MAC_DAEMON_URL = os.getenv("KIMI_MAC_DAEMON_URL", "http://127.0.0.1:39999")


async def _call_kimi_mac_daemon(messages: list, timeout: float = 300.0) -> str:
    prompt = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages if m.get("content"))
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{KIMI_MAC_DAEMON_URL}/generate",
            json={"prompt": prompt, "timeout": timeout},
            timeout=timeout + 15,
        )
        r.raise_for_status()
        data = r.json()
    if not data.get("ok"):
        raise AIError(f"Mac Daemon 失败: {data.get('error', 'unknown')}")
    return data.get("code", "")


# ── 统一流式入口 ──

async def stream_chat(messages: list, provider: str = "auto", task_type: str = None):
    """统一流式生成入口，自动 fallback。

    provider: auto | ollama | minimax | kimi | kimi_cli
    task_type: fast | kimi（覆盖 provider 自动判断）
    """
    if provider == "auto":
        if task_type:
            route = task_type
        else:
            route = _routing(messages[-1]["content"]) if messages else "fast"
    else:
        route = provider

    providers = _provider_priority(route) if route != provider else [provider]
    last_err = ""

    for p in providers:
        try:
            logger.info("[AIEngine] trying provider=%s", p)
            if p == "ollama":
                async for chunk in _call_ollama(messages):
                    yield chunk
                return
            elif p == "minimax":
                async for chunk in _call_minimax(messages):
                    yield chunk
                return
            elif p == "kimi":
                async for chunk in _call_kimi_api(messages):
                    yield chunk
                return
            elif p == "kimi_cli":
                text = await _generate_kimi_cli(messages)
                if text:
                    yield {"type": "chunk", "content": text}
                yield {"type": "done"}
                return
            elif p == "kimi_mac_daemon":
                text = await _call_kimi_mac_daemon(messages)
                if text:
                    yield {"type": "chunk", "content": text}
                yield {"type": "done"}
                return
            elif p == "pyagent":
                # PyAgent — 轻活执行器（女的干轻活）
                from core.pyagent import call_pyagent_stream
                task = messages[-1].get("content", "") if messages else ""
                async for chunk in call_pyagent_stream(task):
                    yield chunk
                return
        except Exception as exc:
            last_err = str(exc)
            logger.warning("[AIEngine] %s failed: %s", p, exc)
            continue

    yield {"type": "error", "content": f"所有 provider 均失败，最后错误: {last_err}"}


# ── 非流式入口 ──

async def generate_sync(messages: list, provider: str = "auto", task_type: str = None) -> str:
    """非流式，直接返回完整文本。"""
    parts = []
    async for chunk in stream_chat(messages, provider, task_type):
        if chunk["type"] == "chunk":
            parts.append(chunk["content"])
        elif chunk["type"] == "error":
            raise AIError(chunk["content"])
    return _clean_think("".join(parts))


# ── JSON 安全解析（搬运自 llm_gateway.generate_json） ──

async def generate_json(messages: list, provider: str = "auto", task_type: str = "fast") -> str:
    """生成并清洗 JSON，失败时正则提取第一个平衡 JSON 对象。"""
    raw = await generate_sync(messages, provider, task_type)
    raw = _clean_think(raw)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.S)
    if not m:
        raise AIError(f"LLM 输出中未找到 JSON: {raw[:200]}")
    return m.group(0)


# ── 图片识别（Vision） ──

async def _call_kimi_vision_api(messages: list) -> str:
    """Kimi vision API，非流式，使用确定支持 vision 的模型。"""
    key = KIMI.get("api_key", "")
    if not key:
        raise AIError("KIMI API key 未配置")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "kimi-k2.5",
        "messages": messages,
        "stream": False,
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.moonshot.cn/v1/chat/completions",
            headers=headers, json=payload, timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def vision_chat(image_base64: str, prompt: str, provider: str = "auto") -> str:
    """传入 base64 图片 + 文字 prompt，返回 AI 识别结果。

    当前优先 Kimi API（强制使用 vision 模型 kimi-k2.5），fallback MiniMax。
    """
    # 检测 base64 图片格式并设置正确 MIME 类型
    mime = "image/png"
    if image_base64.startswith("/9j/"):
        mime = "image/jpeg"
    elif image_base64.startswith("R0lGOD"):
        mime = "image/gif"
    elif image_base64.startswith("UklGR"):
        mime = "image/webp"

    content = [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_base64}"}},
        {"type": "text", "text": prompt or "请识别图片中的内容"},
    ]
    messages = [{"role": "user", "content": content}]

    # 优先 Kimi API（强制使用 vision 模型）
    if KIMI.get("api_key") and provider in ("auto", "kimi"):
        try:
            return await _call_kimi_vision_api(messages)
        except Exception as exc:
            logger.warning("[AIEngine] Kimi vision failed: %s", exc)

    # fallback MiniMax（部分模型支持图片）
    if MINIMAX.get("api_key") and provider in ("auto", "minimax"):
        try:
            return await generate_sync(messages, provider="minimax")
        except Exception as exc:
            logger.warning("[AIEngine] MiniMax vision failed: %s", exc)

    raise AIError("没有可用的 vision provider")


# ── 联网搜索（Web Search）──

async def web_search(
    query: str,
    provider: str = "minimax",
    region: str = None,
    safesearch: str = None,
    timelimit: str = None,
) -> dict:
    """联网搜索 — DuckDuckGo + MiniMax AI 总结。

    region: 地区代码，如 "cn-zh", "us-en", "wt-wt"(全球)
    safesearch: on | moderate | off
    timelimit: d(天) | w(周) | m(月) | y(年)
    """
    import asyncio
    import sys
    sys.path.insert(0, "/Users/wingosz/Library/Python/3.9/lib/python/site-packages")

    # 第一步：DuckDuckGo 搜索（无需 API key）
    def _ddg_search():
        from duckduckgo_search import DDGS
        kwargs = {"max_results": 5}
        if region:
            kwargs["region"] = region
        if safesearch:
            kwargs["safesearch"] = safesearch
        if timelimit:
            kwargs["timelimit"] = timelimit
        with DDGS() as ddgs:
            return list(ddgs.text(query, **kwargs))

    try:
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(None, _ddg_search)
    except Exception as exc:
        logger.warning("[web_search] DuckDuckGo failed: %s", exc)
        search_results = []

    if not search_results:
        return {
            "query": query,
            "summary": "抱歉，当前无法获取搜索结果。请稍后重试。",
            "results": [],
        }

    # 格式化搜索结果
    results_text = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['body'][:200]}...\n{r['href']}"
        for i, r in enumerate(search_results)
    )

    # 第二步：用 MiniMax AI 总结（如果 API 可用）
    if MINIMAX.get("api_key"):
        try:
            headers = {
                "Authorization": f"Bearer {MINIMAX['api_key']}",
                "Content-Type": "application/json",
            }
            summary_prompt = (
                f"根据以下搜索结果，用中文简洁回答用户的问题。\n\n"
                f"用户问题：{query}\n\n"
                f"搜索结果：\n{results_text}\n\n"
                f"请给出简洁的回答（不超过300字）："
            )
            payload = {
                "model": "MiniMax-M2.7",
                "messages": [{"role": "user", "content": summary_prompt}],
                "max_tokens": 1024,
                "temperature": 0.3,
            }
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{MINIMAX['base_url']}/chat/completions",
                    headers=headers, json=payload, timeout=30,
                )
                r.raise_for_status()
                data = r.json()
                summary = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                summary = _clean_think(summary)
        except Exception as exc:
            logger.warning("[web_search] AI summary failed: %s", exc)
            summary = results_text[:800]
    else:
        summary = results_text[:800]

    return {
        "query": query,
        "summary": summary,
        "results": search_results,
    }

async def image_generate(prompt: str, aspect_ratio: str = "1:1", n: int = 1) -> list:
    """调用 MiniMax image-01 文生图。

    返回图片URL列表。
    """
    if not MINIMAX.get("api_key"):
        raise AIError("MINIMAX API key 未配置")

    headers = {
        "Authorization": f"Bearer {MINIMAX['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "image-01",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": n,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{MINIMAX['base_url']}/image_generation",
            headers=headers, json=payload, timeout=60,
        )
        r.raise_for_status()
        data = r.json()

    if data.get("base_resp", {}).get("status_code") != 0:
        raise AIError(f"图像生成失败: {data.get('base_resp', {})}")

    urls = []
    for img in data.get("data", {}).get("image_urls", []):
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict):
            urls.append(img.get("url", ""))
    return urls


# ── 语音合成（TTS）──

async def speech_generate(
    text: str,
    voice_id: str = "male-qn-qingse",
    model: str = None,
    speed: float = 1.0,
    vol: float = 1.0,
    pitch: int = 0,
    emotion: str = None,
    language_boost: str = None,
) -> bytes:
    """调用 MiniMax TTS 语音合成。

    支持参数：
      speed: 0.5 ~ 2.0 (语速)
      vol: 0 ~ 10 (音量)
      pitch: -12 ~ 12 (语调)
      emotion: happy/sad/angry/fearful/disgusted/surprised/calm/fluent/whisper
      language_boost: 语言增强，如 "Chinese"

    注意：当前 Coding Plan 旧 key (sk-cp-) 仅支持 speech-01；
    Token Plan 新 key (sk-tp-) 支持 speech-2.8 等高级模型。

    返回音频二进制数据（mp3）。
    """
    if not MINIMAX.get("api_key"):
        raise AIError("MINIMAX API key 未配置")

    if model is None:
        model = "speech-2.8-hd"

    headers = {
        "Authorization": f"Bearer {MINIMAX['api_key']}",
        "Content-Type": "application/json",
    }
    voice_setting = {
        "voice_id": voice_id,
        "speed": max(0.5, min(2.0, speed)),
        "vol": max(0.0, min(10.0, vol)),
        "pitch": max(-12, min(12, pitch)),
    }
    if emotion:
        voice_setting["emotion"] = emotion

    payload = {
        "model": model,
        "text": text,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    if language_boost:
        payload["language_boost"] = language_boost

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{MINIMAX['base_url']}/t2a_v2",
            headers=headers, json=payload, timeout=30,
        )
        r.raise_for_status()
        data = r.json()

    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") != 0:
        # 如果是模型不支持，给友好提示
        if "not support model" in base_resp.get("status_msg", "").lower():
            raise AIError(
                f"TTS模型不支持: {model}。当前API Key类型可能不支持该模型。"
                f"建议升级到 Token Plan 以解锁 speech-2.8 等高级语音模型。"
            )
        raise AIError(f"语音合成失败: {base_resp}")

    # 返回音频二进制
    audio_data = data.get("data", {})
    audio_hex = audio_data.get("audio", "") if isinstance(audio_data, dict) else audio_data
    if audio_hex and isinstance(audio_hex, str):
        return bytes.fromhex(audio_hex)
    raise AIError("语音合成返回空音频数据")


# ── 音乐生成（Music）──

async def music_generate(prompt: str, lyrics: str = "", audio_duration: int = 30) -> bytes:
    """调用 MiniMax music-2.6 生成音乐。

    返回音频二进制数据（mp3）。
    """
    if not MINIMAX.get("api_key"):
        raise AIError("MINIMAX API key 未配置")

    headers = {
        "Authorization": f"Bearer {MINIMAX['api_key']}",
        "Content-Type": "application/json",
    }
    # MiniMax music-2.6 要求 lyrics 不能为空
    if not lyrics:
        lyrics = prompt
    payload = {
        "model": "music-2.6",
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": audio_duration,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{MINIMAX['base_url']}/music_generation",
            headers=headers, json=payload, timeout=120,
        )
        r.raise_for_status()
        data = r.json()

    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") != 0:
        raise AIError(f"音乐生成失败: {base_resp}")

    audio_data = data.get("data", {})
    audio_hex = audio_data.get("audio", "") if isinstance(audio_data, dict) else audio_data
    if audio_hex and isinstance(audio_hex, str):
        return bytes.fromhex(audio_hex)
    raise AIError("音乐生成返回空音频数据")


# ── 工具 ──

def _clean_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"</?think>", "", text)
    return text.strip()
