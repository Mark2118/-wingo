# WinGo V4 企业级产品需求文档

> 版本: 4.0.0  
> 日期: 2026-04-23  
> 状态: 待开发  
> 验收人: 客户（Mark2118）

---

## 1. 产品概述

### 1.1 产品名称
WinGo V4 — AI 代码内容工厂

### 1.2 一句话定位
**中小企业、小团队的私有化 AI 开发平台。数据不出公司，一句话生成业务系统，一键私有化部署。**

### 1.3 产品形态
- **不是**：面向个人的零代码玩具（避开秒悟/C端）
- **是**：面向中小企业/小团队的 B2B 私有化部署平台
- **核心能力**：对话式 AI 生成企业级业务系统 + 自动化营销 + 数据本地存储

### 1.4 对标产品
| 对标 | 学什么 | 不做什么 |
|------|--------|----------|
| ChatGPT Canvas | 左聊右看的分栏界面，实时协作 | 不做通用对话，聚焦开发 |
| 阿里秒悟 | 一句话启动，自动跑完全流程 | 不做公有云部署，专注私有化 |
| Lovable | 对话生成代码的流畅体验 | 不做海外模板，中文原生 |

---

## 2. 目标用户

### 2.1 核心用户画像

| 分层 | 描述 | 规模 | 付费能力 | 获客渠道 |
|------|------|------|----------|----------|
| **小团队** | 创业公司/工作室/小连锁 | 5-20人 | ¥3,000-10,000/年 | 行业社群/转介绍 |
| **中小企业** | 有IT需求的中小公司 | 20-100人 | ¥10,000-50,000/年 | 行业展会/招投标 |
| **大企业** | 数据敏感型机构 | 100+人 | ¥50,000-200,000/年 | 渠道商/定制销售 |

**核心特征：**
- 有数字化需求但没有完整技术团队
- 数据敏感，不能上公有云（餐饮客户数据、医疗病历、金融数据）
- 需要快速交付（1-3天 vs 传统外包1个月）
- 预算有限（比外包公司便宜70%）

### 2.2 用户痛点
1. 想做个小程序/网站/系统，但找不到靠谱外包
2. 外包报价高（3万+）、周期长（1个月+）
3. 数据敏感，不能上公有云
4. 没有技术团队，需求说不清楚
5. 需要自动化营销，但没有营销团队

---

## 3. 核心功能

### 3.1 功能架构图

```
┌─────────────────────────────────────────────────────────┐
│                      用户层                              │
│  落地页 → 定价 → 注册/登录 → 主应用 → 项目管理           │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                     应用层                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ 用户系统  │  │ 付费系统  │  │ 开发核心  │              │
│  │注册/登录  │  │套餐/订单  │  │对话/PRD  │              │
│  │JWT认证   │  │订阅管理   │  │Pipeline  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                     引擎层（从 taizi 搬运）              │
│  AI引擎 → Pipeline → Builder → Deployer → Previewer    │
└─────────────────────────────────────────────────────────┘
```

### 3.2 功能清单

#### P0 — 必须有（MVP）
- [ ] 用户注册/登录（邮箱+密码）
- [ ] JWT 认证体系
- [ ] 套餐展示页面（免费/专业/企业）
- [ ] 付费订阅系统（订单+订阅状态）
- [ ] 登录后才能进入主应用
- [ ] Canvas 分栏界面（左对话+右预览）
- [ ] 对话式需求输入
- [ ] SSE 流式 PRD 生成
- [ ] PRD 生成完自动启动 Pipeline
- [ ] WebSocket 实时进度推送
- [ ] 右侧 iframe 实时预览
- [ ] 项目历史列表

#### P1 — 重要
- [ ] 手机号注册/登录
- [ ] 密码找回
- [ ] 支付接入（微信/支付宝）
- [ ] 发票管理
- [ ] 管理后台（看用户/订单/收入）
- [ ] 项目下载 ZIP
- [ ] 项目文件浏览

#### P2 — 增值
- [ ] 团队协作（多成员）
- [ ] API 开放平台
- [ ] 自定义域名部署
- [ ] 营销自动化工作流（n8n 集成）

---

## 4. 用户旅程（验收标准）

### 4.1 新客户旅程

```
Step 1: 打开 https://wingo.icu
        → 看到产品介绍页
        → 看到三档定价卡片
        → 点击"开始试用"或"立即订阅"

Step 2: 注册账号
        → 输入邮箱 + 密码
        → 收到验证邮件（可选P0）
        → 注册成功自动登录

Step 3: 进入主应用
        → 看到 Canvas 界面（左空白对话区 + 右折叠预览区）
        → 底部输入框可用

Step 4: 输入需求
        → "做一个餐饮会员管理系统"
        → AI 在左侧实时生成 PRD（markdown 流式渲染）
        → PRD 生成完自动开始开发

Step 5: 实时开发
        → 左侧显示 Pipeline 进度（需求分析→架构设计→代码生成→测试验证→部署执行）
        → 代码生成阶段右侧预览面板自动滑出
        → iframe 实时渲染最新页面

Step 6: 部署完成
        → 左侧显示"✅ 部署完成"
        → 右侧预览显示最终效果
        → 项目自动保存到 sidebar 列表
        → 可下载/预览/重新编辑

Step 7: 付费升级（免费版触发限制时）
        → 达到 3 个项目限制
        → 弹出升级提示
        → 选择套餐 → 支付 → 立即解锁
```

### 4.2 老客户旅程

```
登录 → 看到历史项目列表 → 点击项目 → 加载聊天记录和预览 → 继续对话修改
```

---

## 5. 技术架构

### 5.1 技术栈
| 层 | 技术 |
|----|------|
| 后端 | FastAPI + Python 3.11 |
| 数据库 | PostgreSQL 15（企业级主数据库） |
| 前端 | 纯 HTML/CSS/JS（单页应用） |
| 实时通信 | SSE（PRD流式）+ WebSocket（Pipeline进度） |
| AI 引擎 | MiniMax / Kimi / Ollama（从 taizi 搬运） |
| 部署 | Uvicorn + 本地目录 |

### 5.2 目录结构

```
wingo/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── config.py         # 全局配置
│   ├── database.py       # 数据库连接（v4 新表）
│   ├── models/           # Pydantic 模型
│   ├── api/
│   │   ├── auth.py       # 注册/登录/JWT
│   │   ├── billing.py    # 套餐/订单/订阅
│   │   ├── chat.py       # 对话/流式PRD/自动Pipeline
│   │   ├── projects.py   # 项目管理
│   │   ├── preview.py    # 预览/文件服务
│   │   ├── health.py     # 健康检查
│   │   └── websocket.py  # Pipeline 实时推送
│   └── core/             # 从 taizi 搬运的核心引擎
│       ├── ai_engine.py
│       ├── pipeline.py
│       ├── db.py
│       ├── deployer.py
│       └── ...
├── static/
│   ├── index.html        # 主应用（Canvas 分栏）
│   ├── login.html        # 登录页
│   ├── register.html     # 注册页
│   ├── pricing.html      # 定价页
│   └── landing.html      # 产品落地页
├── projects/             # 生成的项目目录
├── memory/               # 记忆系统
├── docs/                 # PRD/文档
├── requirements.txt
└── main.py               # 启动入口
```

---

## 6. 数据库设计

### 6.1 企业/团队表 teams
```sql
CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- 企业/团队名称
    license_key TEXT UNIQUE,      -- License密钥（企业版）
    plan TEXT DEFAULT 'trial',    -- trial / team / enterprise
    max_members INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expired_at TIMESTAMP          -- 订阅到期时间
);
```

### 6.2 用户表 users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER REFERENCES teams(id),
    email TEXT UNIQUE NOT NULL,
    phone TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT,
    avatar TEXT,
    role TEXT DEFAULT 'member',   -- owner / admin / developer / viewer
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.2 订阅表 subscriptions
```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan TEXT NOT NULL,  -- free / pro / enterprise
    status TEXT DEFAULT 'active',  -- active / expired / cancelled
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expired_at TIMESTAMP,
    price REAL,
    order_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3 订单表 orders
```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending / paid / refunded / failed
    pay_method TEXT,
    pay_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.4 项目表 projects（继承 taizi 结构）
```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),  -- 新增：关联用户
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'created',
    stage TEXT DEFAULT '',
    requirement TEXT,
    prd TEXT,
    deploy_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.5 聊天记录表 chats（继承 taizi 结构）
```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. API 设计

### 7.1 认证 API
```
POST /api/auth/register    {team_name, email, password, name} → {team_id, user_id, token}
POST /api/auth/login       {email, password} → {token, user, team}
POST /api/auth/logout      Header: Authorization → {success}
GET  /api/auth/me          Header: Authorization → {user, team, members}

POST /api/team/members     {email, role} → {invite_link}  (owner/admin)
GET  /api/team/members     → [{member}]
DELETE /api/team/members/{id} → {success}  (owner/admin)
```

### 7.2 付费 API
```
GET  /api/billing/plans              → [{plan, price, features}]
POST /api/billing/subscribe          {plan, period} → {order_id, pay_url}
GET  /api/billing/subscription       → {plan, status, expired_at}
GET  /api/billing/orders             → [{order}]
POST /api/billing/webhook            {payment_callback} → {success}
```

### 7.3 开发核心 API（已有，需加权限控制）
```
POST /api/chat                       {text, project_id} → {project_id}
GET  /api/stream?project_id=&req=    → SSE 流式 PRD
WS   /ws/{project_id}                → Pipeline 进度
GET  /api/projects                   → [{project}]
POST /api/projects/{id}/preview      → {url}
GET  /preview/{id}                   → HTML 预览
```

---

## 8. 前端设计

### 8.1 页面清单

| 页面 | 路径 | 说明 |
|------|------|------|
| 产品落地页 | /landing.html | 产品介绍 + 定价卡片 + CTA |
| 登录页 | /login.html | 邮箱+密码，深色主题 |
| 注册页 | /register.html | 邮箱+密码+确认密码 |
| 定价页 | /pricing.html | 三档套餐对比 |
| 主应用 | /index.html | Canvas 分栏（需登录） |

### 8.2 主应用界面（Canvas 分栏）

```
┌──────────────────────────────────────────────────────┐
│  ⚡ WinGo        [项目名称]        👁 预览  🗑 新建  👤 用户 │
├──────────────────────────┬───────────────────────────┤
│                          │                           │
│   👤 做一个餐饮系统       │                           │
│                          │                           │
│   ⚡ 📝 正在生成PRD...   │      📱 实时预览          │
│   [markdown 实时渲染]     │      ┌─────────────┐     │
│                          │      │   iframe     │     │
│   🔥 确认并发射（自动）   │      │   渲染页面   │     │
│                          │      └─────────────┘     │
│   ⚡ 代码生成中...       │                           │
│   进度：需求→架构→代码→测试→部署 │                           │
│                          │                           │
│   ✅ 部署完成            │                           │
│   [预览按钮] [下载按钮]   │                           │
│                          │                           │
├──────────────────────────┴───────────────────────────┤
│  [输入需求...]                              [发送按钮] │
└──────────────────────────────────────────────────────┘
```

### 8.3 设计规范
- 深色主题：#0d0d0d 背景
- 强调色：#3b82f6（蓝色）
- 文字：#e5e5e5 主文字 / #888 次要文字
- 圆角：8-12px
- 字体：系统默认无衬线字体

---

## 9. 付费体系

### 9.1 套餐设计

| 功能 | 体验版 | 团队版 ¥5,000/年 | 企业版 ¥30,000/年 |
|------|--------|-------------------|-------------------|
| 团队人数 | 1人 | 最多10人 | 无限 |
| 项目数量 | 5个 | 无限 | 无限 |
| 并发任务 | 1 | 5 | 20 |
| 部署方式 | 本地预览 | 本地服务器部署 | 私有化集群部署 |
| 数据存储 | 本地 | 本地 | 本地+备份 |
| 角色权限 | ❌ | ✅（管理员/开发者/访客） | ✅（自定义角色） |
| 营销自动化 | ❌ | ✅ | ✅ |
| API 接入 | ❌ | ❌ | ✅ |
| 专属客服 | ❌ | ❌ | ✅ |

### 9.2 付费流程
```
企业客户咨询 → 需求沟通 → 报价方案 → 签订合同 → 对公转账 → 开通企业账号
                                                    ↓
小团队自助购买 → 选择团队版/企业版 → 在线支付 → 自动生成License → 激活部署
```

---

## 10. 权限控制

### 10.1 路由权限
| 路径 | 权限 |
|------|------|
| /landing.html | 公开 |
| /login.html /register.html /pricing.html | 公开 |
| /index.html /api/chat /api/stream /ws/* | 需登录 |
| /api/billing/* | 需登录 |
| 管理后台 | 需 admin |

### 10.2 功能权限
| 功能 | 免费 | 专业 | 企业 |
|------|------|------|------|
| 创建项目 | 3个/月 | 无限 | 无限 |
| 公网部署 | ❌ | ✅ | ✅ |
| 导出源码 | ❌ | ✅ | ✅ |

---

## 11. 验收标准

### 11.1 功能验收（客户视角）

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | 落地页 | 打开能看到产品介绍、B2B定位、企业案例、CTA |
| 2 | 企业注册 | 输入企业名称+管理员邮箱+密码能注册 |
| 3 | 团队登录 | 管理员/成员能登录，看到团队项目 |
| 4 | 角色权限 | 管理员能添加团队成员，分配开发者/访客角色 |
| 5 | 套餐展示 | 定价页三档清晰，突出私有化部署卖点 |
| 6 | 主应用访问 | 未登录访问 /index.html 自动跳登录页 |
| 7 | 对话输入 | 登录后输入需求，AI回复并生成PRD |
| 8 | PRD流式 | PRD边生成边显示，markdown正确渲染 |
| 9 | 自动Pipeline | PRD生成完自动开始开发，无需手动确认 |
| 10 | 实时预览 | 代码生成阶段右侧自动打开预览iframe |
| 11 | 部署完成 | Pipeline完成后显示成功，项目保存到团队列表 |
| 12 | 私有化部署 | 生成的系统能在本地服务器运行，数据不出公司 |

### 11.2 性能验收
- 页面加载 < 2s
- PRD生成首字响应 < 5s
- Pipeline全流程 < 10分钟（简单项目）

### 11.3 安全验收
- 密码 bcrypt 加密存储
- JWT Token 有效期 24h
- SQL 注入防护（参数化查询）
- 路径遍历防护

---

## 12. 开发计划

| 阶段 | 任务 | 工期 |
|------|------|------|
| **P0-1** | 数据库设计 + 用户表/订阅表/订单表 | 1h |
| **P0-2** | 认证API（注册/登录/JWT） | 2h |
| **P0-3** | 付费API（套餐/订单/订阅状态） | 2h |
| **P0-4** | 登录/注册/定价前端页面 | 3h |
| **P0-5** | 主应用整合（登录态 + 权限控制） | 2h |
| **P0-6** | 端到端测试 + Bug修复 | 2h |

**总计：约 12h，分 2-3 天完成。**

---

## 13. 附录

### 13.1 从 taizi 搬运的核心引擎
- `core/ai_engine.py` — AI 调用（generate_sync / stream_chat）
- `core/pipeline.py` — 流水线执行（run_pipeline）
- `core/db.py` — 数据库操作（兼容层）
- `core/deployer.py` — 本地部署
- `core/previewer.py` — 预览服务

### 13.2 废弃的旧功能
- 飞书确认发射流程（太卡，砍掉）
- 手动 PRD 编辑 textarea（改为对话气泡流式）
- 16 个 API 路由模块（精简为 7 个）
- 系统面板/架构面板/巡逻面板（非核心，P2 再说）

---

**PRD 完成。确认后按 P0-1 → P0-6 顺序开发。**
