"""
쇠퇴 분석 시스템 - 설정 파일
발급받은 키를 아래에 넣으면 실시간 호출이 됩니다. (발급법: README.md)
비워두면 자동으로 --mock(샘플 데이터) 모드로 동작합니다.
"""
import os

# 1) 공공데이터포털 상가(상권)정보 API 인증키  (data.go.kr, 기관코드 B553077)
SBIZ_SERVICE_KEY = os.getenv("SBIZ_SERVICE_KEY", "")

# 2) 지오코딩(주소→좌표)용 키 : VWorld 또는 Kakao 중 택1
VWORLD_KEY = os.getenv("VWORLD_KEY", "")
KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY", "")

# 2-1) 카카오맵 JavaScript 키 (프런트엔드 인라인 로드뷰용, 도메인 등록 필요)
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "")

# 2-2) KOSIS(통계청 국가통계포털) 공유서비스 인증키 - 시군구 연도별 실인구/사업체 시계열
KOSIS_KEY = os.getenv("KOSIS_KEY", "")

# 3) (선택) 쇠퇴진단지표 CSV 경로 - 도시재생 개방데이터 다운로드본
DECLINE_CSV_PATH = os.getenv("DECLINE_CSV_PATH", "data/rurban_decline_index.csv")

# 국가 도시쇠퇴 판정 기준 (도시재생특별법 시행령 기준)
DECLINE_CRITERIA = {
    "population_drop_pct": 20.0,   # 최근 30년 최대 대비 20% 이상 감소
    "business_drop_pct": 5.0,      # 최근 10년 최대 대비 5% 이상 감소
    "aged_building_pct": 50.0,     # 20년 이상 노후건축물 50% 이상
    "criteria_needed": 2,          # 3개 중 2개 이상 충족 시 '쇠퇴지역'
}
