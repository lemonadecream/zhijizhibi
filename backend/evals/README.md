# AI 质量评估集（Eval Harness）

这是"AI 代表作"的质量闭环：**改 prompt 之后跑一遍，分数说明变好还是变坏**。

## 组成

| 文件 | 作用 |
|---|---|
| `golden_cases.json` | 黄金样例：3 个核心任务（F1 简历抽取 / F9 JD 解析 / F10 匹配判断）共 6 个用例，每个用例带可程序判定的验收标准（rubric） |
| `run_evals.py` | 评测脚本：跑批 + rubric 检查 + 生成 `report.md` + 退出码 |
| `../tests/test_eval_golden.py` | CI 集成：mock provider 下跑同一套用例做结构契约回归（不花钱） |

## rubric 维度（PM 视角：这就是"什么是一条好的 AI 输出"的验收标准）

| 维度 | 产品含义 | 检查方式 |
|---|---|---|
| run_ok | 没有降级（AI 真的在工作） | 网关状态 |
| coverage | 该抽到的信息抽到了 | 关键词/数量断言 |
| faithfulness | 证据来自用户原文，没编造 | 证据子串回查输入 / 禁止编造公司 |
| discipline | 解释字段不出现数字（"AI 只解释、程序管数字"纪律） | 数字正则 |
| enum_ok | 枚举值合法（covered/partial/missing 等） | 白名单 |

## 怎么用

```bash
cd backend

# ① 真实模型质量评估（先在 .env 配好真实 AI_API_KEY）
python -m evals.run_evals                 # 全部用例，通过率阈值 85%
python -m evals.run_evals --task f10_match_judge   # 只跑某个任务
# 结果写进 evals/report.md；通过率低于阈值时退出码为 1（可接 CI）

# ② 结构契约回归（无需 API key，已在 pytest 中）
venv\Scripts\python.exe -m pytest tests/test_eval_golden.py -q
```

## 扩展约定

- **改 prompt → 跑一遍 → 看分数**：通过率下降就是回归，先修再合。
- **发现新的坏输出 → 加用例**：往 `golden_cases.json` 加一条（输入 + 期望），让同一个坑只踩一次。
- 用例的 `expect` 全部是程序可判定规则；未来若引入 LLM-as-judge（更主观的维度，如语气温暖度），在 rubric 里加维度即可，脚本结构不变。
