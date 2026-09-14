"""职己职彼 MCP Server（stdio，最小 JSON-RPC 实现，无第三方依赖）。

把产品的核心 AI 能力暴露为 MCP 标准工具，任何 MCP 客户端（Claude Desktop、
其他 Agent）都能接入。这是"能力出口"：产品内的画像/匹配/Gap 变成生态里
可被调用的工具。

协议子集（够用即可）：
  initialize                → 返回协议版本与能力
  notifications/initialized → 忽略
  tools/list                → 工具清单（name/description/inputSchema）
  tools/call                → 执行工具，返回 {content:[{type:"text",text}]}
  ping                      → pong

运行：
    cd backend && set AI_PROVIDER=mock && set JWT_SECRET=dev-secret
    venv\\Scripts\\python.exe mcp_server.py          # stdio，Ctrl+C 退出

工具清单（均按 user_id 隔离）：
  explore_directions   —— 罗盘：返回指定用户的推荐职业方向（名称/匹配依据/AI 理由）
  target_job_match     —— 返回指定用户某目标岗位的匹配分与能力关系
  prep_plan            —— 返回指定用户的求职准备计划（任务/进度）

注意：独立进程，读取同一 DATABASE_URL；指标与网关在本进程内独立计数。
"""
from __future__ import annotations

import json
import sys

SERVER_INFO = {"name": "zhiji-zhibi", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "explore_directions",
        "description": "获取用户基于职业画像推荐的职业方向（含匹配依据与 AI 推荐理由）",
        "inputSchema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer", "description": "职己职彼用户 ID"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "target_job_match",
        "description": "获取用户某目标岗位的匹配总分、能力覆盖关系与 Gap 列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "target_job_id": {"type": "integer"},
            },
            "required": ["user_id", "target_job_id"],
        },
    },
    {
        "name": "prep_plan",
        "description": "获取用户某目标岗位的求职准备计划（任务清单/优先级/完成进度）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "target_job_id": {"type": "integer"},
            },
            "required": ["user_id", "target_job_id"],
        },
    },
]


def _setup_app():
    """Import the FastAPI app package so DB/models/services are ready."""
    from app.db.base import SessionLocal  # noqa: F401
    from app.db.migrate import run_migrations  # noqa: F401

    return True


def _call_tool(name: str, args: dict) -> str:
    from app.db.base import SessionLocal
    from app.services import explore_service, match_service, prep_service

    user_id = int(args["user_id"])
    with SessionLocal() as db:
        if name == "explore_directions":
            recs = explore_service.compute_recommendations(db, user_id=user_id, with_reason=True)
            out = [
                {
                    "direction": r["name"],
                    "score": r["score"],
                    "match_basis": r["match_basis"],
                    "ai_reason": r.get("reason", ""),
                }
                for r in recs[:5]
            ]
        elif name == "target_job_match":
            payload = match_service.run_match(db, user_id=user_id, target_job_id=int(args["target_job_id"]))
            out = {
                "total_score": payload["match"]["total_score"],
                "ai_status": payload["match"]["ai_status"],
                "relations": [
                    {"ability": j["ability"], "relation": j["relation"]}
                    for j in payload["match"]["relation_judgements"]
                ],
                "gaps": [
                    {"ability": g["ability"], "priority": g["priority"], "why": g["why"]}
                    for g in payload["gaps"]
                ],
            }
        elif name == "prep_plan":
            home = prep_service.get_prep_home(db, user_id=user_id, target_job_id=int(args["target_job_id"]))
            out = {
                "target_job": home.get("target_job"),
                "progress": home.get("prep_plan", {}).get("overall_progress") if home.get("prep_plan") else None,
                "tasks": [
                    {"title": t["title"], "priority": t["priority"], "status": t["status"]}
                    for t in home.get("tasks", [])
                ],
            }
        else:
            out = {"error": f"unknown tool: {name}"}
    return json.dumps(out, ensure_ascii=False)


def _handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    mid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        try:
            text = _call_tool(params.get("name", ""), params.get("arguments", {}))
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
        except Exception as exc:  # noqa: BLE001 — MCP 错误也走 result.isError
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            }
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method: {method}"}}
    return None


def main() -> None:
    _setup_app()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        resp = _handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
