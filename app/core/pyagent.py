# -*- coding: utf-8 -*-
"""
PyAgent — 本地轻量执行器

与 Kimi CLI 的分工：
┌─────────────┬─────────────────────┬─────────────────────┐
│ 维度        │ PyAgent             │ Kimi CLI            │
├─────────────┼─────────────────────┼─────────────────────┤
│ 定位        │ 执行者（手脚）       │ 设计者（大脑）       │
│ 速度        │ 秒级                │ 分钟级              │
│ 成本        │ 极低（本地/Ollama）  │ 高（Kimi 级联）      │
│ 擅长        │ 文件/代码/HTTP/数据  │ 架构/设计/推理/创造  │
│ 触发条件    │ 简单/本地/确定性任务 │ 复杂/创造性/多文件   │
└─────────────┴─────────────────────┴─────────────────────┘

路由规则（ai_engine.py 中配置）：
- 关键词包含「执行」「运行」「读取」「写入」「查询」「转换」→ PyAgent
- 关键词包含「设计」「架构」「生成」「创建」「完整项目」→ Kimi CLI
"""

import json
import os
import re
import subprocess
import tempfile
import ast
import textwrap
from typing import Any, Optional, Union
from datetime import datetime

from core.config import PROJECTS_DIR, DANGEROUS_COMMANDS
from core.ai_engine import generate_sync, AIError

logger = __import__("logging").getLogger("pyagent")


# ── 工具注册表 ──

class ToolError(Exception):
    pass


_REGISTRY = {}


def tool(name: str, desc: str):
    def deco(fn):
        _REGISTRY[name] = {"func": fn, "desc": desc}
        return fn
    return deco


# ── 文件工具 ──

@tool("read_file", "读取文件内容，支持相对路径（基于 PROJECTS_DIR）")
def _read_file(path: str, project_id: str = "") -> str:
    base = os.path.join(PROJECTS_DIR, project_id) if project_id else PROJECTS_DIR
    filepath = os.path.normpath(os.path.join(base, path))
    if not filepath.startswith(os.path.normpath(base)):
        raise ToolError("路径越界")
    if not os.path.isfile(filepath):
        raise ToolError(f"文件不存在: {path}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


@tool("write_file", "写入文件内容，自动创建目录")
def _write_file(path: str, content: str, project_id: str = "") -> str:
    base = os.path.join(PROJECTS_DIR, project_id) if project_id else PROJECTS_DIR
    filepath = os.path.normpath(os.path.join(base, path))
    if not filepath.startswith(os.path.normpath(base)):
        raise ToolError("路径越界")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return f"已写入 {path} ({len(content)} 字节)"


@tool("list_dir", "列出目录内容")
def _list_dir(path: str = ".", project_id: str = "") -> list:
    base = os.path.join(PROJECTS_DIR, project_id) if project_id else PROJECTS_DIR
    dirpath = os.path.normpath(os.path.join(base, path))
    if not dirpath.startswith(os.path.normpath(base)):
        raise ToolError("路径越界")
    if not os.path.isdir(dirpath):
        raise ToolError(f"目录不存在: {path}")
    result = []
    for entry in os.listdir(dirpath):
        full = os.path.join(dirpath, entry)
        result.append({
            "name": entry,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": os.path.getsize(full) if os.path.isfile(full) else None,
        })
    return result


@tool("search_text", "在文件中搜索文本")
def _search_text(pattern: str, path: str = ".", project_id: str = "") -> list:
    base = os.path.join(PROJECTS_DIR, project_id) if project_id else PROJECTS_DIR
    search_dir = os.path.normpath(os.path.join(base, path))
    if not search_dir.startswith(os.path.normpath(base)):
        raise ToolError("路径越界")
    results = []
    for root, _, files in os.walk(search_dir):
        for fname in files:
            if fname.startswith("."):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pattern in line:
                            rel = os.path.relpath(fpath, search_dir)
                            results.append({"file": rel, "line": i, "text": line.strip()})
                            if len(results) >= 50:
                                return results
            except Exception:
                pass
    return results


# ── 代码执行工具 ──

@tool("exec_python", "在受限沙箱中执行 Python 代码，返回 stdout + result")
def _exec_python(code: str, timeout: int = 30) -> dict:
    """执行 Python 代码，带安全限制。"""
    # 安全检查：禁止危险操作
    _check_python_safety(code)

    wrapped = textwrap.dedent(f'''
import json, sys, os, math, random, datetime, re, statistics, itertools, collections, typing, hashlib, base64, string, time, csv, io

_locals = {{}}
_exec_result = None
_exec_stdout = []

class _Capture:
    def write(self, s):
        if s:
            _exec_stdout.append(s)
    def flush(self): pass

_old_stdout = sys.stdout
sys.stdout = _Capture()

try:
{ textwrap.indent(code, "    ") }
    _exec_result = _locals.get("__result__", None)
except Exception as _e:
    _exec_result = {{"error": str(_e), "type": type(_e).__name__}}

sys.stdout = _old_stdout

print("<<<PYAGENT_RESULT>>>")
print(json.dumps({{
    "stdout": "".join(_exec_stdout),
    "result": _exec_result,
}}, ensure_ascii=False, default=str))
''')

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(wrapped)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            ["python3", tmp_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=PROJECTS_DIR,
        )
        # 提取结果
        output = proc.stdout
        marker = "<<<PYAGENT_RESULT>>>"
        if marker in output:
            result_json = output.split(marker, 1)[1].strip()
            data = json.loads(result_json)
            return {
                "success": proc.returncode == 0,
                "stdout": data.get("stdout", ""),
                "result": data.get("result"),
                "stderr": proc.stderr,
            }
        return {
            "success": proc.returncode == 0,
            "stdout": output,
            "result": None,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "result": None, "stderr": f"执行超时 ({timeout}s)"}
    except Exception as exc:
        return {"success": False, "stdout": "", "result": None, "stderr": str(exc)}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _check_python_safety(code: str):
    """静态检查 Python 代码安全性。"""
    dangerous = [
        "__import__", "eval(", "exec(", "compile(", "open(",
        "os.system", "os.popen", "subprocess.", "socket.",
        "importlib", "pty.", "pickle.", "marshal.",
    ]
    for d in dangerous:
        if d in code:
            # 允许 open() 用于项目目录内的文件
            if d == "open(" and "PROJECTS_DIR" in code:
                continue
            raise ToolError(f"代码包含危险操作: {d}")

    # AST 检查
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ToolError(f"语法错误: {exc}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in {"subprocess", "socket", "pty", "pickle", "marshal"}:
                    raise ToolError(f"禁止导入模块: {top}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in {"subprocess", "socket", "pty", "pickle", "marshal"}:
                    raise ToolError(f"禁止导入模块: {top}")


# ── Shell 工具 ──

@tool("run_shell", "执行安全的 shell 命令（带黑名单过滤）")
def _run_shell(cmd: str, cwd: str = None, timeout: int = 60) -> dict:
    for d in DANGEROUS_COMMANDS:
        if d.lower() in cmd.lower():
            raise ToolError(f"危险命令被拦截: {d}")
    project_cwd = os.path.join(PROJECTS_DIR, cwd) if cwd else PROJECTS_DIR
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=project_cwd
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"超时 ({timeout}s)", "exit_code": -1}


# ── HTTP 工具 ──

@tool("http_get", "发送 HTTP GET 请求")
def _http_get(url: str, headers: dict = None, timeout: int = 30) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": resp.read().decode("utf-8", errors="ignore")[:10000],
            }
    except Exception as exc:
        return {"error": str(exc)}


@tool("http_post", "发送 HTTP POST 请求")
def _http_post(url: str, data: str = "", headers: dict = None, timeout: int = 30) -> dict:
    import urllib.request
    req = urllib.request.Request(url, data=data.encode("utf-8"), headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": resp.read().decode("utf-8", errors="ignore")[:10000],
            }
    except Exception as exc:
        return {"error": str(exc)}


# ── 数据工具 ──

@tool("parse_json", "解析 JSON 字符串")
def _parse_json(text: str) -> Any:
    return json.loads(text)


@tool("now", "获取当前时间")
def _now(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


# ── 核心 Agent 循环 ──

SYSTEM_PROMPT_PYAGENT = f"""你是一个本地 Python Agent（PyAgent），负责执行确定性任务。

你的能力（通过 tool_use 调用）：
{chr(10).join(f"- {name}: {meta['desc']}" for name, meta in _REGISTRY.items())}

工作方式：
1. 分析用户需求，判断需要哪些工具
2. 如果一次工具调用就能完成，直接执行并返回结果
3. 如果需要多步，按顺序执行，每步说明在做什么
4. 最终结果用简洁的中文总结

重要规则：
- 不要编造数据，只使用工具返回的真实结果
- 代码执行在沙箱中，禁止危险操作
- 文件操作限制在 PROJECTS_DIR 内
- 如果任务超出能力范围，诚实说明

输出格式：
直接给出执行结果和简短说明，不要多余的寒暄。"""


async def run_pyagent(task: str, project_id: str = "") -> str:
    """
    执行 PyAgent 任务。

    流程：
    1. 让轻量 LLM（MiniMax/Ollama）分析任务，生成 tool_use 计划
    2. 按顺序执行工具
    3. 汇总结果返回

    如果任务明显不需要 LLM（如直接文件读取），跳过 LLM，直接执行。
    """
    task_lower = task.lower()

    # 快速路径：直接工具匹配（不需要 LLM）
    quick = _try_quick_path(task, project_id)
    if quick is not None:
        return quick

    # LLM 规划路径
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_PYAGENT},
        {"role": "user", "content": f"任务: {task}\n\n项目ID: {project_id or '无'}"},
    ]

    try:
        plan = await generate_sync(messages, provider="auto", task_type="fast")
    except AIError as exc:
        return f"PyAgent 规划失败: {exc}"

    # 从 LLM 输出中提取 tool_use 指令
    # 格式: ```tool_use\n{{"tool": "xxx", "args": {{...}}}}\n```
    results = []
    for match in re.finditer(r"```tool_use\n(.*?)\n```", plan, re.S):
        try:
            call = json.loads(match.group(1).strip())
            tool_name = call.get("tool")
            args = call.get("args", {})
            if project_id:
                args.setdefault("project_id", project_id)
            result = _call_tool(tool_name, args)
            results.append(f"【{tool_name}】\n{json.dumps(result, ensure_ascii=False, default=str)[:800]}")
        except Exception as exc:
            results.append(f"【错误】{exc}")

    if not results:
        # LLM 没有输出 tool_use，直接返回 LLM 的回答
        return plan

    # 让 LLM 汇总结果
    summary_msg = [
        {"role": "system", "content": SYSTEM_PROMPT_PYAGENT},
        {"role": "user", "content": f"任务: {task}\n\n工具执行结果:\n{chr(10).join(results)}\n\n请给出最终总结。"},
    ]
    try:
        summary = await generate_sync(summary_msg, provider="auto", task_type="fast")
        return summary
    except AIError:
        return "\n\n".join(results)


def _try_quick_path(task: str, project_id: str) -> Optional[str]:
    """尝试直接匹配简单任务，跳过 LLM，节省时间和 token。"""
    t = task.lower()

    # 读取文件
    m = re.search(r"读取文件\s+(.+)|read\s+file\s+(.+)|cat\s+(.+)|查看\s+(.+)", t)
    if m:
        path = next(g for g in m.groups() if g)
        try:
            content = _read_file(path, project_id)
            return f"📄 `{path}`\n```\n{content[:2000]}{'...' if len(content) > 2000 else ''}\n```"
        except ToolError as exc:
            return f"❌ {exc}"

    # 列出目录
    m = re.search(r"列出目录\s*(.+)|ls\s+(.+)|list\s+dir\s*(.+)|查看目录\s*(.+)", t)
    if m:
        path = next((g for g in m.groups() if g), ".")
        try:
            items = _list_dir(path, project_id)
            lines = []
            for i in items:
                icon = '📁' if i['type'] == 'dir' else '📄'
                size_info = f" ({i['size']} bytes)" if i['size'] else ''
                lines.append(f"{icon} {i['name']}{size_info}")
            return f"📂 `{path}`\n" + "\n".join(lines)
        except ToolError as exc:
            return f"❌ {exc}"

    # 运行 Python
    m = re.search(r"运行[Python代码]*[:：]\s*(.+)|exec[:：]\s*(.+)|计算[:：]\s*(.+)", t, re.S)
    if m:
        code = next(g for g in m.groups() if g)
        try:
            r = _exec_python(code)
            out = r.get("stdout", "")
            result = r.get("result")
            err = r.get("stderr", "")
            text = ""
            if out:
                text += f"stdout:\n{out}\n"
            if result is not None:
                text += f"result: {json.dumps(result, ensure_ascii=False, default=str)}\n"
            if err:
                text += f"stderr:\n{err}\n"
            return text or "✅ 执行完成（无输出）"
        except ToolError as exc:
            return f"❌ {exc}"

    # HTTP GET
    m = re.search(r"请求\s+(https?://\S+)|get\s+(https?://\S+)|curl\s+(https?://\S+)", t)
    if m:
        url = next(g for g in m.groups() if g)
        r = _http_get(url)
        if "error" in r:
            return f"❌ {r['error']}"
        body = r.get("body", "")[:1500]
        return f"Status: {r['status']}\n```\n{body}{'...' if len(r.get('body','')) > 1500 else ''}\n```"

    return None


def _call_tool(name: str, args: dict) -> Any:
    if name not in _REGISTRY:
        raise ToolError(f"未知工具: {name}")
    return _REGISTRY[name]["func"](**args)


# ── 流式接口（兼容 ai_engine） ──

async def call_pyagent_stream(task: str, project_id: str = ""):
    """流式接口，yield chunk。"""
    result = await run_pyagent(task, project_id)
    # 模拟流式输出
    for chunk in result.split("\n"):
        if chunk:
            yield {"type": "chunk", "content": chunk + "\n"}
    yield {"type": "done"}
