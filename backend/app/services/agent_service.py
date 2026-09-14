"""备战 Agent（P4）：把既有 AI 能力链编排成"一键备战"工作流。

设计立场（产品红线）：
  * 这是"有边界的 Agent"——它只**编排**既有任务（JD 解析 → 匹配 → Gap →
    准备计划 → 面试重点 → 简历建议），所有数字仍由程序计算；
  * 不新增任何自主决策，不改变任何工作区的交互；
  * 每一步的耗时/状态记录在返回的 trace 里（AI 网关指标同步累加）。

用途：用户选定目标岗位后，一次调用拿到完整备战包，替代在"求职准备"
工作区里手动点 3 次"生成"。幂等：重复调用即全量重算。
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.errors.exceptions import ValidationError_ as AppValidationError
from app.services import jd_service, match_service, prep_service


def build_battle_plan(db: Session, *, user_id: int, target_job_id: int) -> dict:
    """为指定目标岗位生成完整备战包，返回 {steps, plan}。"""
    steps: list[dict] = []

    def _step(name: str, fn):
        t0 = time.monotonic()
        data = fn()
        steps.append({"step": name, "ok": True, "ms": int((time.monotonic() - t0) * 1000)})
        return data

    # 1. 岗位存在性 + 详情（未确认的 JD 无法备战）
    tj = _step("target_job_detail", lambda: jd_service.get_target_job_detail(db, user_id=user_id, target_job_id=target_job_id))
    if tj["jd_status"] != "user_edited":
        raise AppValidationError(
            "目标岗位的 JD 还未确认，请先在「目标岗位」工作区完成解析与确认",
            code="jd_not_confirmed",
        )

    # 2. 匹配 + Gap（重算，保证与最新画像/JD 一致）
    match_payload = _step("match", lambda: match_service.run_match(db, user_id=user_id, target_job_id=target_job_id))

    # 3. 准备计划（F12）—— 已有计划会被覆盖重算（幂等全量重算语义）
    plan = _step("prep_plan", lambda: prep_service.generate_prep_plan(db, user_id=user_id, target_job_id=target_job_id))

    # 4. 面试重点（F14）
    focus = _step("interview_focus", lambda: prep_service.generate_interview_focus(db, user_id=user_id, target_job_id=target_job_id))

    # 5. 简历建议（F13）
    advice = _step("resume_advice", lambda: prep_service.generate_resume_advice(db, user_id=user_id, target_job_id=target_job_id))

    return {
        "target_job": {
            "target_job_id": target_job_id,
            "job_title": tj["job_title"],
            "company": tj["company"],
            "city": tj["city"],
        },
        "match": {
            "total_score": match_payload["match"]["total_score"],
            "ai_status": match_payload["match"]["ai_status"],
            "gap_count": len(match_payload["gaps"]),
            "strengths": match_payload["match"]["strengths"],
        },
        "prep_plan": plan,
        "interview_focus": focus,
        "resume_advice": advice,
        "steps": steps,
    }
