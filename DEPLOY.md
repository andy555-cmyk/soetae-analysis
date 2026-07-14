# 배포 가이드 — 무료 클라우드 호스팅 (Render)

목표: Andy가 **URL 하나만 열면** 주소 넣고 진단하는 웹앱. 파이썬 설치 불필요.

이 폴더 파일 전부가 배포 준비 완료 상태입니다 (`app.py`, `requirements.txt`, `Procfile`, `render.yaml` 등).

---

## 준비물 (무료, Andy 계정 필요)

계정 생성·로그인은 본인만 할 수 있습니다(대행 불가). 두 개만 만들면 됩니다:

1. **GitHub** 계정 — 코드 저장소 (github.com)
2. **Render** 계정 — 호스팅 (render.com, GitHub로 바로 로그인 가능)

---

## 배포 순서

### 1) 코드를 GitHub에 올리기
- github.com → New repository → 이름 예: `soetae-analysis` → Create
- 이 폴더의 파일 전부(app.py, geocode.py, commercial.py, decline_grade.py, vacancy.py, report_grade.py, requirements.txt, Procfile, render.yaml)를 업로드
  - 웹에서 "uploading an existing file"로 드래그&드롭해도 됩니다.

### 2) Render에 연결
- render.com → New → Web Service → GitHub 저장소 선택
- 설정은 `render.yaml`이 자동 인식 (runtime Python, `gunicorn app:app`)
- Plan: **Free**

### 3) 키 입력 (중요 — 코드에 넣지 말 것)
Render의 Environment(환경변수)에 2개 추가:
- `SBIZ_SERVICE_KEY` = 상가 API 인증키 (data.go.kr 마이페이지)
- `VWORLD_KEY` = VWorld 개발키 (vworld 인증키관리)

### 4) 배포
- Create Web Service → 몇 분 후 `https://soetae-analysis.onrender.com` 같은 URL 발급
- 그 URL 열고 주소 입력 → 진단. 끝.

---

## 무료 플랜 주의사항 (솔직히)

- **첫 접속이 느림**: 무료 서버는 미사용 시 잠들어, 첫 요청에 30초쯤 깨어나는 시간이 걸립니다. 이후는 빠릅니다.
- **빈점포 스냅샷 비영속**: 무료 플랜은 재배포 시 파일이 초기화돼 스냅샷(폐업 비교 기준점)이 사라질 수 있습니다. 폐업 순증감을 계속 쌓으려면 나중에 DB(무료 Postgres 등) 연결이 필요합니다.
- **VWorld 개발키 6개월 만료**: 만료 전 vworld에서 연장(최대 3회).

---

## 다음 개선 (배포 후)
- 읍면동 단위 쇠퇴등급(getGradeEmd) 정밀화 — 참고문서/관리부서(051-998-6756) 확인
- 등급 종합 판정 산식 — 공식 범례로 방향 확정
- 빈점포 스냅샷 DB화 (폐업 순증감 누적)
- 리포트 PDF/Word 다운로드 버튼 추가
