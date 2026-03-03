# tools/health_query.py
import sqlite3
from typing import Any, Dict, List


TOOL_DEF = {
    "name": "health_query",
    "description": (
        "러닝 데이터를 SQL로 조회합니다.\n"
        "중요: 페이스는 반드시 v_running_pace 뷰(정지구간 제외)를 사용하세요.\n"
        "트렌드(좋아지고 있어?)는 v_weekly_summary의 주간 avg_pace 조회를 권장합니다."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "실행할 SQLite SELECT SQL"},
        },
        "required": ["sql"],
    },
}


def _is_readonly_sql(sql: str) -> bool:
    s = (sql or "").strip().lower()
    # 단일 statement + SELECT/CTE만 허용
    if ";" in s.strip().rstrip(";"):
        return False
    allowed_starts = ("select", "with")
    if not s.startswith(allowed_starts):
        return False
    blocked = ["insert", "update", "delete", "drop", "alter", "create", "attach", "pragma", "vacuum", "replace"]
    return not any(b in s for b in blocked)


async def run(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    sql = args["sql"]
    db = ctx["db"]
    user = ctx["user"]

    if not _is_readonly_sql(sql):
        return {
            "error": "Only read-only SELECT/CTE SQL is allowed.",
            "hint": "Use SELECT ... FROM v_running_pace / v_weekly_summary ...",
        }

    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
            data: List[Dict[str, Any]] = [dict(r) for r in rows]
    except Exception as e:
        return {"error": f"SQL execution failed: {type(e).__name__}: {e}"}

    return {
        "data": data,
        "context": {
            "user_target_pace": user.get("target_pace_min_km"),
            "user_goal": user.get("running_goal"),
            "weekly_target_km": user.get("weekly_target_km"),
            "preferred_distance_km": user.get("preferred_distance_km"),
            "row_count": len(data),
        },
    }