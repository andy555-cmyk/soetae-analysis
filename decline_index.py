"""쇠퇴진단지표 조회 + 국가기준 판정.
도시재생 개방데이터(쇠퇴진단지표 CSV)를 행정구역으로 필터.
CSV 컬럼명은 배포본마다 다를 수 있어 유연 매핑."""
import csv, os, config

# CSV 컬럼 후보명 (배포본에 맞게 자동 매핑)
COLS = {
    "sigungu": ["시군구", "시군구명", "SIGUNGU_NM", "sggnm"],
    "emd": ["읍면동", "읍면동명", "EMD_NM", "emdnm"],
    "pop_drop": ["인구감소율", "인구변화율", "POP_DROP_RATE"],
    "biz_drop": ["사업체감소율", "사업체수변화율", "BIZ_DROP_RATE"],
    "aged_bld": ["노후건축물비율", "노후건축물", "AGED_BLD_RATE"],
}

def _pick(row, keys):
    for k in keys:
        if k in row and row[k] not in ("", None):
            return row[k]
    return None

def lookup(sigungu: str, emd: str = None):
    path = config.DECLINE_CSV_PATH
    if not os.path.exists(path):
        return None  # CSV 미확보 -> mock
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sg = _pick(row, COLS["sigungu"]) or ""
            em = _pick(row, COLS["emd"]) or ""
            if sigungu in sg and (emd is None or emd in em):
                return {
                    "sigungu": sg, "emd": em,
                    "pop_drop_pct": _num(_pick(row, COLS["pop_drop"])),
                    "biz_drop_pct": _num(_pick(row, COLS["biz_drop"])),
                    "aged_bld_pct": _num(_pick(row, COLS["aged_bld"])),
                }
    return None

def _num(v):
    try: return float(str(v).replace("%", "").strip())
    except: return None

def judge(ind: dict):
    """3대 기준 대입 -> 충족 개수 + 쇠퇴 여부."""
    c = config.DECLINE_CRITERIA
    checks = []
    if ind.get("pop_drop_pct") is not None:
        checks.append(("인구감소", ind["pop_drop_pct"] >= c["population_drop_pct"],
                       f"{ind['pop_drop_pct']}% (기준 {c['population_drop_pct']}%↑)"))
    if ind.get("biz_drop_pct") is not None:
        checks.append(("사업체감소", ind["biz_drop_pct"] >= c["business_drop_pct"],
                       f"{ind['biz_drop_pct']}% (기준 {c['business_drop_pct']}%↑)"))
    if ind.get("aged_bld_pct") is not None:
        checks.append(("노후건축물", ind["aged_bld_pct"] >= c["aged_building_pct"],
                       f"{ind['aged_bld_pct']}% (기준 {c['aged_building_pct']}%↑)"))
    met = sum(1 for _, ok, _ in checks if ok)
    return {"checks": checks, "met": met,
            "is_declining": met >= c["criteria_needed"]}
