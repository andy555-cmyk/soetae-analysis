"""국토교통부 쇠퇴진단 '지표값'(Idx) API — 등급(1~10)이 아니라 실제 측정값(%, 비율)을 제공.
DceDgnssGradeService(등급)의 형제 서비스. 시군구 조회(getIdxSigngu).
엔드포인트가 배포본마다 다를 수 있어 두 후보를 순차 시도하고, 실패 시 빈 dict 반환 -> app.py에서 등급기반 판정으로 안전 폴백.
유효 base 확정 후 나머지 지표코드는 병렬(ThreadPool) 조회해 신규 시군구 첫 조회 지연 최소화."""
import requests, config
from concurrent.futures import ThreadPoolExecutor

BASES = [
    "https://apis.data.go.kr/1611000/DceDgnssIdxService",
    "https://apis.data.go.kr/1613574/DceDgnssIdxService",
]

def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _body(base, idx_cd, signgu_cd, year):
    """단일 지표코드 조회(재시도 없이 짧은 타임아웃). 실패 시 None."""
    try:
        r = requests.get(f"{base}/getIdxSigngu", params={
            "serviceKey": config.SBIZ_SERVICE_KEY, "signguCd": signgu_cd,
            "idxCd": idx_cd, "year": year, "type": "json",
            "numOfRows": 3, "pageNo": 1}, timeout=8)
        j = r.json()
        return j.get("body") or (j.get("response", {}) or {}).get("body")
    except Exception:
        return None

def _mk(b):
    if not b:
        return None
    name = b.get("idxMean") or b.get("gradeMean") or b.get("idxNm") or ""
    val = _num(b.get("value"))
    if name and val is not None:
        return {"name": str(name).replace(" 지표", "").replace(" 등급", ""),
                "value": val, "unit": b.get("unit") or b.get("valueUnit") or ""}
    return None

def sigungu_values(signgu_cd, year="2016", max_codes=40):
    """VALUE00001~40 실측값 수집. 첫 코드로 유효 base 판별 후 나머지 병렬 조회. [{name, value, unit}]."""
    base_ok = None; first = None
    for base in BASES:
        b = _body(base, "VALUE00001", signgu_cd, year)
        if b and (b.get("idxMean") or b.get("gradeMean") or b.get("value") is not None):
            base_ok = base; first = b; break
    if not base_ok:
        return []
    out = []
    r0 = _mk(first)
    if r0:
        out.append(r0)
    codes = [f"VALUE{n:05d}" for n in range(2, max_codes + 1)]
    with ThreadPoolExecutor(max_workers=10) as ex:
        bodies = list(ex.map(lambda c: _body(base_ok, c, signgu_cd, year), codes))
    for b in bodies:
        r = _mk(b)
        if r:
            out.append(r)
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
