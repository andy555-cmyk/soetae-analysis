"""국토교통부 건축HUB 건축물대장 표제부 조회(getBrTitleInfo).
대상 지번의 사용승인일(노후연수)·주구조·주용도·층수·건폐율·용적률·연면적을 제공.
data.go.kr 계정 인증키(SBIZ_SERVICE_KEY) 공용 — 건축물대장 서비스 활용신청 승인 후 동작.
해외 IP는 정부 API 차단이라 Cloudtype(서울)에서만 실동작 검증 가능.
엔드포인트가 배포본마다 다를 수 있어 후보를 순차 시도하고 실패 시 None 반환(딥링크로 폴백)."""
import re, time, requests, config

BASES = [
    "https://apis.data.go.kr/1613000/BldRgstHubService",
    "https://apis.data.go.kr/1613000/BldRgstHubService_v2",
    "https://apis.data.go.kr/1613000/BldRgstService_v2",
]

def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _parse_bun_ji(address):
    """주소 끝의 지번(본번-부번) 추출. '산' 지번이면 platGbCd=1."""
    plat = "0"
    if not address:
        return None, None, plat
    a = address.strip()
    m = re.search(r"(산)?\s*(\d{1,4})(?:-(\d{1,4}))?\s*(?:번지)?\s*$", a)
    if not m:
        return None, None, plat
    if m.group(1) == "산":
        plat = "1"
    bun = m.group(2).zfill(4)
    ji = (m.group(3) or "0").zfill(4)
    return bun, ji, plat

def _pick(it):
    ap = str(it.get("useAprDay") or "").strip()
    year = int(ap[:4]) if len(ap) >= 4 and ap[:4].isdigit() else None
    return {
        "approved": ap,
        "approved_year": year,
        "structure": (it.get("strctCdNm") or "").strip(),
        "purpose": (it.get("mainPurpsCdNm") or "").strip(),
        "floors_up": _num(it.get("grndFlrCnt")),
        "floors_down": _num(it.get("ugrndFlrCnt")),
        "bc_rat": _num(it.get("bcRat")),
        "vl_rat": _num(it.get("vlRat")),
        "tot_area": _num(it.get("totArea")),
        "arch_area": _num(it.get("archArea")),
        "households": _num(it.get("hhldCnt")),
        "name": (it.get("bldNm") or "").strip(),
        "kind": (it.get("regstrKindCdNm") or "").strip(),
    }

def title_info(ldong_cd, address):
    """법정동코드(10자리)+주소 → 표제부 대표 1건 dict, 실패 시 None."""
    if not ldong_cd or len(str(ldong_cd)) < 10 or not config.SBIZ_SERVICE_KEY:
        return None
    lc = str(ldong_cd)
    sigungu, bjdong = lc[:5], lc[5:10]
    bun, ji, plat = _parse_bun_ji(address)
    if not bun:
        return None
    params = {"serviceKey": config.SBIZ_SERVICE_KEY, "sigunguCd": sigungu, "bjdongCd": bjdong,
              "platGbCd": plat, "bun": bun, "ji": ji, "numOfRows": 30, "pageNo": 1, "_type": "json"}
    s = requests.Session()
    for base in BASES:
        for i in range(2):
            try:
                r = s.get(f"{base}/getBrTitleInfo", params=params, timeout=15)
                j = r.json()
                body = ((j.get("response") or {}).get("body") or {})
                items = body.get("items") or {}
                item = items.get("item") if isinstance(items, dict) else None
                if isinstance(item, list):
                    # 대표 동: 연면적 최대 동을 대표로
                    item = max(item, key=lambda x: _num(x.get("totArea")) or 0) if item else None
                if item:
                    return _pick(item)
                break  # 정상 응답이나 항목 없음 → 다음 base 불필요
            except Exception:
                time.sleep(0.5 * (i + 1))
    return None
