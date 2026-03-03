# tools/running_recommend.py
import sqlite3
from typing import Any, Dict, List, Optional

import httpx


WEATHER_API = "https://api.open-meteo.com/v1/forecast"

TOOL_DEF = {
    "name": "running_recommend",
    "description": (
        "날씨와 사용자 데이터를 종합해 러닝 코스를 추천합니다.\n"
        "- 기온 5도 이하: cold_suitable=1 코스 우선 + 페이스 보정 안내\n"
        "- 사용자 선호 거리(preferred_distance_km) 기반 추천\n"
        "- 최근 4주 평균 페이스(v_weekly_summary)와 목표 비교"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "예: 마포구 / 마포 / 강남 등. 미입력 시 user_profile preferred_area"},
            "lat": {"type": "number", "description": "날씨 조회용 위도(옵션)"},
            "lon": {"type": "number", "description": "날씨 조회용 경도(옵션)"},
        },
        "required": [],
    },
}


async def get_weather(lat: float, lon: float) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            WEATHER_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "forecast_days": 1,
            },
        )
        r.raise_for_status()
        j = r.json()
        return j["hourly"]


def _pick_course_recommendations(courses: List[Dict[str, Any]], preferred: List[float]) -> List[Dict[str, Any]]:
    # 선호 거리와 가까운 순으로 정렬 (단순 heuristic)
    if not preferred:
        return courses[:5]
    def dist_score(km: float) -> float:
        return min(abs(km - p) for p in preferred)
    return sorted(courses, key=lambda c: dist_score(float(c.get("distance_km") or 0.0)))[:5]


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


async def run(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    user = ctx["user"]
    location = args.get("location") or user.get("preferred_area") or "마포구"

    # 날씨 좌표 기본: 서울시청
    lat = float(args.get("lat", 37.5665))
    lon = float(args.get("lon", 126.9780))

    # 1) 날씨
    try:
        weather = await get_weather(lat, lon)
        temp = _safe_float(weather["temperature_2m"][0])
    except Exception as e:
        temp = None
        weather = {"error": f"weather_fetch_failed: {type(e).__name__}: {e}"}

    is_cold = (temp is not None and temp <= 5)

    # 2) 코스 조회
    courses: List[Dict[str, Any]] = []
    try:
        with sqlite3.connect(ctx["db"]) as conn:
            conn.row_factory = sqlite3.Row
            sql = """
            SELECT *
            FROM running_courses
            WHERE location LIKE ?
              AND (? = 0 OR cold_suitable = 1)
            ORDER BY distance_km
            """
            rows = conn.execute(sql, (f"%{location}%", int(is_cold))).fetchall()
            courses = [dict(r) for r in rows]
    except Exception as e:
        return {"error": f"course_query_failed: {type(e).__name__}: {e}"}

    # 3) 최근 4주 평균 페이스
    recent_pace = None
    try:
        with sqlite3.connect(ctx["db"]) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT AVG(avg_pace) AS recent_pace
                FROM (
                  SELECT avg_pace
                  FROM v_weekly_summary
                  ORDER BY week_start DESC
                  LIMIT 4
                )
                """
            ).fetchone()
            recent_pace = _safe_float(row["recent_pace"]) if row else None
    except Exception:
        recent_pace = None

    # 4) 추운 날 페이스 보정 (설계서: +0.25 min/km 예시)  [oai_citation:9‡running_mcp_design.pdf](sediment://file_000000005d8c720885b2f694777c4a90)
    suggested_pace = (recent_pace + 0.25) if (is_cold and recent_pace is not None) else recent_pace

    preferred = user.get("preferred_distance_km") or []
    rec_courses = _pick_course_recommendations(courses, preferred)

    cold_tips = (
        ctx["concepts"]
        .get("cold_weather_running", {})
        .get("recommendation", [])
    )

    return {
        "input": {"location": location, "lat": lat, "lon": lon},
        "weather": {"temp_c": temp, "is_cold": is_cold, "raw": weather},
        "recent_pace_min_km": recent_pace,
        "suggested_pace_min_km": suggested_pace,
        "courses": rec_courses,
        "cold_tips": cold_tips if is_cold else [],
        "user_context": {
            "running_goal": user.get("running_goal"),
            "target_pace_min_km": user.get("target_pace_min_km"),
            "preferred_distance_km": preferred,
        },
    }