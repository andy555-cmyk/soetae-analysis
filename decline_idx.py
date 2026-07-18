"""국토교통부 쇠퇴진단 '지표값'(Idx) API — 등급(1~10)이 아니라 실제 측정값(%, 비율)을 제공.
DceDgnssGradeService(등급)의 형제 서비스. 시군구 조회(getIdxSigngu).
엔드포인트/오퍼레이션이 배포본마다 다를 수 있어 두 후보를 순차 시도하고,
실패 시 빈 dict 반환 -> app.py에서 등급기반 판정으로 안전 폴백.
해외 IP는 정부 API 차단이라 Cloudtype(서울)에서만 실동작 검증 가능."""
import time, requests, config

BASES = [
    "https://apis.data.go.kr/1611000/DceDgnssIdxService",
    "https://apis.data.go.kr/1613574/DceDgnssIdxService",
]

def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _body(session, base, idx_cd, signgu_cd, year, retries=2):
    for i in range(retries):
        try:
            r = session.get(f"{base}/getIdxSigngu", params={
                "serviceKey": config.SBIZ_SERVICE_KEY, "signguCd": signgu_cd,
                "idxCd": idx_cd, "year": year, "type": "json",
                "numOfRows": 3, "pageNo": 1}, timeout=15)
            j = r.json()
            return j.get("body") or (j.get("response", {}) or {}).get("body")
        except Exception:
            time.sleep(0.6 * (i + 1))
    return None

def sigungu_values(signgu_cd, year="2016", max_codes=40):
    """VALUE00001~40 지표를 돌며 실제 측정값 수집. [{name, value, unit}] 반환."""
    s = requests.Session()
    # 유효 엔드포인트 자동 판별: 첫 코드가 값을 주는 base 채택
    base_ok = None
    for base in BASES:
        b = _body(s, base, "VALUE00001", signgu_cd, year)
        if b and (b.get("idxMean") or b.get("gradeMean") or b.get("value") is not None):
            base_ok = base
            first = b
            break
    if not base_ok:
        return []
    out = []
    def _push(b):
        if not b:
            return
        name = b.get("idxMean") or b.get("gradeMean") or b.get("idxNm") or ""
        val = _num(b.get("value"))
        if name and val is not None:
            out.append({"name": str(name).replace(" 지표", "").replace(" 등급", ""),
                        "value": val, "unit": b.get("unit") or b.get("valueUnit") or ""})
    _push(first)
    for n in range(2, max_codes + 1):
        _push(_body(s, base_ok, f"VALUE{n:05d}", signgu_cd, year))
    return out

def find_value(values, *keys):
    """정부 표기 률/율 혼용 정규화 후 매칭."""
    def _norm(x):
        return (x or "").replace("률", "율")
    for k in keys:
        nk = _norm(k)
        for v in values:
            if nk in _norm(v.get("name")):
                return v.get("value"), v.get("name"), v.get("unit")
    return None, None, None
