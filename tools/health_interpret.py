# tools/health_interpret.py
from typing import Any, Dict, List


TOOL_DEF = {
    "name": "health_interpret",
    "description": (
        "사용자 질의에서 러닝/마라톤 도메인 개념을 파악합니다.\n"
        "- '페이스'는 정지구간 제외 계산(v_running_pace)\n"
        "- '유지시간'은 연속 구간 최댓값(개념에 sql_hint 제공)\n"
        "- '좋아지고 있어?/트렌드/추이'는 4주 이동평균 트렌드 분석을 유도합니다."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_query": {"type": "string", "description": "사용자 자연어 질문"},
        },
        "required": ["user_query"],
    },
}


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


async def run(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    query: str = args["user_query"]
    concepts: Dict[str, Any] = ctx["concepts"]

    qn = _normalize(query)

    matched: List[Dict[str, Any]] = []
    for key, concept in concepts.items():
        label = concept.get("label", key)
        aliases = concept.get("aliases") or [label]
        # 간단 substring 매칭 (설계서 수준). 필요하면 토큰화/퍼지매칭으로 확장 가능.
        if any(_normalize(alias) in qn for alias in aliases):
            matched.append(
                {
                    "key": key,
                    "label": label,
                    "db_view": concept.get("db_view"),
                    "db_column": concept.get("db_column"),
                    "sql_hint": concept.get("sql_hint", ""),
                    "calculation": concept.get("calculation", ""),
                    "interpretation": concept.get("interpretation", {}),
                    "edge_cases": concept.get("edge_cases", []),
                    "common_misuse": concept.get("common_misuse", ""),
                }
            )

    trend_markers = ["좋아지", "나빠지", "트렌드", "추이", "변화", "개선", "악화", "늘었", "줄었"]
    is_trend_query = any(m in qn for m in trend_markers)

    return {
        "matched_concepts": matched,
        "is_trend_query": is_trend_query,
        "user_baseline": ctx["user"],
    }