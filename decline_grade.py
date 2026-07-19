"""국토교통부 쇠퇴진단 등급 API (data.go.kr 15058591, 1611000/DceDgnssGradeService).
인구사회·산업경제·물리환경 3부문 개별지표를 등급값(1~10)으로 제공. 계정 공용 인증키 사용.
시군구 조회(getGradeSigngu) 검증 완료. 신규 시군구 첫 조회 지연을 줄이기 위해 병렬(ThreadPool) 조회."""
import requests, config
from concurrent.futures import ThreadPoolExecutor

BASE = "https://apis.data.go.kr/1611000/DceDgnssGradeService"

SECTOR = {}
for n in list(range(1,17))+[25]: SECTOR[f"GRADE{n:05d}"]="인구사회"
for n in [17,18,19,20,21,22,23,24,26,27,28,29,30,31,32]: SECTOR[f"GRADE{n:05d}"]="산업경제"
for n in [33,34,35,36,37,38,39,40]: SECTOR[f"GRADE{n:05d}"]="물리환경"

def _num(v):
    try: return float(v)
    except: return None

def _get_body(gc, signgu_cd, year):
    """단일 등급코드 조회(재시도 없이 짧은 타임아웃). 실패 시 None."""
    try:
        return requests.get(f"{BASE}/getGradeSigngu", params={
            "serviceKey":config.SBIZ_SERVICE_KEY,"signguCd":signgu_cd,
            "gradeCd":gc,"year":year,"type":"json","numOfRows":3,"pageNo":1},
            timeout=8).json().get("body")
    except Exception:
        return None

def sigungu_indicators(signgu_cd, year="2016", max_codes=40):
    """GRADE00001~40을 병렬 조회해 등급 지표 목록 반환(코드 순서 유지)."""
    codes=[f"GRADE{n:05d}" for n in range(1, max_codes+1)]
    with ThreadPoolExecutor(max_workers=10) as ex:
        pairs=list(ex.map(lambda gc:(gc, _get_body(gc, signgu_cd, year)), codes))
    out=[]
    for gc,b in pairs:
        if b and b.get("gradeMean"):
            out.append({"gradeCd":gc,"sector":SECTOR.get(gc,"기타"),
                        "mean":b["gradeMean"],"value":_num(b["value"]),
                        "name":b.get("signguNm"),"year":b.get("year")})
    return out
