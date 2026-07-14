"""국토교통부 쇠퇴진단 등급 API (data.go.kr 15058591, 1611000/DceDgnssGradeService).
인구사회·산업경제·물리환경 3부문 개별지표를 등급값(1~10)으로 제공. 계정 공용 인증키 사용.
시군구 조회(getGradeSigngu) 검증 완료. HTTPS + 재시도로 클라우드 안정화."""
import time, requests, config

BASE = "https://apis.data.go.kr/1611000/DceDgnssGradeService"

SECTOR = {}
for n in list(range(1,17))+[25]: SECTOR[f"GRADE{n:05d}"]="인구사회"
for n in [17,18,19,20,21,22,23,24,26,27,28,29,30,31,32]: SECTOR[f"GRADE{n:05d}"]="산업경제"
for n in [33,34,35,36,37,38,39,40]: SECTOR[f"GRADE{n:05d}"]="물리환경"

def _get_body(session, gc, signgu_cd, year, retries=2):
    for i in range(retries):
        try:
            return session.get(f"{BASE}/getGradeSigngu", params={
                "serviceKey":config.SBIZ_SERVICE_KEY,"signguCd":signgu_cd,
                "gradeCd":gc,"year":year,"type":"json","numOfRows":3,"pageNo":1},
                timeout=15).json().get("body")
        except Exception:
            time.sleep(0.8 * (i + 1))
    return None

def sigungu_indicators(signgu_cd, year="2016", max_codes=40):
    s = requests.Session(); out=[]
    for n in range(1, max_codes+1):
        gc=f"GRADE{n:05d}"
        b=_get_body(s, gc, signgu_cd, year)
        if b and b.get("gradeMean"):
            out.append({"gradeCd":gc,"sector":SECTOR.get(gc,"기타"),
                        "mean":b["gradeMean"],"value":_num(b["value"]),
                        "name":b.get("signguNm"),"year":b.get("year")})
    return out

def _num(v):
    try: return float(v)
    except: return None
