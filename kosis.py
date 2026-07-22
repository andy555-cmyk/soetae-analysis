"""KOSIS(통계청 국가통계포털) 공유서비스 API 연동.
시군구별 연도별 실측 시계열(인구/사업체 등)을 조회해 그래프용 데이터로 반환한다.
- 인구: 주민등록인구 DT_1B040A3(orgId 101), itmId=T20(총인구수), objL1=시군구코드, prdSe=Y
- KOSIS 시군구 코드는 우리 앱의 법정동 앞5자리(_signgu_from_geo)와 일치(예: 기장군 26710).
KOSIS API는 해외/컨테이너에서도 접속 가능(data.go.kr과 달리)."""
import os, json
import urllib.request, urllib.parse

KOSIS_KEY = os.environ.get("KOSIS_KEY", "")
_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
_TIMEOUT = 8
_CACHE = {}   # (kind, code) -> series list


def _get(params):
    q = urllib.parse.urlencode(params)
    url = _BASE + "?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        raw = r.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if isinstance(data, dict):  # {"err":..,"errMsg":..}
        return None
    return data


def _series(kind, org, tbl, itm, code, sy, ey):
    """단일 시군구·연도구간 시계열 → [{"year":int,"value":float}] (연도 오름차순)."""
    ck = (kind, code, sy, ey)
    if ck in _CACHE:
        return _CACHE[ck]
    if not KOSIS_KEY or not code:
        return []
    params = {
        "method": "getList", "apiKey": KOSIS_KEY,
        "orgId": org, "tblId": tbl, "itmId": itm, "objL1": code,
        "prdSe": "Y", "startPrdDe": str(sy), "endPrdDe": str(ey),
        "format": "json", "jsonVD": "Y",
    }
    try:
        rows = _get(params)
    except Exception:
        rows = None
    out = []
    if rows:
        for r in rows:
            try:
                y = int(str(r.get("PRD_DE"))[:4])
                v = float(r.get("DT"))
                out.append({"year": y, "value": v})
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda x: x["year"])
    # 중복 연도 제거(마지막 값 유지)
    dedup = {}
    for p in out:
        dedup[p["year"]] = p["value"]
    out = [{"year": y, "value": dedup[y]} for y in sorted(dedup)]
    _CACHE[ck] = out
    return out


def population_series(sigungu_code, start_year=2014, end_year=2023):
    """시군구 총인구수(주민등록) 연도별 실측 시계열."""
    code = str(sigungu_code)[:5] if sigungu_code else None
    return _series("pop", "101", "DT_1B040A3", "T20", code, start_year, end_year)


def trends(sigungu_code, start_year=2014, end_year=2023):
    """대상 시군구의 그래프용 시계열 묶음. 확보된 지표만 채운다."""
    pop = population_series(sigungu_code, start_year, end_year)
    return {
        "population": pop,
        "business": [],      # 전국사업체조사(시도 분리) 연동 예정
        "old_building": [],  # 노후주택/건축물 연동 예정
    }
