# context/analysis_guidelines.py

GUIDELINES = {
    "pace": [
        "페이스는 v_running_pace의 pace_min_per_km를 사용한다(정지구간 제외).",
        "트렌드는 최소 4주 이동평균/주간 avg_pace 흐름으로 해석한다.",
    ],
    "cold_weather": [
        "기온 5도 이하에서는 페이스가 10~15% 느려지는 것이 정상이다.",
        "워밍업 5분 이상 권장, 바람 막힌 코스/실내 우선.",
    ],
}