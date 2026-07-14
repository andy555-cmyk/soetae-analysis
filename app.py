"""쇠퇴 분석 시스템 - 웹앱.
브라우저에서 주소 입력 -> 뒤에서 지오코딩/상권/쇠퇴등급/빈점포 API 호출 -> 리포트 표시.
실행: pip install -r requirements.txt && (키 환경변수 설정) && python app.py -> http://localhost:5000
정부 API는 CORS로 브라우저 직접호출 불가 -> 이 백엔드가 대신 호출한다."""
import os
from flask import Flask, request, jsonify, render_template_string
import geocode, commercial, decline_grade, vacancy

app = Flask(__name__)
_GRADE_CACHE = {}   # 시군구+연도 쇠퇴등급 캐시(정적)

# 시군구코드: 좌표->행정표준코드 앞 5자리. VWorld 지오코딩 결과의 level4LC(법정동코드) 앞5.
def _signgu_from_geo(geo):
    ld = geo.get("ldongCd") or geo.get("emd_code")
    if ld: return str(ld)[:5]
    return None

def diagnose(address, radius=500, year="2016"):
    geo = geocode.geocode(address)
    if not geo:
        return {"error": "주소를 좌표로 변환하지 못했습니다. 주소를 확인해주세요."}
    # 상권
    rows = commercial.stores_in_radius(geo["lon"], geo["lat"], radius) or []
    comm = commercial.summarize(rows) if rows else {"total_stores":0,"by_major_category":{},"note":""}
    # 빈점포 스냅샷
    key = f"{round(geo['lat'],4)}_{round(geo['lon'],4)}_{radius}"
    snap_path = f"snapshots/{key}.json"
    prev = vacancy.load(snap_path)
    cur = {"date": __import__("datetime").date.today().isoformat(),
           "lon":geo["lon"],"lat":geo["lat"],"radius":radius,"count":len(rows),
           "ids":{r.get("bizesId"):{"nm":r.get("bizesNm")} for r in rows}}
    if prev:
        vac = vacancy.compare(prev, cur); vac["has_prev"]=True
    else:
        vacancy.save(cur, snap_path)
        vac = {"has_prev":False, "base_date":cur["date"], "base_count":cur["count"]}
    # 쇠퇴 등급 (시군구, 캐시)
    signgu = _signgu_from_geo(geo)
    grades = []
    if signgu:
        ck = f"{signgu}_{year}"
        if ck not in _GRADE_CACHE:
            _GRADE_CACHE[ck] = decline_grade.sigungu_indicators(signgu, year)
        grades = _GRADE_CACHE[ck]
    gonga = next((int(g["value"]) for g in grades if "공가율" in (g["mean"] or "")), None)
    vac["gonga"] = gonga
    by_sector = {}
    for g in grades:
        by_sector.setdefault(g["sector"], []).append(
            {"name": (g["mean"] or "").replace(" 등급",""), "value": int(g["value"]) if g["value"] else None})
    return {"address":address, "lat":geo["lat"], "lon":geo["lon"],
            "sigungu":geo.get("sigungu"), "emd":geo.get("emd"),
            "commercial":comm, "vacancy":vac, "grades_by_sector":by_sector,
            "grade_area":geo.get("sigungu"), "grade_year":year}

@app.route("/api/diagnose")
def api_diagnose():
    addr = request.args.get("address","").strip()
    radius = int(request.args.get("radius", 500))
    if not addr:
        return jsonify({"error":"주소를 입력하세요."})
    try:
        return jsonify(diagnose(addr, radius))
    except Exception as e:
        return jsonify({"error": f"오류: {e}"})

@app.route("/")
def index():
    return render_template_string(PAGE)

PAGE = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>쇠퇴 분석 시스템</title>
<style>
:root{--navy:#1F3A5F;--red:#C0392B;--bg:#f5f6f8;--line:#e4e7ec}
*{box-sizing:border-box}body{font-family:-apple-system,'Malgun Gothic',sans-serif;margin:0;background:var(--bg);color:#222}
.wrap{max-width:860px;margin:0 auto;padding:28px 20px 60px}
h1{color:var(--navy);font-size:24px;margin:0 0 4px}.sub{color:#667085;font-size:13px;margin-bottom:24px}
.box{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:16px}
.searchbar{display:flex;gap:8px}
input{flex:1;padding:13px 14px;border:1px solid #cbd2dc;border-radius:9px;font-size:15px}
button{background:var(--navy);color:#fff;border:0;border-radius:9px;padding:0 22px;font-size:15px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.sec-title{color:var(--navy);font-weight:700;font-size:16px;margin:0 0 10px;border-bottom:2px solid var(--navy);padding-bottom:6px}
.kv{display:flex;flex-wrap:wrap;gap:8px}.chip{background:#eef1f6;border-radius:20px;padding:5px 12px;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left}
th{color:#667085;font-weight:600;background:#fafbfc}.g{display:inline-block;min-width:26px;text-align:center;font-weight:700;color:var(--navy)}
.sector{font-weight:700;color:var(--navy);margin:14px 0 6px}
.note{font-size:12px;color:var(--red);margin-top:8px}.muted{color:#667085;font-size:12px}
.big{font-size:22px;font-weight:800;color:var(--navy)}
.loading{text-align:center;color:#667085;padding:30px}
.err{color:var(--red);padding:14px;background:#fdecea;border-radius:9px}
</style></head><body><div class=wrap>
<h1>쇠퇴 분석 시스템</h1>
<div class=sub>주소를 넣으면 대상지의 상권·빈점포·쇠퇴진단 등급을 자동 분석합니다 (실데이터: 국토부·소상공인시장진흥공단·VWorld)</div>
<div class=box><div class=searchbar>
<input id=addr placeholder="예) 부산광역시 기장군 기장읍 동부리 487" value="부산광역시 기장군 기장읍 동부리 487">
<button id=go onclick=run()>진단</button>
</div><div class=muted style=margin-top:8px>반경 500m 기준</div></div>
<div id=out></div>
<script>
const out=document.getElementById('out');
async function run(){
  const a=document.getElementById('addr').value.trim();
  if(!a)return;
  document.getElementById('go').disabled=true;
  out.innerHTML='<div class="box loading">분석 중… 정부 데이터를 불러오고 있습니다 (10~20초)</div>';
  try{
    const r=await fetch('/api/diagnose?address='+encodeURIComponent(a));
    const d=await r.json();
    if(d.error){out.innerHTML='<div class="box"><div class=err>'+d.error+'</div></div>';}
    else render(d);
  }catch(e){out.innerHTML='<div class="box"><div class=err>요청 실패: '+e+'</div></div>';}
  document.getElementById('go').disabled=false;
}
function render(d){
  const c=d.commercial, v=d.vacancy;
  let h='';
  h+='<div class=box><div class=muted>'+d.address+'  ·  좌표 '+d.lat.toFixed(5)+', '+d.lon.toFixed(5)+'  ·  '+(d.sigungu||'')+' '+(d.emd||'')+'</div></div>';
  // 상권
  h+='<div class=box><div class=sec-title>1. 상권 현황 (반경 500m)</div>';
  h+='<div class=big>'+c.total_stores+'개 <span class=muted style=font-size:13px>영업 점포</span></div><div class=kv style=margin-top:10px>';
  for(const [k,val] of Object.entries(c.by_major_category).slice(0,8))h+='<span class=chip>'+k+' '+val+'</span>';
  h+='</div></div>';
  // 빈점포
  h+='<div class=box><div class=sec-title>2. 빈 점포 · 공실</div>';
  if(v.has_prev){h+='<div class=kv><span class=chip>기간 '+v.t0_date+'→'+v.t1_date+'</span><span class=chip>폐업 '+v.closed+'</span><span class=chip>신규 '+v.opened+'</span><span class=chip>순증감 '+(v.net>0?'+':'')+v.net+'</span><span class=chip>폐업률 '+v.closure_rate_pct+'%</span></div>';}
  else{h+='<div class=muted>기준 스냅샷 저장됨 ('+v.base_date+' · '+v.base_count+'개). 상가정보 분기 갱신 시 재실행하면 폐업·공실 순증감이 자동 산출됩니다.</div>';}
  if(v.gonga!=null)h+='<div class=kv style=margin-top:8px><span class=chip>공가율(빈집) 등급 '+v.gonga+'/10</span></div><div class=muted style=margin-top:4px>※주거 빈집 지표(상업 공실과 구분)</div>';
  h+='</div>';
  // 쇠퇴 등급
  h+='<div class=box><div class=sec-title>3. 쇠퇴진단 등급 ('+(d.grade_area||'')+' · '+d.grade_year+')</div>';
  const secs=d.grades_by_sector;
  if(Object.keys(secs).length===0)h+='<div class=muted>등급 데이터를 불러오지 못했습니다.</div>';
  for(const sec of ['인구사회','산업경제','물리환경']){
    if(!secs[sec])continue;
    h+='<div class=sector>['+sec+'부문] '+secs[sec].length+'개 지표</div><table><tr><th>지표</th><th style=width:90px>등급(1~10)</th></tr>';
    for(const g of secs[sec])h+='<tr><td>'+g.name+'</td><td><span class=g>'+(g.value??'-')+'</span></td></tr>';
    h+='</table>';
  }
  h+='<div class=note>※ 등급값(1~10)은 전국 상대 위치. 지표별 방향이 달라 종합 판정은 공식 범례 확정 후 산출.</div></div>';
  out.innerHTML=h;
}
</script></div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # 호스팅(Render 등)은 PORT를 주입
    app.run(host="0.0.0.0", port=port, debug=False)
