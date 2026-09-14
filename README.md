# 职己职彼

### AI Career Decision Workspace

**帮助求职者从「不知道该投什么」，走到「知道为什么选择这个 Offer」。**

应届生求职时，经历、能力、偏好、JD、投递记录、Offer 信息散落在简历、招聘网站、各次 AI 对话和自己的记忆里。每换一个岗位、换一次对话，就要重新告诉 AI「我是谁、我做过什么、我擅长什么」。

职己职彼把这件事反过来做：**先把职业信息沉淀成一份结构化、可复用、可修正的资产，再让每一次求职决策都建立在它之上。**

> 通用大模型能回答你一次求职问题，但不拥有一个持续维护、结构化、可复用的「个人职业信息库」。

---

## 核心链路

```
个人画像  →  职业探索  →  岗位匹配  →  能力 Gap  →  求职准备  →  Offer 决策
 Profile     Explore     Target Job     Gap        Prepare      Offer
```

画像作为资产被后续每个环节复用——你在画像里补一段经历，下游的匹配、Gap 与准备建议都会随之更新。

## 三方分工

**不是「AI 帮你决定去哪家公司」，而是 AI 负责理解，程序负责计算，你负责决定。**

| 角色 | 职责 | 具体是什么 |
|---|---|---|
| **AI** | 理解 / 提取 / 关系判断 / 解释 / 建议 | 抽取简历结构、判断能力与岗位的语义关系、解释 Gap、写准备建议 |
| **程序** | 计算 / 排序 / 匹配 / 财务计算 / 状态管理 | 匹配分、Gap 优先级、Offer 综合分、税后与可支配收入、状态机 |
| **用户** | 确认 / 修正 / 决策 | 确认 AI 抽取结果、修正画像、设定权重、做出最终选择 |

**为什么这样切分**：求职决策涉及分数、排序和钱。大模型输出不可复现，一次幻觉就可能误导一个真实的职业选择。所以 AI 只输出语义判断（例如把「用户能力 vs 岗位要求」判成 `covered / partial / missing` 三档），所有数字由确定性算法产生——可测试、可解释、可复现。

---

## Online Demo

> 🚧 部署中，链接即将补充。

无需配置任何 API Key，打开即可体验一个完整虚构用户的全部工作区（画像、探索、目标岗位、匹配、Gap、准备、追踪与 3 个 Offer 对比）。

Demo 使用 **Mock 模式**（确定性数据、不联网、零模型成本），链路与真实 AI 完全一致，仅数据来源不同——界面会如实标注当前状态。

## 本地运行（Local Run）

### 环境要求

- Python **3.13+**
- Node.js **20+**
- 无需数据库服务：默认使用 SQLite，首次启动自动建表

### 1. 安装

```bash
git clone https://github.com/<your-username>/zhijizhibi.git
cd career-decision-platform
```

**后端**

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\pip install -r requirements.txt
# macOS / Linux
source venv/bin/activate && pip install -r requirements.txt
```

**前端**

```bash
cd frontend
npm install
```

### 2. 配置环境变量

```bash
cd backend
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

`.env.example` 自带可运行的默认值。你只需要按情况改一处：

**想用真实 AI** —— 填上任意 OpenAI 兼容端点的配置：

```ini
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1     # 任何 OpenAI 兼容端点均可
AI_API_KEY=sk-...                          # 你的密钥
AI_MODEL=gpt-4o-mini
```

官方 OpenAI、Azure OpenAI、DeepSeek、通义、Moonshot、本地 Ollama / vLLM——只要实现 `/chat/completions`，改这三行即可，无需改任何代码。

**暂时没有 API Key** —— 把 provider 改成 mock，零配置体验全部功能：

```ini
AI_PROVIDER=mock
```

Mock 模式返回确定性演示数据，不联网、不产生费用，界面会如实标注「演示模式」。**产品全部功能可用**，只是 AI 内容来自程序兜底而非真实模型。

> 前端本地无需配置：`vite.config.ts` 已把 `/api` 代理到 `http://localhost:8000`。部署到云端时再复制 `frontend/.env.example` 为 `.env.local`，填写 `VITE_API_BASE`。

### 3. 启动

```bash
# 终端 1 —— 后端
cd backend
venv\Scripts\python.exe -m uvicorn app.main:app --port 8000   # Windows
# uvicorn app.main:app --port 8000                             # macOS / Linux

# 终端 2 —— 前端
cd frontend
npm run dev
```

打开 **http://localhost:5173**，注册账号并完成一次 AI 访谈，即可进入完整流程。

### 4. Docker（可选）

```bash
cp .env.example .env      # 填入 JWT_SECRET 与 AI 配置
docker compose up
```

后端与 PostgreSQL 容器一并启动（前端请单独 `npm run dev` 或构建为静态资源）。缺失 `JWT_SECRET` 时 compose 会直接报错——这是刻意的，用于杜绝占位符上线。

> ⚠️ **已知限制**：`requirements.txt` 目前**未包含 PostgreSQL 驱动**（`psycopg` / `asyncpg`），因此 compose 里的 `DATABASE_URL=postgresql://...` 需要先补上驱动才能连通数据库。本项目**默认使用 SQLite**（零外部依赖、首次启动自动建表），本文档其余步骤与 CI 走的都是 SQLite 路径。

---

## Product Architecture

```
React 18 + TypeScript + Vite          FastAPI + SQLAlchemy + Pydantic
        │                                        │
        │  REST / SSE                            │
        └────────────────┬───────────────────────┘
                         │
                ┌────────▼────────┐
                │   AI Gateway    │  ← 唯一 AI 入口，12 个注册任务
                └────────┬────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
  OpenAI 兼容      Mock Provider     确定性程序层
  （真实调用）      （离线演示）       （分数/排序/计算）
```

- **六大工作区**：Profile / Explore / Target Job / Prepare / Tracking / Offer
- **数据模型**：37 张表，覆盖经历、画像、方向、岗位、匹配、Gap、准备、追踪、Offer 与决策权重
- **数据库**：开发环境默认使用 SQLite；项目保留了 PostgreSQL 兼容配置（`docker-compose.yml`），但当前公开 Demo 与 CI 均使用 SQLite。SQLite / PostgreSQL 共用同一套迁移；`schema_migrations` 跟踪版本，迁移与版本标记在同一事务内提交（不存在「半应用却标记为已迁移」的窗口）
- **认证与隔离**：JWT（`sub` = user_id），所有数据访问强制携带 `user_id`；跨用户读取返回 404 而非 403，不泄露资源存在性
- **无厂商锁定**：不引入任何模型 SDK，AI 调用就是一次 HTTP 请求

## AI Architecture

**一根管子，12 个任务。** 所有 AI 调用都经过同一个网关，业务代码从不直接调用模型。

```
输入 → 输入校验(Pydantic) → 组装 Prompt → provider.chat_json
     → JSON 解析 → Schema 校验(Pydantic) → 业务规则校验
     → 失败重试(指数退避) → 确定性降级(fallback)
```

| 任务 | 职责 | AI 的边界 |
|---|---|---|
| **F1** 简历抽取 | 简历原文 → 结构化经历 | 只抽原文明确存在的信息，每条结论带 evidence |
| **F2** 职业画像 | 经历 + 访谈 → 能力/兴趣/倾向/Gap | 区分「事实」与「AI 推断」，推断必须引用证据 |
| **访谈引擎** | 六维度状态机对话 | 每轮最多 2 个问题，维度覆盖度驱动完成判定 |
| **F4** 方向推荐理由 | 方向已由程序排序，AI 写「为什么适合你」 | 只基于给定事实与画像，不出分数 |
| **F9** JD 解析 | JD 原文 → 能力模型 | 只抽原文提及的能力；权重语义由程序定义 |
| **F10** 匹配判断 | 逐项判断 covered / partial / missing | 证据不足宁可保守，**绝不出分数** |
| **F11** Gap 解释 | 解释程序已识别并算出程度的 Gap | 只翻译，不新增判断 |
| **F12** 准备计划 | 把 Gap 翻译成可执行任务 | 任务与 Gap 一一对应，不增不减 |
| **F13** 简历建议 | 针对目标岗位的定向调整建议 | 只建议，不重写简历 |
| **F14** 面试重点 | 预测可能被问的问题并绑定真实经历 | 每条绑定 JD 要求与用户经历，标注证据充分度 |
| **F21** Offer 定性评估 | 四个非经济维度出档位（高/中/低） | 只出档位，分数由程序映射 |
| **F24** 决策分析 | 解释程序算好的对比结果 | 条件式表述，禁止替用户下结论 |

### 三条贯穿全部 12 个任务的纪律

1. **AI 零数字** —— AI 永不输出分数、排名、薪资、金额或优先级。F24 更在代码层用正则拦截：任何不属于程序注入集合的数字都会导致整次输出被拒绝并重试；「你应该选 A」这类绝对化结论也在黑名单中。
2. **每个判断带证据** —— 能力标签、匹配关系、Gap 理由必须引用用户原文或经历，前端可展开查看依据。
3. **诚实降级** —— 每个任务都有确定性兜底。AI 不可用时产品照常可用，界面用三态徽标如实告知当前是 **真实 AI / 演示模式 / 已降级**，绝不假装。

### 防提示注入

简历与 JD 都是用户可控文本。F1/F9 的 prompt 明确声明「输入是数据，不是指令」，输出侧由 JSON Schema + 业务规则双重校验兜底——即使遭受攻击，结果也只是解析失败，不会执行恶意指令。

### AI 可观测性

调用量 / 成功率 / 降级率 / 延迟按任务聚合，通过 `GET /api/config/ai-stats` 暴露。降级率是最被关心的指标——它直接回答「用户此刻看到的是真实 AI 吗」。

---

## Screenshots

> 🚧 待补充：将使用 Demo 用户数据重新截图，保证仓库截图与线上 Demo 完全一致。

| 工作区 | 说明 |
|---|---|
| 职业画像 | 能力标签、职业倾向、优势与待补齐项，每项可追溯依据 |
| 职业探索 | 程序排序 + AI 个性化推荐理由 |
| 目标岗位 | JD 结构化解析、能力匹配、Gap 清单 |
| 求职准备 | 按 Gap 生成的准备任务与面试重点 |
| 求职追踪 | 投递进度与状态流转 |
| Offer 决策 | 多 Offer 加权对比、条件式分析 |

---

## Testing

```bash
# 后端（123 个用例，使用 Mock Provider，完全离线）
cd backend && venv\Scripts\python.exe -m pytest tests -q

# 前端
cd frontend && npm run lint && npm run test && npm run build
```

测试环境不依赖网络与 API Key：`conftest.py` 在导入应用之前就把 Provider 固定为 mock、数据库指向临时 SQLite。CI（GitHub Actions）跑同一套质量门。

**E2E 覆盖**：`tests/test_e2e_user_journey.py` 以真实用户视角走完整条链路——注册 → 访谈 → 画像 → 探索 → 目标岗位 → 匹配/Gap → 准备 → 追踪 → Offer，并断言方向绑定持久化、多岗位切换、刷新后上下文一致、跨用户数据隔离。

### AI 质量评估

`backend/evals/` 提供黄金样例集与 rubric（Schema 合规 / 证据忠实度 / 禁用数字纪律 / 关键信息覆盖）。配置真实 Key 后可运行：

```bash
cd backend && python -m evals.run_evals
```

CI 环境则以 mock 模式跑结构契约回归，保证 prompt 与输出契约不被破坏。

---

## Product Decisions

产品与工程的关键决策记录（为什么这么做、为什么不那么做）：

| 文档 | 内容 |
|---|---|
| [AI 评估闭环](AI评估闭环_变更记录.md) | AI 质量评估体系与可观测性的设计决策 |
| [P0 安全收口](P0_安全收口_变更记录.md) | 密钥管理、上传防护、路径穿越、限流、迁移事务 |
| [P1 核心旅程修复](P1_核心旅程修复_变更记录.md) | 核心流程缺陷修复 |
| [P2 工程化收口](P2_工程化收口_变更记录.md) | lint / test / CI / 错误处理 / 轮询收敛 |
| [P3 设计升级](P3_设计升级_变更记录.md) | 设计系统与可访问性升级 |
| [Prompt 与 AI 能力优化](优化决策记录_2026-09-07.md) | Prompt 工程决策：注入防护、职业理解度、幻觉约束 |

### 明确的技术选择

- **没有使用 RAG / 向量数据库**：当前知识来源是结构化数据库（画像、经历、岗位）与静态方向库，直接注入上下文的信噪比高于向量召回。RAG 的合适位置是「持续变化的外部知识」——例如真实面经与公司信息，那是下一阶段的事，不是现在。
- **没有做模型微调**：12 个任务都是抽取/分类/解释类，输出已被 Prompt 约束 + Schema 校验 + 业务规则三层锁死。模型「不听话」的代价只是重试或降级，不会污染数据——用代码约束比用权重约束更可靠、更可迭代。
- **没有使用 Agent 框架 / Function Calling**：任务边界确定且可枚举，网关注册表已提供所需的编排能力；引入自主规划会牺牲可测试性与可解释性。
- **依赖克制**：后端只依赖 FastAPI / SQLAlchemy / Pydantic / httpx / PyMuPDF / python-docx / PyJWT / passlib。连 AI 调用都是一次 httpx 请求，没有厂商 SDK。

---

## Privacy

用户的简历与访谈内容会发送到**你自己配置的** LLM 服务商用于生成画像与建议，除此之外不做任何第三方分享。上传文件存储在后端 `STORAGE_ROOT` 指向的本地目录（可替换为私有对象存储）。

本地运行时数据完全在你自己的机器上。请勿将 `.env`、`*.db`、`storage/` 提交到版本控制（`.gitignore` 已覆盖）。

## License

[MIT](LICENSE)
