"""주소 -> 좌표(위경도) + 행정구역코드. VWorld 우선, 없으면 Kakao. 재시도 적용."""
import time, requests, config

def _get(url, **kw):
    last = None
    for i in range(3):
        try:
            return requests.get(url, timeout=20, **kw)
        except Exception as e:
            last = e; time.sleep(1.0 * (i + 1))
    raise last

def geocode(address: str):
    if config.VWORLD_KEY:
        r = _get("https://api.vworld.kr/req/address", params={
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "epsg:4326", "type": "road" if _has_road(address) else "parcel",
            "address": address, "format": "json", "key": config.VWORLD_KEY,
        }, headers={"Referer": "http://localhost"})
        try:
            d = r.json()
        except Exception:
            d = {}
        if d.get("response", {}).get("status") == "OK":
            p = d["response"]["result"]["point"]
            s = d["response"]["refined"]["structure"]
            return {"lon": float(p["x"]), "lat": float(p["y"]),
                    "sido": s.get("level1"), "sigungu": s.get("level2"),
                    "emd": s.get("level4L"), "ldongCd": s.get("level4LC"), "source": "vworld"}
    if config.KAKAO_REST_KEY:
        r = _get("https://dapi.kakao.com/v2/local/search/address.json",
            headers={"Authorization": f"KakaoAK {config.KAKAO_REST_KEY}"},
            params={"query": address})
        docs = r.json().get("documents", [])
        if docs:
            doc = docs[0]; addr = doc.get("address") or {}
            return {"lon": float(doc["x"]), "lat": float(doc["y"]),
                    "sido": addr.get("region_1depth_name"),
                    "sigungu": addr.get("region_2depth_name"),
                    "emd": addr.get("region_3depth_name"), "ldongCd": addr.get("b_code"), "source": "kakao"}
    return None  # 키 없음 -> mock 모드에서 대체

def _has_road(a):
    return any(k in a for k in ["로", "길"]) and "리" not in a.split()[-1]
