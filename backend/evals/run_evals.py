"""AI 质量评测脚本（P0-AI 评估闭环的执行器）。

用法：
    # 真实模型质量评估（需要 backend/.env 配置真实 AI_API_KEY）
    cd backend && python -m evals.run_evals

    # 只跑结构契约（mock provider，不花钱，用于 CI）
    cd backend && python -m evals.run_evals --threshold 1.0

输入：evals/golden_cases.json（黄金样例 + 可程序判定的验收标准）
输出：控制台报告 + evals/report.md + 退出码（通过率低于 --threshold 时为 1）

rubric 维度（每个用例）：
  * run_ok        —— 网关跑通且未降级（fallback 视为质量不达标）
  * coverage      —— 关键信息被抽到（any_item_contains / min_items）
  * faithfulness  —— 证据忠实于输入、无编造（evidence_substring_of_input /
                     no_invented_companies / forbid_item_contains / ability_names_from_input）
  * discipline    —— 解释性字段禁数字（no_numbers_in，"AI 只解释程序管数字"纪律）
  * enum_ok       —— 枚举字段合法（enum_in）

扩展方式：往 golden_cases.json 加用例即可，脚本无需改动；prompt 迭代后跑一遍，
分数下降即回归——这是"凭感觉改"变成"看分数改"的那一步。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))  # backend/ on sys.path

from app.ai.gateway import get_gateway  # noqa: E402
from app.errors.exceptions import AIGatewayError  # noqa: E402


def _resolve(data: dict, path: str) -> list:
    """极简 dot-path 取值：列表值自动展开，"*" 表示逐项展开。

    如 abilities[*].name / requirements.experience_years / judgements。
    """
    cur: list = [data]
    for part in path.split("."):
        nxt: list = []
        for item in cur:
            if part == "*":
                if isinstance(item, list):
                    nxt.extend(item)
                else:
                    nxt.append(item)
            elif isinstance(item, dict):
                v = item.get(part)
                if isinstance(v, list):
                    nxt.extend(v)  # 列表值直接展开，保证 len() 是"条数"语义
                else:
                    nxt.append(v)
            elif isinstance(item, list):
                nxt.extend(item)
        cur = [x for x in nxt if x is not None]
    return cur


def _strings_at(data: dict, path: str) -> list[str]:
    return [str(v) for v in _resolve(data, path)]


def check_case(case: dict, result_data: dict) -> tuple[bool, list[str]]:
    """对单个用例执行 rubric。返回 (是否全部通过, 失败原因列表)。"""
    failures: list[str] = []
    exp = case.get("expect", {})

    for m in exp.get("min_items", []):
        if len(_resolve(result_data, m["path"])) < m["count"]:
            failures.append(f"coverage: {m['path']} 期望 ≥{m['count']} 项")

    for m in exp.get("max_items", []):
        values = _resolve(result_data, m["path"])
        if m.get("absent_or_empty"):
            if any(str(v).strip() for v in values):
                failures.append(f"coverage: {m['path']} 应为空，实际有值 {values[:2]}")
        elif len(values) > m["count"]:
            failures.append(f"coverage: {m['path']} 期望 ≤{m['count']} 项")

    for m in exp.get("any_item_contains", []):
        strings = [s.lower() for s in _strings_at(result_data, m["path"])]
        any_of = [str(x).lower() for x in m["any_of"]]
        if not any(kw in s for s in strings for kw in any_of):
            failures.append(f"coverage: {m['path']} 未命中 {any_of}（实际 {strings[:4]}）")

    for m in exp.get("forbid_item_contains", []):
        strings = [s.lower() for s in _strings_at(result_data, m["path"])]
        for kw in m.get("forbidden", []):
            if any(kw.lower() in s for s in strings):
                failures.append(f"no_invention: {m['path']} 出现了输入之外的编造内容「{kw}」")

    ev_path = exp.get("evidence_substring_of_input")
    if ev_path:
        source = str(case["input"].get(exp.get("input_field", "raw_text"), ""))
        for ev in _strings_at(result_data, ev_path):
            probe = re.sub(r"[「」『』\"'…。,\s]", "", ev)[:18]
            if probe and probe not in re.sub(r"\s", "", source):
                failures.append(f"evidence: 证据「{ev[:30]}…」未在原文中出现")

    invented = exp.get("no_invented_companies")
    if invented:
        source = str(case["input"].get(invented.get("input_field", "raw_text"), ""))
        for c in _strings_at(result_data, invented["path"]):
            if c and c.rstrip("公司有限科技责任")[:4] not in source:
                failures.append(f"invention: 编造了输入中不存在的公司「{c}」")

    for path in exp.get("no_numbers_in", []):
        for s in _strings_at(result_data, path):
            if re.search(r"\d", s):
                failures.append(f"discipline: {path} 解释字段含数字「{s[:40]}」")

    for m in exp.get("enum_in", []):
        allowed = {str(v) for v in m["values"]}
        for v in _resolve(result_data, m["path"]):
            if str(v) not in allowed:
                failures.append(f"enum_ok: {m['path']}={v} 不在 {sorted(allowed)}")

    names_spec = exp.get("ability_names_from_input")
    if names_spec:
        allowed = {str(a.get("name", "")).lower() for a in case["input"].get(names_spec, {}).get("abilities", [])}
        for s in _strings_at(result_data, "judgements[*].ability"):
            if s.lower() not in allowed:
                failures.append(f"invention: 判断了输入能力模型之外的能力「{s}」")

    for path in exp.get("field_nonempty", []):
        if not any(s.strip() for s in _strings_at(result_data, path)):
            failures.append(f"discipline: {path} 应有内容但为空")

    return (len(failures) == 0, failures)


def run(threshold: float, only_task: str | None = None) -> int:
    cases = json.loads((HERE / "golden_cases.json").read_text(encoding="utf-8"))["cases"]
    if only_task:
        cases = [c for c in cases if c["task"] == only_task]
    gateway = get_gateway()

    lines = ["# AI 质量评测报告", "", f"用例数：{len(cases)} ｜ 阈值：{threshold:.0%}", ""]
    passed_total = 0
    per_task: dict[str, list[bool]] = {}

    for case in cases:
        t0 = time.monotonic()
        status, data, err = "error", {}, ""
        try:
            result = gateway.run(case["task"], case["input"])
            status, data = result.status, result.data
        except AIGatewayError as exc:
            err = str(exc)
        latency_ms = int((time.monotonic() - t0) * 1000)

        ok = False
        failures: list[str] = []
        if status == "fallback":
            failures.append(f"run_ok: 触发降级（{err or 'provider 不可用'}）")
        elif status == "error":
            failures.append(f"run_ok: 调用失败（{err}）")
        else:
            ok, failures = check_case(case, data)

        passed_total += ok
        per_task.setdefault(case["task"], []).append(ok)
        mark = "✅" if ok else "❌"
        lines.append(f"## {mark} {case['id']}（{case['task']}，{latency_ms}ms）")
        lines.append(f"- {case.get('note', '')}")
        if failures:
            lines.extend(f"- ⚠️ {f}" for f in failures)
        lines.append("")

    rate = passed_total / len(cases) if cases else 0.0
    lines.append("---")
    lines.append(f"**总通过率：{passed_total}/{len(cases)} = {rate:.0%}（阈值 {threshold:.0%}，{'通过' if rate >= threshold else '未通过'}）**")
    lines.append("")
    for task, results in per_task.items():
        p = sum(results)
        lines.append(f"- {task}: {p}/{len(results)}")

    report = "\n".join(lines)
    (HERE / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print("报告已写入 evals/report.md")
    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI 质量评测")
    parser.add_argument("--threshold", type=float, default=0.85, help="最低通过率（默认 0.85）")
    parser.add_argument("--task", type=str, default=None, help="只跑某个任务，如 f1_resume_parse")
    args = parser.parse_args()
    sys.exit(run(args.threshold, args.task))
