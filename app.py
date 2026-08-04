
import json, math
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

DATA_DIR=Path("data"); DATA_DIR.mkdir(exist_ok=True)
RACES_FILE=DATA_DIR/"races.json"; SETTINGS_FILE=DATA_DIR/"settings.json"
DEFAULT_WEIGHTS={"barrier":.30,"recent":.20,"moisture":.18,"weight_fit":.12,"body":.08,"odds_value":.05,"consistency":.07}

def load_json(p,d):
    try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d
    except: return d
def save_json(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def settings():
    s=load_json(SETTINGS_FILE,{})
    s.setdefault("weights",DEFAULT_WEIGHTS.copy()); s.setdefault("learning_rate",.03)
    return s
def races(): return load_json(RACES_FILE,[])

def pace(sec):
    if not sec or sec<=0:return 50.
    return max(0,min(100,160-sec*(160/240)))
def barrier(sec):
    if not sec or sec<=0:return 50.
    return max(0,min(100,120-sec*1.5))
def moisture(today,hist):
    vals=[]
    for s in hist:
        if s.get("moisture") is None or not s.get("time_sec"):continue
        sim=max(0,1-abs(today-float(s["moisture"]))/2)
        vals.append((sim,pace(float(s["time_sec"]))))
    return sum(a*b for a,b in vals)/(sum(a for a,_ in vals) or 1) if vals else 50.
def recent(hist):
    vals=[]
    for i,s in enumerate(hist[:5]):
        if not s.get("time_sec") and not s.get("finish"):continue
        sc=pace(float(s["time_sec"])) if s.get("time_sec") else 50
        if s.get("finish"): sc=sc*.7+max(0,100-(int(s["finish"])-1)*10)*.3
        w=1/(1+i*.18); vals.append((w,sc))
    return sum(w*s for w,s in vals)/sum(w for w,_ in vals) if vals else 50.
def barrier_stats(hist):
    v=[float(s["barrier_sec"]) for s in hist if s.get("barrier_sec")]
    if not v:return 50.,50.
    avg=sum(v)/len(v); b=barrier(avg)
    if len(v)==1:return b,60.
    sd=(sum((x-avg)**2 for x in v)/len(v))**.5
    return b,max(0,min(100,100-sd*4))
def weight_fit(w,hist):
    vals=[]
    for s in hist:
        if not s.get("carry_weight") or not s.get("time_sec"):continue
        sim=max(0,1-abs(w-float(s["carry_weight"]))/60)
        vals.append(sim*pace(float(s["time_sec"])))
    return sum(vals)/len(vals) if vals else 50.
def body_score(b,c):
    base=max(30,min(75,45+(float(b or 950)-850)/12))
    c=float(c or 0); adj=10 if -10<=c<=20 else (3 if -25<=c<=35 else -8)
    return max(0,min(100,base+adj))
def odds_score(o):
    if not o or o<=0:return 50.
    return max(20,min(90,35+math.log(float(o)+1,2)*9))
def score(h,m,wts):
    hist=h.get("history",[])
    bs,cs=barrier_stats(hist)
    f={"barrier":bs,"recent":recent(hist),"moisture":moisture(m,hist),
       "weight_fit":weight_fit(float(h.get("carry_weight",0)),hist),
       "body":body_score(h.get("body_weight"),h.get("body_change")),
       "odds_value":odds_score(h.get("odds")),"consistency":cs}
    total=sum(f[k]*wts.get(k,0) for k in f)
    return total,total*.78+f["odds_value"]*.22,f
def predict(r,wts):
    arr=[]
    for h in r["horses"]:
        s,l,f=score(h,float(r["moisture"]),wts)
        arr.append({**h,"score":s,"longshot":l,"features":f})
    arr.sort(key=lambda x:x["score"],reverse=True)
    marks=["◎","○","▲","☆","△","△","注","注","-","-","-","-"]
    for i,h in enumerate(arr):h["mark"]=marks[i]
    return arr
def review(r,p):
    res=r.get("result",[])
    if len(res)<3:return "結果未入力"
    d={h["number"]:h for h in p}; out=[]
    for i,n in enumerate(res[:3],1):
        h=d.get(n)
        if h:out.append(f"{i}着 {n} {h['name']} / 予想{h['mark']} / 総合{h['score']:.1f}")
    top={h["number"] for h in p[:3]}
    out.append(f"予想上位3頭からの馬券内捕捉: {len(top & set(res[:3]))}/3")
    for n in res[:3]:
        if n not in top and n in d:
            h=d[n]; strong=sorted(h["features"].items(),key=lambda x:x[1],reverse=True)[:2]
            out.append(f"見落とし: {n} {h['name']} / 強み "+ "・".join(f"{k}:{v:.0f}" for k,v in strong))
    return "\n".join(out)
def learn(r,s):
    res=r.get("result",[])
    if len(res)<3:return s,{}
    p=predict(r,s["weights"]); d={h["number"]:h for h in p}
    win=[d[n] for n in res[:3] if n in d]; lose=[h for h in p if h["number"] not in res[:3]]
    if not win or not lose:return s,{}
    before=s["weights"].copy(); lr=float(s.get("learning_rate",.03))
    for k in s["weights"]:
        a=sum(h["features"][k] for h in win)/len(win); b=sum(h["features"][k] for h in lose)/len(lose)
        s["weights"][k]=max(.01,s["weights"][k]+lr*(a-b)/100)
    z=sum(s["weights"].values()); s["weights"]={k:v/z for k,v in s["weights"].items()}
    return s,{k:s["weights"][k]-before[k] for k in before}

st.set_page_config(page_title="ばんえいAI",layout="wide")
st.title("🐎 ばんえいAI")
st.caption("予想 → 保存 → 結果入力 → 自動回顧 → 自動学習")

S=settings(); R=races()
t1,t2,t3,t4=st.tabs(["新規レース","保存レース","学習設定","使い方"])

with t1:
    a,b,c=st.columns(3)
    name=a.text_input("レース名","帯広 1R"); m=b.number_input("馬場水分 %",0.,10.,2.2,.1); date=c.date_input("日付")
    n=int(st.number_input("頭数",2,12,10,1)); hs=[]
    for i in range(n):
        with st.expander(f"{i+1}番"):
            x1,x2,x3,x4,x5=st.columns(5)
            hn=x1.text_input("馬名",key=f"n{i}"); cw=x2.number_input("斤量",value=600.,step=10.,key=f"cw{i}")
            bw=x3.number_input("馬体重",value=950,step=1,key=f"bw{i}"); ch=x4.number_input("増減",value=0,step=1,key=f"ch{i}")
            od=x5.number_input("オッズ",value=10.,min_value=.1,step=.1,key=f"od{i}")
            st.caption("近5走：タイムは秒で入力（1:42.3 → 102.3）。未入力は0。")
            hist=[]
            for j in range(5):
                q1,q2,q3,q4,q5=st.columns(5)
                hm=q1.number_input(f"{j+1}走前 水分",value=2.,step=.1,key=f"m{i}_{j}")
                tm=q2.number_input("走破秒",value=0.,step=.1,key=f"t{i}_{j}")
                br=q3.number_input("障害秒",value=0.,step=.1,key=f"b{i}_{j}")
                hw=q4.number_input("斤量",value=0.,step=10.,key=f"w{i}_{j}")
                fn=q5.number_input("着順",value=0,min_value=0,max_value=12,step=1,key=f"f{i}_{j}")
                if tm or br or hw or fn:hist.append({"moisture":hm,"time_sec":tm or None,"barrier_sec":br or None,"carry_weight":hw or None,"finish":fn or None})
            hs.append({"number":i+1,"name":hn or f"{i+1}番","carry_weight":cw,"body_weight":bw,"body_change":ch,"odds":od,"history":hist})
    if st.button("予想する",type="primary"):
        r={"id":datetime.now().strftime("%Y%m%d%H%M%S"),"name":name,"date":str(date),"moisture":m,"horses":hs,"result":[]}
        st.session_state.race=r; st.session_state.pred=predict(r,S["weights"])
    if "pred" in st.session_state:
        p=st.session_state.pred
        df=pd.DataFrame([{"印":h["mark"],"馬番":h["number"],"馬名":h["name"],"総合":round(h["score"],1),"障害":round(h["features"]["barrier"],1),
                          "近走":round(h["features"]["recent"],1),"水分適性":round(h["features"]["moisture"],1),
                          "斤量適性":round(h["features"]["weight_fit"],1),"安定度":round(h["features"]["consistency"],1),"穴期待":round(h["longshot"],1)} for h in p])
        st.dataframe(df,use_container_width=True,hide_index=True)
        st.success("最終印: "+" ".join(f"{h['mark']}{h['number']} {h['name']}" for h in p[:6]))
        st.info("三連系候補: 1列目 "+"・".join(str(h["number"]) for h in p[:2])+" / 2列目 "+"・".join(str(h["number"]) for h in p[:4])+" / 3列目 "+"・".join(str(h["number"]) for h in p[:6]))
        if st.button("この予想を保存"):
            r=st.session_state.race; r["prediction"]=[{"number":h["number"],"name":h["name"],"mark":h["mark"],"score":h["score"],"features":h["features"]} for h in p]
            R.append(r); save_json(RACES_FILE,R); st.success("保存しました")

with t2:
    if not R:st.info("保存レースはまだありません")
    for rev_i,r in enumerate(reversed(R)):
        i=len(R)-1-rev_i
        with st.expander(f"{r.get('date','')} {r.get('name','')} / 水分{r.get('moisture')}%"):
            p=predict(r,S["weights"])
            st.dataframe(pd.DataFrame([{"印":h["mark"],"馬番":h["number"],"馬名":h["name"],"総合":round(h["score"],1)} for h in p]),hide_index=True,use_container_width=True)
            tx=st.text_input("結果（例 7-2-9）","-".join(map(str,r.get("result",[]))),key=f"res{i}")
            if st.button("結果保存＋自動学習",key=f"sr{i}"):
                try:
                    r["result"]=[int(x) for x in tx.replace("→","-").split("-") if x.strip()][:3]
                    r["review"]=review(r,p); S,delta=learn(r,S); R[i]=r
                    save_json(RACES_FILE,R); save_json(SETTINGS_FILE,S)
                    st.success("保存・学習しました"); st.code(r["review"]); st.write({k:round(v,4) for k,v in delta.items()})
                except Exception as e: st.error(str(e))
            if r.get("review"):st.text_area("自動回顧",r["review"],height=150,key=f"rv{i}")

with t3:
    nw={}
    for k,v in S["weights"].items(): nw[k]=st.slider(k,0.,.6,float(v),.01)
    lr=st.slider("learning_rate",0.,.2,float(S.get("learning_rate",.03)),.01)
    if st.button("設定を保存"):
        z=sum(nw.values()) or 1; S["weights"]={k:v/z for k,v in nw.items()}; S["learning_rate"]=lr; save_json(SETTINGS_FILE,S); st.success("保存しました")
    st.json(S)

with t4:
    st.markdown("""
### 使い方
1. 新規レースで馬場水分・各馬・近5走を入力  
2. 「予想する」で印とスコアを表示  
3. 予想を保存  
4. レース後に `7-2-9` のように結果入力  
5. 自動回顧＋重み自動更新

### 評価軸
- 障害力
- 近走内容
- 馬場水分適性
- 今回斤量への適性
- 馬体重・増減
- 障害安定度
- 穴期待（オッズは能力とは分離して弱めに使用）

結果を見て毎回ルールを全変更するのではなく、学習率を小さくして少しずつ補正します。
""")
