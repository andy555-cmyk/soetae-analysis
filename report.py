"""수집 데이터 -> 자연어 쇠퇴 진단 리포트. 템플릿 기반(무료), LLM 훅은 선택."""
from datetime import date

def build_report(addr, geo, ind, judge, comm):
    L = []
    L.append(f"# 쇠퇴 진단 리포트")
    L.append(f"- 대상지: {addr}")
    if geo:
        L.append(f"- 좌표: {geo['lat']:.6f}, {geo['lon']:.6f}  ({geo['sigungu']} {geo.get('emd','')})")
    L.append(f"- 생성일: {date.today()}  |  데이터: 도시재생 쇠퇴진단지표 + 소상공인 상가정보")
    L.append("")
    # 1. 판정
    L.append("## 1. 종합 판정")
    if judge:
        verdict = "쇠퇴지역 해당" if judge["is_declining"] else "쇠퇴 기준 미달"
        L.append(f"**{verdict}** — 국가 3대 기준 중 {judge['met']}개 충족 (2개 이상 시 쇠퇴지역)")
        for name, ok, detail in judge["checks"]:
            L.append(f"- {'[O]' if ok else '[ ]'} {name}: {detail}")
    else:
        L.append("_쇠퇴지표 미확보(키/CSV 필요)_")
    L.append("")
    # 2. 상권
    L.append("## 2. 상권 현황 (반경 500m)")
    if comm:
        L.append(f"- 영업 점포 수: {comm['total_stores']}개")
        top = list(comm["by_major_category"].items())[:6]
        L.append("- 업종 구성: " + ", ".join(f"{k} {v}" for k, v in top))
        L.append(f"- (!) {comm['note']}")
    else:
        L.append("_상가 데이터 미확보(키 필요)_")
    L.append("")
    # 3. 해석
    L.append("## 3. 해석")
    L.append(_interpret(ind, judge, comm))
    return "\n".join(L)

def _interpret(ind, judge, comm):
    if not judge:
        return "지표 확보 후 자동 해석이 생성됩니다."
    parts = []
    for name, ok, _ in (judge["checks"] or []):
        if ok and name == "인구감소": parts.append("인구가 국가 기준을 넘어 감소해 배후수요 축소가 진행 중")
        if ok and name == "사업체감소": parts.append("사업체 수 감소로 지역 경제활력 저하가 관측")
        if ok and name == "노후건축물": parts.append("노후건축물 비율이 높아 물리적 정비 수요가 큼")
    head = "본 대상지는 " + (", ".join(parts) if parts else "일부 지표에서 쇠퇴 신호가 있으나 기준 미달")
    tail = "이다. 정비·재생 사업의 명분 지표로 활용 가능하다." if judge["is_declining"] else "이다. 추가 지표 보완이 필요하다."
    return head + tail
