"""빈 점포/공실 = 시점비교(스냅샷 차분)로 산출.
상가 API는 '현재 영업중' 스냅샷만 준다. 두 시점의 상가업소번호(bizesId) 집합을 비교하면
사라진 업소=폐업, 추가된 업소=신규, 순증감·폐업률(공실 대리지표)을 실측할 수 있다.
상가정보는 분기 갱신 -> 오늘 기준점 저장 후 다음 분기부터 실수치 산출.
(참고: 상가 API의 storeListByDate '삭제 포함' 조회는 현재 데이터 미제공(NODATA)이라 시점비교 채택)"""
import json, os, datetime
import commercial

def capture(lon, lat, radius=500):
    rows = commercial.stores_in_radius(lon, lat, radius) or []
    ids = {r.get("bizesId"): {"nm": r.get("bizesNm"), "lcls": r.get("indsLclsNm"),
                              "lon": r.get("lon"), "lat": r.get("lat")} for r in rows}
    return {"date": datetime.date.today().isoformat(), "lon": lon, "lat": lat,
            "radius": radius, "count": len(ids), "ids": ids}

def save(snap, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    return path

def load(path):
    if not os.path.exists(path): return None
    with open(path, encoding="utf-8") as f: return json.load(f)

def compare(t0, t1):
    """t0=과거, t1=현재. 폐업/신규/순증감/폐업률."""
    a, b = set(t0["ids"]), set(t1["ids"])
    closed = a - b        # 사라진 업소 = 폐업(공실화)
    opened = b - a        # 신규 개업
    survived = a & b
    closure_rate = round(len(closed) / len(a) * 100, 1) if a else None
    return {
        "t0_date": t0["date"], "t1_date": t1["date"],
        "t0_count": len(a), "t1_count": len(b),
        "closed": len(closed), "opened": len(opened), "survived": len(survived),
        "net": len(b) - len(a),
        "closure_rate_pct": closure_rate,   # 폐업률(빈 점포 발생률 대리지표)
        "closed_samples": [t0["ids"][x]["nm"] for x in list(closed)[:10]],
    }
