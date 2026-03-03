# tools/health_report.py
import sqlite3
from typing import Any, Dict, List, Optional


TOOL_DEF = {
    "name": "health_report",
    "description": (
        "주간/월간 러닝 리포트를 생성합니다.\n"
        "- 기본: v_weekly_summary 기반 주간 요약\n"
        "- 선택: 최근 N주/최근 N개월 범위\n"
        "리포트는 Claude가 바로 문장화할 수 있도록 요약 통계를 포함합니다."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["weekly", "monthly"], "description": "리포트 단위"},
            "n": {"type": "integer", "minimum": 1, "maximum": 52, "default": 8, "description": "최근 n개 기간"},
        },
        "required": ["period"],
    },
}


def _fetch_weekly_summary(conn: sqlite3.Connection, n: int) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    sql = """
    SELECT week_start, session_count, total_km, avg_pace
    FROM v_weekly_summary
    ORDER BY week_start DESC
    LIMIT ?
    """
    rows = conn.execute(sql, (n,)).fetchall()
    return [dict(r) for r in rows]


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


async def run(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    period = args["period"]
    n = int(args.get("n", 8))
    db = ctx["db"]
    user = ctx["user"]

    with sqlite3.connect(db) as conn:
        if period == "weekly":
            try:
                series = _fetch_weekly_summary(conn, n)
            except Exception:
                # 폴백: running_sessions에서 직접 주별 집계 (v_weekly_summary가 없을 때)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT
                      DATE(session_date, 'weekday 1', '-7 days') AS week_start,
                      COUNT(*) AS session_count,
                      ROUND(SUM(distance_km), 2) AS total_km
                    FROM running_sessions
                    GROUP BY week_start
                    ORDER BY week_start DESC
                    LIMIT ?
                    """,
                    (n,),
                ).fetchall()
                series = [dict(r) for r in rows]

        else:  # monthly
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  STRFTIME('%Y-%m-01', session_date) AS month_start,
                  COUNT(*) AS session_count,
                  ROUND(SUM(distance_km), 2) AS total_km,
                  ROUND(AVG(p.pace_min_per_km), 2) AS avg_pace
                FROM running_sessions rs
                LEFT JOIN v_running_pace p ON p.session_id = rs.id
                GROUP BY month_start
                ORDER BY month_start DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
            series = [dict(r) for r in rows]

    # 간단 요약 통계
    total_km = sum(_safe_float(x.get("total_km")) or 0.0 for x in series)
    avg_paces = [_safe_float(x.get("avg_pace")) for x in series if _safe_float(x.get("avg_pace")) is not None]
    avg_pace_overall = (sum(avg_paces) / len(avg_paces)) if avg_paces else None

    return {
        "period": period,
        "series": series,
        "summary": {
            "total_km": round(total_km, 2),
            "avg_pace_overall": round(avg_pace_overall, 2) if avg_pace_overall is not None else None,
            "user_goal": user.get("running_goal"),
            "weekly_target_km": user.get("weekly_target_km"),
            "target_pace_min_km": user.get("target_pace_min_km"),
        },
    }