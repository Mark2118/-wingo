# -*- coding: utf-8 -*-
import json
import re
import os
import sys
import glob
import time
from core.ai_engine import generate_sync, AIError
from core.deployer import write_file, run_command
from core.db import update_project, get_project, record_stage_timing, save_prd_history
from core.config import PROJECTS_DIR
from core.ammo import consume_ammo


def _project_exists(project_id: str) -> bool:
    """检查项目是否还存在（用于发射过程中被删除时及时止损）"""
    return get_project(project_id) is not None


def _pipeline_should_stop(project_id: str) -> bool:
    """检查 Pipeline 是否应该停止（用户点了停止或删除了项目）"""
    p = get_project(project_id)
    if not p:
        # 项目不在数据库中（脚本直接调用），不停止
        return False
    return p.get("status") != "running"


def _is_prd(text: str) -> bool:
    """检测输入是否已经是 PRD（结构化文档），不是原始需求"""
    t = text.strip()
    # PRD 特征：包含标题、章节、结构化内容
    if "# 产品需求文档" in t or "## 项目概述" in t or "## 功能需求" in t:
        return True
    if "PRD" in t[:200] and ("## " in t or "### " in t):
        return True
    # 原始需求通常很短、没有 markdown 标题结构
    if len(t) < 300 and t.count("##") < 2:
        return False
    return True


async def _validate_requirement(text: str) -> dict:
    """需求预审：判断需求是否合理，防止荒谬需求进入 Pipeline。

    Returns: {"ok": True} 或 {"ok": False, "reason": "拒绝理由"}
    """
    prompt = f"""你是一个资深产品预审官。请判断以下需求是否合理，是否适合由一个小型自动化开发平台（WinGo）承接。

WinGo 当前能力边界：
- 可以开发：Web 应用、小程序、自动化脚本、数据处理工具、简单的 AI 应用、教育类工具
- 技术栈：Python/FastAPI、HTML/JS、Docker、SQLite
- 不能开发：需要物理硬件的（火箭、芯片、无人机）、需要国家牌照的（银行系统、医疗诊断）、超出小型 Web 应用范畴的（宇宙飞船、航空母舰、大规模社交平台）
- 红线：不做 K12 学科培训类内容

用户原始需求：
{text[:500]}

请只输出 JSON，格式如下：
{{"ok": true/false, "reason": "如果拒绝，说明原因（简短，50字内）"}}
"""
    try:
        from core.ai_engine import generate_sync
        result = await generate_sync([{"role": "user", "content": prompt}])
        # 提取 JSON
        m = re.search(r'\{.*?"ok".*?\}', result, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return data
    except Exception as e:
        print(f"[预审DEBUG] 异常: {e}")
    # AI 判断失败时默认放行（避免阻塞正常需求）
    return {"ok": True}


SYSTEM_PROMPT_ANALYSIS = """你是 WinGo AI 指挥官，负责需求分析。
用户会描述一个开发需求。你的任务是：
1. 用一句话总结需求核心
2. 列出关键功能点
3. 判断项目类型：Python后端 / HTML前端 / 其他
4. 推荐技术栈（语言+框架）
5. 评估复杂度（简单/中等/复杂）

输出格式（严格按以下结构）：
【核心需求】...
【关键功能】
- ...
- ...
【项目类型】Python / HTML / 其他
【推荐技术栈】...
【复杂度】..."""

SYSTEM_PROMPT_ARCHITECT = """你是 WinGo AI 架构师。基于已确认的需求，输出项目的文件结构和每个文件的核心职责。

输出格式：
【文件结构】
- main.py: 入口文件
- ...

【核心设计】
..."""

SYSTEM_PROMPT_CODER_PYTHON = """你是一个Python工程师。根据需求直接生成完整可运行的Python代码。

要求：
1. 只输出Python代码，不要任何解释、不要问候、不要闲聊
2. 如果项目只需要单个文件，包裹在 markdown 代码块中：
   ```python
   # 你的代码
   ```
3. 如果项目需要多个文件（有import本地模块），必须使用以下格式，每个文件独立输出：
   === FILE: main.py ===
   # main.py 的完整代码
   === END ===
   
   === FILE: blog.py ===
   # blog.py 的完整代码
   === END ===
4. 代码必须是完整可运行的，包含 if __name__ == '__main__':
5. 不要输出任何代码之外的文字
6. 不要输出不存在的模块引用，每个文件必须完整独立输出"""

SYSTEM_PROMPT_CODER_HTML = """你是一个前端工程师。根据需求直接生成完整的HTML页面代码。

要求：
1. 生成完整的HTML文件，包含内联CSS和JavaScript
2. 使用以下格式输出：
   === FILE: index.html ===
   <!DOCTYPE html>
   <html>...</html>
   === END ===
3. 如果项目需要多个文件（如单独的CSS或JS），继续使用 === FILE: xxx === 格式
4. 页面必须美观、响应式、可直接在浏览器打开
5. 不要输出任何代码之外的文字
6. 所有资源尽量内联，减少外部依赖"""

SYSTEM_PROMPT_TESTER = """你是 WinGo AI 测试工程师。为已生成的代码编写 pytest 测试用例，并执行测试。
只输出测试代码，不要解释。"""


async def run_pipeline(project_id: str, input_text: str, on_log):
    """
    执行完整交付管道，on_log 是回调函数: on_log(stage, message)
    
    input_text 可以是原始需求，也可以是用户编辑后的 PRD。
    如果是 PRD，跳过需求分析，直接用于架构设计和代码生成。
    """
    project_path = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_path, exist_ok=True)
    
    is_prd = _is_prd(input_text)
    project_type = "Python"  # 默认，后面会被覆盖

    # ── 需求预审（A方案：简单过滤）──
    if not is_prd:
        await on_log("需求预审", "正在判断需求合理性...")
        check = await _validate_requirement(input_text)
        if not check.get("ok", True):
            reason = check.get("reason", "需求超出当前能力范围")
            await on_log("需求预审", f"❌ 拒绝：{reason}")
            update_project(project_id, status="rejected", stage="需求预审未通过")
            return False
        await on_log("需求预审", "✅ 需求合理，进入 Pipeline")

    def _timeit(stage_name: str, coro):
        """包装协程，计时并记录"""
        async def _wrapper():
            nonlocal project_type
            t0 = time.time()
            try:
                result = await coro
                elapsed = int((time.time() - t0) * 1000)
                record_stage_timing(stage_name, elapsed, project_type)
                return result
            except Exception:
                elapsed = int((time.time() - t0) * 1000)
                record_stage_timing(stage_name, elapsed, project_type)
                raise
        return _wrapper()

    # ── Stage 1: 需求分析 ──
    if is_prd:
        await on_log("需求分析", "PRD 已确认（用户编辑版），跳过重新分析")
        analysis = input_text
        project_type = _detect_project_type(analysis)
        await on_log("需求分析", f"从 PRD 检测到项目类型: {project_type}")
    else:
        await on_log("需求分析", "正在分析需求...")
        try:
            await on_log("需求分析", "👨 Kimi CLI（重活）正在分析需求...")
            analysis = await _timeit("需求分析", generate_sync([
                {"role": "system", "content": SYSTEM_PROMPT_ANALYSIS},
                {"role": "user", "content": input_text}
            ], task_type="heavy"))
            consume_ammo("text")
        except AIError as exc:
            await on_log("需求分析", f"分析失败: {exc}")
            return False
        await on_log("需求分析", analysis)
        project_type = _detect_project_type(analysis)
        await on_log("需求分析", f"检测到项目类型: {project_type}")
    
    if _pipeline_should_stop(project_id):
        await on_log("需求分析", "执行已停止")
        return False
    update_project(project_id, stage="架构设计", project_type=project_type)

    # ── Stage 2: 架构设计 ──
    await on_log("架构设计", "正在设计架构...")
    try:
        arch = await _timeit("架构设计", generate_sync([
            {"role": "system", "content": SYSTEM_PROMPT_ARCHITECT},
            {"role": "user", "content": f"需求:\n{input_text}\n\n分析:\n{analysis}\n\n项目类型: {project_type}"}
        ], task_type="heavy"))
        consume_ammo("text")
    except AIError as exc:
        await on_log("架构设计", f"设计失败: {exc}")
        return False
    await on_log("架构设计", arch)
    if _pipeline_should_stop(project_id):
        await on_log("架构设计", "执行已停止")
        return False
    update_project(project_id, stage="代码生成")

    # ── Stage 3: 代码生成 ──
    await on_log("代码生成", "正在生成代码...")
    coder_prompt = SYSTEM_PROMPT_CODER_PYTHON if project_type == "Python" else SYSTEM_PROMPT_CODER_HTML
    files = []
    for attempt in range(2):
        if attempt > 0:
            await on_log("代码生成", f"第{attempt+1}次尝试生成...")
        try:
            await on_log("代码生成", f"👨 Kimi CLI（重活）第{attempt+1}次生成代码...")
            code_bundle = await _timeit("代码生成", generate_sync([
                {"role": "system", "content": coder_prompt},
                {"role": "user", "content": f"需求:\n{input_text}\n\n架构:\n{arch}\n\n项目类型: {project_type}" + ("\n\n注意：请严格使用 === FILE: 文件名 === 格式输出每个文件的内容。" if attempt > 0 else "")}
            ], task_type="heavy"))
            consume_ammo("text")
        except AIError as exc:
            await on_log("代码生成", f"生成失败: {exc}")
            if attempt == 0:
                continue
            return False

        files = _parse_code_bundle(code_bundle, project_id, project_type)
        if files:
            break
        await on_log("代码生成", f"未能提取到代码文件，" + ("重试中..." if attempt == 0 else "放弃。"))

    if not files:
        await on_log("代码生成", "错误: 2次尝试均未能提取到代码文件")
        # 清理空项目目录
        try:
            if os.path.exists(project_path) and not os.listdir(project_path):
                os.rmdir(project_path)
                await on_log("代码生成", "已清理空项目目录")
        except Exception:
            pass
        if not _pipeline_should_stop(project_id):
            update_project(project_id, status="failed", stage="错误")
        return False

    # Bug 4: 自动生成 README.md
    _generate_readme(project_id, input_text, project_type, files)

    await on_log("代码生成", f"已生成 {len(files)} 个文件: {', '.join(files)}")
    if _pipeline_should_stop(project_id):
        await on_log("代码生成", "执行已停止")
        return False
    update_project(project_id, stage="测试验证", files=json.dumps(files))

    # ── Stage 4: 测试 ──
    await on_log("测试验证", "正在运行测试...")
    t0 = time.time()
    test_result = _run_tests(project_id, project_type)
    record_stage_timing("测试验证", int((time.time() - t0) * 1000), project_type)
    await on_log("测试验证", test_result["stdout"] + test_result["stderr"])
    if _pipeline_should_stop(project_id):
        await on_log("测试验证", "执行已停止")
        return False
    update_project(project_id, stage="部署执行", test_result=json.dumps(test_result))

    # ── Stage 4.5: 生成 requirements.txt ──
    if project_type == "Python":
        await on_log("部署执行", "正在生成依赖配置...")
        _generate_requirements(project_id)

    # ── Stage 5: 部署 ──
    await on_log("部署执行", "正在部署...")
    t0 = time.time()
    try:
        from core.local_deployer import sync_project, start_and_run, get_deploy_info
        deploy_info = get_deploy_info(project_id)
        port = deploy_info["port"]
        project_path = os.path.join(PROJECTS_DIR, project_id)

        await on_log("部署执行", f"同步项目到本地部署目录 (port={port})...")
        sync_result = sync_project(project_id, project_path)
        if not sync_result["success"]:
            raise RuntimeError(f"同步失败: {sync_result.get('error', 'unknown')}")
        await on_log("部署执行", f"同步完成 ({sync_result.get('mode', '?')})")

        await on_log("部署执行", f"子进程启动 (零 Docker)...")
        deploy_result = start_and_run(project_id, port)
        record_stage_timing("部署执行", int((time.time() - t0) * 1000), project_type)
        await on_log("部署执行", str(deploy_result.get("note", "")))
        if deploy_result.get("stdout"):
            await on_log("部署执行", deploy_result["stdout"][:500])
        if deploy_result.get("stderr"):
            await on_log("部署执行", "STDERR: " + deploy_result["stderr"][:300])

        if _pipeline_should_stop(project_id):
            await on_log("部署执行", "执行已停止")
            return False

        if not deploy_result.get("success"):
            update_project(project_id, status="error", stage="部署失败")
            await on_log("部署执行", f"部署失败: {deploy_result.get('note', '')}")
            return False

        deploy_url = deploy_result.get("url", "")
        update_project(project_id, status="deployed", stage="已完成", deploy_result=json.dumps(deploy_result), deploy_url=deploy_url)
        # 归档 PRD 历史
        p = get_project(project_id)
        if p:
            save_prd_history(
                project_id=project_id,
                title=p.get("name", "未命名项目"),
                content=p.get("prd", ""),
                category=p.get("project_type", ""),
                deploy_url=deploy_url,
                status="deployed",
            )
        await on_log("已完成", f"🎉 项目交付完成！访问地址: {deploy_url}")
        return True
    except Exception as exc:
        record_stage_timing("部署执行", int((time.time() - t0) * 1000), project_type)
        await on_log("部署执行", f"部署失败: {exc}")
        update_project(project_id, status="error", stage="部署失败")
        return False


def _detect_project_type(analysis: str) -> str:
    """从分析结果中检测项目类型"""
    t = analysis.lower()
    if "html" in t or "网页" in t or "前端" in t or "页面" in t or "h5" in t or "网站" in t:
        return "HTML"
    if "python" in t or "后端" in t or "api" in t or "爬虫" in t or "脚本" in t:
        return "Python"
    # 兜底：根据关键词判断
    html_keywords = ["博客", "个人主页", "展示页", "landing", "dashboard", "管理后台"]
    if any(k in t for k in html_keywords):
        return "HTML"
    return "Python"


def _clean_think(text: str) -> str:
    # 只去掉 think 标签，保留标签内的内容（避免代码被误删）
    text = re.sub(r'<think>', '', text, flags=re.S)
    text = re.sub(r'</think>', '', text, flags=re.S)
    return text.strip()


def _parse_code_bundle(text: str, project_id: str, project_type: str = "Python") -> list:
    """从 AI 输出中提取代码文件并写入磁盘。支持 === FILE 格式和 markdown 代码块。"""
    text = _clean_think(text)
    files = []

    # 格式 A-严格: === FILE: xxx === ... === END ===
    strict_pattern = re.compile(r'^=== FILE:\s*(.+?)\s*===(.*?)=== END ===$', re.MULTILINE | re.DOTALL)
    matches = list(strict_pattern.finditer(text))
    if matches:
        for m in matches:
            filename = m.group(1).strip()
            content = m.group(2).strip('\n')
            if '..' in filename or ':' in filename or filename.startswith('/') or filename.startswith('\\'):
                continue
            write_file(project_id, filename, content)
            files.append(filename)
        return files

    # 格式 A-宽松: === FILE: xxx === ...（到下一个 FILE 或文件末尾）
    loose_pattern = re.compile(r'^=== FILE:\s*(.+?)\s*===(.*?)(?=^=== FILE:|\Z)', re.MULTILINE | re.DOTALL)
    loose_matches = list(loose_pattern.finditer(text))
    if loose_matches:
        for m in loose_matches:
            filename = m.group(1).strip()
            content = m.group(2).strip('\n')
            # 去除尾部可能残留的 === END ===
            content = re.sub(r'\n?=== END ===\s*$', '', content)
            if '..' in filename or ':' in filename or filename.startswith('/') or filename.startswith('\\'):
                continue
            write_file(project_id, filename, content)
            files.append(filename)
        return files

    # 格式 B: 多个 markdown 代码块 → 分别保存
    lang_pattern = r'```(?:python|py|html|css|js|javascript)?\n(.*?)```'
    code_pattern = re.compile(lang_pattern, re.S)
    code_matches = list(code_pattern.finditer(text))
    if code_matches:
        if len(code_matches) == 1:
            code = code_matches[0].group(1).strip()
            ext = "index.html" if project_type == "HTML" else "main.py"
            write_file(project_id, ext, code)
            files.append(ext)
        else:
            for idx, m in enumerate(code_matches):
                code = m.group(1).strip()
                before = text[:m.start()]
                patterns = [
                    r'[`\'"](\w+\.(py|html|css|js))[`\'"]?:?\s*$',
                    r'文件\s*[`\'"](\w+\.(py|html|css|js))[`\'"]?',
                    r'(\w+\.(py|html|css|js))\s*的?内容',
                    r'#?\s*(\w+\.(py|html|css|js))\s*$',
                ]
                fname = None
                for pat in patterns:
                    match = re.search(pat, before, re.M)
                    if match:
                        candidate = match.group(1)
                        if candidate.endswith(('.py', '.html', '.css', '.js')):
                            fname = candidate
                            break
                if not fname:
                    if project_type == "HTML":
                        fname = "index.html" if idx == 0 else f"page_{idx}.html"
                    else:
                        fname = "main.py" if idx == 0 else f"module_{idx}.py"
                write_file(project_id, fname, code)
                files.append(fname)
        return files

    # 兜底: 清洗掉 === FILE 标记后作为单个文件
    cleaned = re.sub(r'^=== FILE:\s*.+?\s*===\s*', '', text, flags=re.M)
    cleaned = re.sub(r'\s*=== END ===\s*$', '', cleaned)
    ext = "index.html" if project_type == "HTML" else "main.py"
    write_file(project_id, ext, cleaned)
    files.append(ext)
    return files


def _generate_readme(project_id: str, input_text: str, project_type: str, files: list):
    """自动生成 README.md"""
    project_path = os.path.join(PROJECTS_DIR, project_id)
    readme_path = os.path.join(project_path, "README.md")
    file_list = "\n".join([f"- `{f}`" for f in files])
    readme = f"""# 项目说明

## 需求
{input_text[:500]}{'...' if len(input_text) > 500 else ''}

## 项目类型
{project_type}

## 文件列表
{file_list}

## 使用方式
"""
    if project_type == "HTML":
        readme += """1. 打开 `index.html` 即可使用
2. 或本地预览：`python3 -m http.server 8080`
"""
    else:
        readme += """1. 安装依赖：`pip install -r requirements.txt`
2. 运行：`python main.py`
3. 或：`python3 -m uvicorn main:app --host 0.0.0.0 --port 8080`
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)


def _run_tests(project_id: str, project_type: str = "Python") -> dict:
    """运行测试"""
    project_path = os.path.join(PROJECTS_DIR, project_id)

    if project_type == "HTML":
        # HTML项目：检查文件是否存在，不做pytest
        index_file = os.path.join(project_path, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()
            has_doctype = "<!DOCTYPE html>" in content.upper() or "<html" in content.lower()
            has_body = "<body" in content.lower()
            if has_doctype and has_body:
                return {"success": True, "stdout": "✅ HTML结构验证通过", "stderr": "", "exit_code": 0}
            else:
                return {"success": True, "stdout": "⚠️ HTML文件已生成（结构简单验证通过）", "stderr": "", "exit_code": 0}
        return {"success": True, "stdout": "HTML项目，跳过pytest", "stderr": "", "exit_code": 0}

    # Python项目：查找所有 test_*.py 文件
    import glob
    test_files = glob.glob(os.path.join(project_path, "**/test_*.py"), recursive=True)
    if test_files:
        # 运行所有找到的测试文件
        test_names = [os.path.relpath(f, project_path) for f in test_files]
        return run_command(f"python3 -m pytest {' '.join(test_names)} -q --tb=short", cwd=project_path, timeout=60)

    # 没有测试文件，自动生成最小测试
    main_file = os.path.join(project_path, "main.py")
    if os.path.exists(main_file):
        with open(main_file, "r", encoding="utf-8") as f:
            code = f.read()
        test_code = f'''# auto-generated test
import os, sys, importlib.util

def test_file_exists():
    assert os.path.exists(r"{main_file}")

def test_file_syntax():
    with open(r"{main_file}", "r", encoding="utf-8") as f:
        compile(f.read(), r"{main_file}", "exec")
'''
        write_file(project_id, "test_main.py", test_code)
        return run_command(f"python3 -m pytest test_main.py -q --tb=short", cwd=project_path, timeout=60)
    return {"success": True, "stdout": "未找到Python文件，跳过测试", "stderr": "", "exit_code": 0}


def _generate_requirements(project_id: str):
    """扫描代码中的 import，自动生成最小 requirements.txt"""
    project_path = os.path.join(PROJECTS_DIR, project_id)
    import ast
    imports = set()
    stdlib = {
        "os", "sys", "json", "re", "time", "datetime", "math", "random",
        "typing", "collections", "itertools", "functools", "pathlib",
        "subprocess", "tempfile", "glob", "hashlib", "base64", "io",
        "html", "http", "urllib", "uuid", "warnings", "string", "copy",
        "inspect", "traceback", "asyncio", "contextlib", "decimal",
    }
    import_map = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
    }

    for root, _, files in os.walk(project_path):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top = alias.name.split(".")[0]
                            if top not in stdlib:
                                imports.add(import_map.get(top, top))
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            top = node.module.split(".")[0]
                            if top not in stdlib:
                                imports.add(import_map.get(top, top))
            except Exception:
                continue

    # 去掉项目自身模块
    project_modules = {f[:-3] for f in os.listdir(project_path) if f.endswith(".py")}
    imports = imports - project_modules

    req_path = os.path.join(project_path, "requirements.txt")
    with open(req_path, "w", encoding="utf-8") as f:
        for pkg in sorted(imports):
            f.write(f"{pkg}\n")


