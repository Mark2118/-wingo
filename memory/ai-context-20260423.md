# AI 助手上下文记忆 — 2026-04-23

## 当前任务状态
- 老系统 `/Users/wingosz/taizi` 已封存，作为资源库保留
- 新系统 `/Users/wingosz/wingo-new` 是唯一的活跃开发系统
- 新系统仓库：https://github.com/Mark2118/-wingo
- 新系统运行在端口 38889

## 重要教训（必读）
**用户提醒：之前 AI 犯了严重错误，把老系统 `/Users/wingosz/taizi` 当成新系统分析，浪费了大量时间。**

- **新系统永远是 `/Users/wingosz/wingo-new/`，端口 38889**
- **老系统 `/Users/wingosz/taizi` 只是资源库，已停用**
- 用户情绪：非常生气。不要再犯同样的错误。

## 系统架构
- WinGo V4 — AI 代码内容工厂
- B2B 私有化部署平台
- FastAPI + SQLite + 纯 HTML/CSS/JS 前端
- 企业级功能：用户/团队/付费订阅/JWT 认证

## 未完成工作
- P0 MVP 清单全部未验收
- 支付是模拟的（未接真实微信支付/支付宝）
- PRD 状态：待开发
- 需要端到端联调

## 技术栈
- Python 3.9 (系统自带)
- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- bcrypt + python-jose (JWT)
- httpx (SSE 流式)
- Ollama qwen2.5-coder:7b (本地 AI)

## 启动方式
```bash
cd /Users/wingosz/wingo-new
python3 -m uvicorn main:app --host 0.0.0.0 --port 38889
```

## 文件位置
- 入口：`/Users/wingosz/wingo-new/main.py`
- 应用：`/Users/wingosz/wingo-new/app/`
- 引擎：`/Users/wingosz/wingo-new/app/core/`（软链接到 core/）
- 前端：`/Users/wingosz/wingo-new/static/`
- 数据库：`/Users/wingosz/wingo-new/wingo_v4.db`
- 记忆：`/Users/wingosz/wingo-new/memory/`
