"""상가(상권)정보 반경검색 - 소상공인시장진흥공단 (data.go.kr B553077).
현재 유효 엔드포인트: sdsc2 (구버전 sdsc 는 폐기됨 - 2026.07 확인).
클라우드 환경 안정화를 위해 HTTPS + 재시도 적용."""
import time, requests, collections, config

BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius"

def _get_json(params, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(BASE, params=params, timeout=30)
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise last

def stores_in_radius(lon: float, lat: float, radius_m: int = 500):
    if not config.SBIZ_SERVICE_KEY:
        return None  # 키 없음 -> mock
    rows, page = [], 1
    while True:
        d = _get_json({
            "serviceKey": config.SBIZ_SERVICE_KEY, "radius": radius_m,
            "cx": lon, "cy": lat, "type": "json",
            "pageNo": page, "numOfRows": 1000,
        })
        body = d.get("body", {}) if isinstance(d, dict) else {}
        items = (body.get("items") or [])
        rows.extend(items)
        total = int(body.get("totalCount", 0) or 0)
        if page * 1000 >= total or not items:
            break
        page += 1
    return rows

def summarize(rows):
    """업종 구성/밀도 요약. 빈점포는 이 API에 없음 -> 업종분포로 상권 활력 간접 추정."""
    by_major = collections.Counter(x.get("indsLclsNm", "미분류") for x in rows)
    return {"total_stores": len(rows), "by_major_category": dict(by_major.most_common()),
            "note": "빈 점포/공실은 본 API에 없음. 시점별 상가 수 비교 또는 소상공인365 폐업률로 보완 필요."}
