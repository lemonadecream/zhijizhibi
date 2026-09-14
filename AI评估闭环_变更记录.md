# AI 质量评估闭环 · 变更记录（P0-AI）

> 日期：2026-09-07 ｜ 定位：AI 代表作能力层的第一优先补强（评估闭环 + 可观测性）
> 验证：后端 **118 passed**（新增 7 个用例）；评测脚本端到端跑通并产出 `evals/report.md`

## 为什么是它（产品决策记录）

AI 链路的工程骨架（网关三件套/诚实降级/证据纪律）已经完整，但缺一章：**"AI 输出质量如何度量、改 prompt 后如何证明变好"**。这一章是 AI 产品经理面试必被追问的问题，也是后续所有 prompt 迭代的前提——先有考卷，再谈提分。

## 交付 1：网关可观测性

| 文件 | 内容 |
|---|---|
| `app/ai/metrics.py`（新增） | 进程内指标：每任务 total/ok/fallback/error 计数 + 平均/最大延迟 + 最近错误，线程安全，`snapshot()` 供未来管理端点使用 |
| `app/ai/gateway.py` | `run()` 三条退出路径（ok/fallback/error）全部埋点；每次调用输出结构化日志 `AI_CALL task=… status=… attempts=… latency_ms=…` |

产品含义：现在每个 AI 功能"调用多少次、降级率多高、平均多慢、最近一次为什么失败"都有数可查——成本和可靠性的对话从"感觉"变成"报表"。

## 交付 2：评估闭环

| 文件 | 内容 |
|---|---|
| `evals/golden_cases.json` | 黄金样例集：F1 简历抽取 / F9 JD 解析 / F10 匹配判断 × 6 用例（含**提示注入**与**信息稀疏防编造**两个对抗用例） |
| `evals/run_evals.py` | 评测执行器：跑批 → rubric 检查 → `report.md` → 退出码（低于阈值即失败，可接 CI） |
| `evals/README.md` | rubric 维度的产品解释 + 使用/扩展约定 |
| `tests/test_eval_golden.py` | CI 集成：mock provider 下跑同一套用例锁**管道契约**（路由/校验/枚举/不回显输入），不花钱 |

**rubric 五维度**（"一条好的 AI 输出"的验收标准）：run_ok 未降级 / coverage 关键信息抽到 / faithfulness 证据来自原文不编造 / discipline 解释字段禁数字 / enum_ok 枚举合法。

## 使用方式

```bash
# 真实模型质量评估（先在 backend/.env 配真实 AI_API_KEY，当前为待轮换占位符）
python -m evals.run_evals            # 全量，阈值 85%
python -m evals.run_evals --task f10_match_judge
# CI 契约回归（无需 key，已入 pytest）
venv\Scripts\python.exe -m pytest tests/test_eval_golden.py -q
```

**工作流约定**：改 prompt → 跑评测 → 分数降了就是回归，先修再合；发现新的坏输出 → 加一条黄金用例。

## 实现中修掉的坑（给下一个 agent）

1. dot-path 解析器：列表值必须展开（`len()` 才是"条数"语义），`[*]` 段需处理——首版两处都错导致检查空转。
2. mock provider 返回固定内容：CI 契约模式只锁 run_ok/enum/防回显类规则；coverage/faithfulness/discipline 留给真实模型离线评测。F10 的业务规则要求"每个能力都有判断"，黄金用例的能力名必须与 mock 的能力覆盖表对齐（需求分析/SQL/沟通协调/行业经验）。
3. F10 真实评估还能顺带验证 reason/evidence 无数字——这是"AI 只解释"纪律的自动化审计。

## 后续可选（P1-AI 候选）

- 指标 `snapshot()` 暴露为管理端点（如 `/api/admin/ai-stats`）+ 前端展示
- 评估维度扩展 LLM-as-judge（语气/有用性等主观维度）
- 真实 key 配好后跑一次基线，把基线分数写进 README 作为回归锚点
