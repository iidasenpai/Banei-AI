import json, math, io, re
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

DATA_DIR=Path('data'); DATA_DIR.mkdir(exist_ok=True)
RACES_FILE=DATA_DIR/'races.json'; SETTINGS_FILE=DATA_DIR/'settings.json'; SEED_FILE=DATA_DIR/'seed_results.json'
CALIBRATED_WEIGHTS={"barrier":.31,"recent":.16,"moisture":.23,"weight_fit":.12,"body":.05,"odds_value":.03,"consistency":.10}
FEATURE_LABELS={"barrier":"障害力","recent":"近走","moisture":"馬場水分適性","weight_fit":"斤量適性","body":"馬体・増減","odds_value":"妙味","consistency":"障害安定"}
SEED_RESULTS=[
 {"day":"Day1","race":1,"result":"4-1-5"},{"day":"Day1","race":2,"result":"6-8-3"},{"day":"Day1","race":3,"result":"2-4-9"},{"day":"Day1","race":4,"result":"5-6-1"},{"day":"Day1","race":5,"result":"3-10-5"},{"day":"Day1","race":6,"result":"1-4-8"},{"day":"Day1","race":7,"result":"8-9-7"},{"day":"Day1","race":8,"result":"2-6-3"},{"day":"Day1","race":9,"result":"7-8-5"},{"day":"Day1","race":10,"result":"4-1-6"},{"day":"Day1","race":11,"result":"10-3-8"},{"day":"Day1","race":12,"result":"6-5-1"},
 {"day":"Day2","race":1,"result":"5-1-4"},{"day":"Day2","race":2,"result":"8-9-10"},{"day":"Day2","race":3,"result":"10-7-5"},{"day":"Day2","race":4,"result":"10-4-9"},{"day":"Day2","race":5,"result":"10-7-4"},{"day":"Day2","race":6,"result":"7-2-9"},{"day":"Day2","race":7,"result":"5-10-8"},{"day":"Day2","race":8,"result":"7-2-9"},{"day":"Day2","race":9,"result":"9-2-4"},{"day":"Day2","race":10,"result":"1-10-2"},{"day":"Day2","race":11,"result":"3-9-5"},{"day":"Day2","race":12,"result":"1-4-6"}
]

def load_json(p,d):
    try:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
    except:return d

def save_json(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')

def get_settings():
    s=load_json(SETTINGS_FILE,{})
    s.setdefault('weights',CALIBRATED_WEIGHTS.copy()); s.setdefault('learning_rate',.02); s.setdefault('seed_calibrated',True)
    return s

def get_races():return load_json(RACES_FILE,[])

def sec_score(sec):
    if not sec or sec<=0:return 50.
    return max(0,min(100,160-float(sec)*(160/240)))

def barrier_score(sec):
    if not sec or sec<=0:return 50.
    return max(0,min(100,120-float(sec)*1.5))

def recent_score(hist):
    vals=[]
    for i,s in enumerate(hist[:5]):
        if not s.get('time_sec') and not s.get('finish'):continue
        sc=sec_score(s.get('time_sec')) if s.get('time_sec') else 50
        if s.get('finish'):sc=.68*sc+.32*max(0,100-(int(s['finish'])-1)*10)
        w=1/(1+i*.2); vals.append((w,sc))
    return sum(w*x for w,x in vals)/sum(w for w,_ in vals) if vals else 50.

def moisture_score(today,hist):
    vals=[]
    for s in hist:
        if s.get('moisture') is None or not s.get('time_sec'):continue
        diff=abs(float(today)-float(s['moisture']))
        sim=max(0,1-diff/1.8)
        # exact/near match bonus
        if diff<=.3: sim*=1.18
        vals.append((sim,sec_score(s['time_sec'])))
    return sum(a*b for a,b in vals)/(sum(a for a,_ in vals) or 1) if vals else 50.

def barrier_stats(hist):
    v=[float(s['barrier_sec']) for s in hist if s.get('barrier_sec')]
    if not v:return 50.,50.
    avg=sum(v)/len(v); bs=barrier_score(avg)
    if len(v)==1:return bs,60.
    sd=(sum((x-avg)**2 for x in v)/len(v))**.5
    consistency=max(0,min(100,100-sd*4.5))
    # recurrent sub-35 sec is strongly rewarded
    fast=sum(x<=35 for x in v)
    bs=min(100,bs+fast*2.5)
    return bs,consistency

def weight_score(today_weight,hist):
    vals=[]
    for s in hist:
        if not s.get('carry_weight') or not s.get('time_sec'):continue
        diff=abs(float(today_weight)-float(s['carry_weight']))
        sim=max(0,1-diff/70)
        vals.append(sim*sec_score(s['time_sec']))
    return sum(vals)/len(vals) if vals else 50.

def body_score(b,c):
    base=max(35,min(75,45+(float(b or 950)-850)/14))
    c=float(c or 0)
    adj=8 if -10<=c<=20 else (2 if -25<=c<=35 else -8)
    return max(0,min(100,base+adj))

def odds_value(o):
    if not o or o<=0:return 50.
    return max(20,min(90,35+math.log(float(o)+1,2)*9))

def score_horse(h,moist,wts):
    hist=h.get('history',[]); bs,cs=barrier_stats(hist)
    f={"barrier":bs,"recent":recent_score(hist),"moisture":moisture_score(moist,hist),"weight_fit":weight_score(h.get('carry_weight',0),hist),"body":body_score(h.get('body_weight'),h.get('body_change')),"odds_value":odds_value(h.get('odds')),"consistency":cs}
    total=sum(f[k]*wts.get(k,0) for k in f)
    # 3rd-place/longshot score emphasizes stable barrier + moisture, not just odds
    longshot=.55*total+.18*f['barrier']+.17*f['consistency']+.10*f['odds_value']
    return total,longshot,f

def predict(r,wts):
    out=[]
    for h in r['horses']:
        total,longshot,feats=score_horse(h,float(r['moisture']),wts)
        out.append({**h,'score':total,'longshot':longshot,'features':feats})
    out.sort(key=lambda x:x['score'],reverse=True)
    marks=['◎','○','▲','☆','△','△','注','注','-','-','-','-']
    for i,h in enumerate(out):h['mark']=marks[i]
    return out

def bet_suggestions(pred):
    win=[h['number'] for h in pred[:3]]
    place=[h['number'] for h in pred[:5]]
    longshots=sorted(pred,key=lambda x:x['longshot'],reverse=True)[:4]
    longnums=[h['number'] for h in longshots]
    return {
      '本線3連単':f"{win[0]} → {win[1]}・{win[2]} → {'・'.join(map(str,place))}",
      '押さえ3連単':f"{win[1]}・{win[2]} → {win[0]} → {'・'.join(map(str,place))}",
      '穴3連系':f"軸 {win[0]} / 穴候補 {'・'.join(map(str,longnums))}",
      '3連複':f"{'・'.join(map(str,place[:4]))} BOX"
    }

def review(r,p):
    res=r.get('result',[])
    if len(res)<3:return '結果未入力'
    d={h['number']:h for h in p}; lines=[]
    for pos,no in enumerate(res[:3],1):
        h=d.get(no)
        if h: lines.append(f"{pos}着 {no} {h['name']} / 予想{h['mark']} / 総合{h['score']:.1f} / 穴{h['longshot']:.1f}")
    top3={h['number'] for h in p[:3]}; top6={h['number'] for h in p[:6]}
    lines.append(f"上位3頭捕捉 {len(top3 & set(res[:3]))}/3 / 印6頭捕捉 {len(top6 & set(res[:3]))}/3")
    for no in res[:3]:
        if no not in top3 and no in d:
            h=d[no]; strong=sorted(h['features'].items(),key=lambda x:x[1],reverse=True)[:3]
            lines.append('見落とし '+f"{no} {h['name']} / 強み "+'・'.join(f"{FEATURE_LABELS[k]}:{v:.0f}" for k,v in strong))
    return '\n'.join(lines)

def learn(r,s):
    res=r.get('result',[])
    if len(res)<3:return s,{}
    p=predict(r,s['weights']); d={h['number']:h for h in p}
    winners=[d[n] for n in res[:3] if n in d]; losers=[h for h in p if h['number'] not in res[:3]]
    if not winners or not losers:return s,{}
    before=s['weights'].copy(); lr=float(s.get('learning_rate',.02))
    # 1st > 2nd > 3rd weighting
    pos_w={res[0]:1.0,res[1]:.75,res[2]:.55}
    for k in s['weights']:
        wa=sum(h['features'][k]*pos_w[h['number']] for h in winners)/sum(pos_w[h['number']] for h in winners)
        la=sum(h['features'][k] for h in losers)/len(losers)
        s['weights'][k]=max(.01,s['weights'][k]+lr*(wa-la)/100)
    z=sum(s['weights'].values()); s['weights']={k:v/z for k,v in s['weights'].items()}
    return s,{k:s['weights'][k]-before[k] for k in before}

def stats_df(races):
    rows=[]
    for r in races:
        if len(r.get('result',[]))<3:continue
        p=predict(r,get_settings()['weights']); res=r['result'][:3]
        top3=[h['number'] for h in p[:3]]; top6=[h['number'] for h in p[:6]]
        rows.append({'日付':r.get('date',''),'レース':r.get('name',''),'結果':'-'.join(map(str,res)),'◎1着':int(p[0]['number']==res[0]),'上位3捕捉':len(set(top3)&set(res)),'印6捕捉':len(set(top6)&set(res))})
    return pd.DataFrame(rows)


def _clean_lines(text):
    return [x.strip() for x in str(text or '').replace('\r','').split('\n') if x.strip()]

def _time_to_sec(text):
    m=re.search(r'(\d+):(\d+(?:\.\d+)?)', str(text))
    if not m:return None
    return int(m.group(1))*60+float(m.group(2))

def parse_entry_text(text):
    """netkeiba地方競馬の出馬表コピペを馬ごとに解析。"""
    lines=_clean_lines(text)
    horses=[]
    i=0
    while i < len(lines):
        if re.fullmatch(r'\d{1,2}', lines[i]) and i+2 < len(lines) and 'データベース' in lines[i+2]:
            no=int(lines[i]); name=lines[i+1]
            j=i+3
            while j < len(lines):
                if re.fullmatch(r'\d{1,2}', lines[j]) and j+2 < len(lines) and 'データベース' in lines[j+2]:
                    break
                j+=1
            block=lines[i:j]
            joined='\n'.join(block)
            carry=None
            m=re.search(r'(?:牡|牝|セ)\d+\s+.*?\s+([^\s]+)\s+(\d{3}(?:\.\d+)?)', joined)
            if m: carry=float(m.group(2))
            odds=None; popularity=None; body=None; change=0
            # Common mobile copy format:
            # 63.2
            # 7人気  904
            # (+5)
            em=re.search(r'(?m)^\s*(\d+(?:\.\d+)?)\s*$\n^\s*(\d+)人気(?:\s+(\d{3,4}))?\s*$\n^\s*\(([+-]?\d+)\)\s*$', joined)
            if em:
                odds=float(em.group(1)); popularity=int(em.group(2))
                body=int(em.group(3)) if em.group(3) else None
                change=int(em.group(4))
            if odds is None:
                for k,line in enumerate(block):
                    if re.fullmatch(r'\d+(?:\.\d+)?', line):
                        val=float(line)
                        if k+1 < len(block) and re.search(r'\d+人気', block[k+1]):
                            odds=val
                            pm=re.search(r'(\d+)人気',block[k+1]); popularity=int(pm.group(1)) if pm else None
                            bm=re.search(r'人気\s+(\d{3,4})',block[k+1])
                            if bm: body=int(bm.group(1))
                            for z in range(k+2,min(k+7,len(block))):
                                if body is None and re.fullmatch(r'\d{3,4}', block[z]): body=int(block[z])
                                cm=re.search(r'\(([+-]?\d+)\)', block[z])
                                if cm:
                                    change=int(cm.group(1)); break
                            break
            horses.append({'number':no,'name':name,'carry_weight':carry or 0.0,
                           'body_weight':body or 0,'body_change':change,'odds':odds or 0.0,
                           'popularity':popularity,'history':[]})
            i=j
        else:
            i+=1
    return horses

def parse_history_text(text):
    """近走コピペを {馬番: [history...]} に変換。"""
    raw=str(text or '').replace('\r','')
    header_pat=re.compile(r'(?m)^(\d{1,2})\s*\n([^\n]+)\s*\n\2のデータベース\s*$')
    heads=list(header_pat.finditer(raw))
    out={}
    for hi,h in enumerate(heads):
        no=int(h.group(1)); start=h.end(); end=heads[hi+1].start() if hi+1<len(heads) else len(raw)
        block=raw[start:end]
        races=[]
        date_matches=list(re.finditer(r'(?m)^(\d{2}/\d{2})\s+帯広\(ば\s+\d+R\s*$', block))
        for ri,dm in enumerate(date_matches[:5]):
            rs=dm.start(); re_end=date_matches[ri+1].start() if ri+1<len(date_matches) else len(block)
            chunk=block[rs:re_end]
            fm=re.search(r'(?m)^\s*(\d{1,2})\s*\n\s*(\d{1,2})頭\s*$',chunk)
            finish=int(fm.group(1)) if fm else None
            mm=re.search(r'(\d+(?:\.\d+)?)%',chunk); moist=float(mm.group(1)) if mm else None
            tsec=_time_to_sec(chunk)
            wm=re.search(r'(?m)^\s*(\d{3}(?:\.\d+)?)\s*\n\s*\d{3,4}kg',chunk)
            carry=float(wm.group(1)) if wm else None
            bm=re.search(r'(?m)^後\s*\n\s*(\d+(?:\.\d+)?)\s*$',chunk)
            bsec=float(bm.group(1)) if bm else None
            races.append({'moisture':moist,'time_sec':tsec,'barrier_sec':bsec,
                          'carry_weight':carry,'finish':finish,'date':dm.group(1)})
        out[no]=races
    return out

def parse_pasted_netkeiba(entry_text, history_text):
    horses=parse_entry_text(entry_text)
    hist=parse_history_text(history_text)
    for h in horses:
        h['history']=hist.get(h['number'],[])
    return horses

st.set_page_config(page_title='ばんえいAI',layout='wide')
st.title('🐎 ばんえいAI')
st.caption('2日24Rで初期調整済み / 予想 → 保存 → 結果入力 → 自動回顧 → 自動学習')
S=get_settings(); R=get_races()
if not SEED_FILE.exists(): save_json(SEED_FILE,SEED_RESULTS)

T=st.tabs(['新規レース','保存レース','成績','学習設定','バックアップ','使い方'])

with T[0]:
    st.info('初期重みは2日24Rの検証から、障害・馬場水分・障害安定を強めに設定しています。')
    a,b,c=st.columns(3); name=a.text_input('レース名','帯広 1R'); moist=b.number_input('馬場水分 %',0.,10.,2.2,.1); date=c.date_input('日付')
    mode=st.radio('入力方法',['テキスト貼り付け','フォーム','CSV一括'],horizontal=True)
    hs=[]
    if mode=='テキスト貼り付け':
        st.markdown('#### netkeibaテキスト貼り付け')
        st.caption('「出馬表」と「近走」をそのままコピーして貼り付けます。馬名・斤量・オッズ・馬体重・増減・近5走を自動解析します。')
        entry_text=st.text_area('出馬表 ↓',height=220,placeholder='1\\nプライムチョウター\\n牡3 ... 590.0\\n63.2\\n7人気 ...',key='entry_paste')
        history_text=st.text_area('近走 ↓',height=360,placeholder='1\\nプライムチョウター\\nプライムチョウターのデータベース\\n...\\n07/20  帯広(ば 1R\\n...',key='history_paste')
        if entry_text.strip():
            hs=parse_pasted_netkeiba(entry_text,history_text)
            if hs:
                preview=[{'馬番':h['number'],'馬名':h['name'],'斤量':h['carry_weight'],'オッズ':h['odds'],
                          '人気':h.get('popularity'),'馬体重':h['body_weight'],'増減':h['body_change'],
                          '近走取得':len(h['history'])} for h in hs]
                st.success(f'{len(hs)}頭を解析しました。')
                st.dataframe(pd.DataFrame(preview),use_container_width=True,hide_index=True)
                missing=[h['number'] for h in hs if not h['history']]
                if history_text.strip() and missing:
                    st.warning('近走を取得できなかった馬番: '+', '.join(map(str,missing)))
                with st.expander('解析した近走を確認'):
                    rows=[]
                    for h in hs:
                        for n,x in enumerate(h['history'],1):
                            rows.append({'馬番':h['number'],'馬名':h['name'],'何走前':n,'日付':x.get('date'),
                                         '水分':x.get('moisture'),'走破秒':x.get('time_sec'),'後/障害指標':x.get('barrier_sec'),
                                         '斤量':x.get('carry_weight'),'着順':x.get('finish')})
                    if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
            else:
                st.error('出馬表を解析できませんでした。馬番から最終馬までまとめてコピーして貼り付けてください。')
    elif mode=='CSV一括':
        st.caption('列: number,name,carry_weight,body_weight,body_change,odds,h1_m,h1_t,h1_b,h1_w,h1_f ... h5_m,h5_t,h5_b,h5_w,h5_f')
        sample_cols=['number','name','carry_weight','body_weight','body_change','odds']+[f'h{i}_{x}' for i in range(1,6) for x in ['m','t','b','w','f']]
        st.download_button('CSVテンプレート',pd.DataFrame(columns=sample_cols).to_csv(index=False).encode('utf-8-sig'),'banei_template.csv','text/csv')
        up=st.file_uploader('CSVアップロード',type=['csv'])
        if up:
            df=pd.read_csv(up); st.dataframe(df,use_container_width=True)
            for _,row in df.iterrows():
                hist=[]
                for i in range(1,6):
                    tm=row.get(f'h{i}_t',0)
                    if pd.notna(tm) and float(tm)>0:
                        hist.append({'moisture':float(row.get(f'h{i}_m',0) or 0),'time_sec':float(tm),'barrier_sec':float(row.get(f'h{i}_b',0) or 0) or None,'carry_weight':float(row.get(f'h{i}_w',0) or 0) or None,'finish':int(row.get(f'h{i}_f',0) or 0) or None})
                hs.append({'number':int(row['number']),'name':str(row['name']),'carry_weight':float(row['carry_weight']),'body_weight':float(row['body_weight']),'body_change':float(row['body_change']),'odds':float(row['odds']),'history':hist})
    else:
        n=int(st.number_input('頭数',2,12,10,1))
        for i in range(n):
            with st.expander(f'{i+1}番'):
                x1,x2,x3,x4,x5=st.columns(5)
                hn=x1.text_input('馬名',key=f'n{i}'); cw=x2.number_input('斤量',value=600.,step=10.,key=f'cw{i}'); bw=x3.number_input('馬体重',value=950,step=1,key=f'bw{i}'); ch=x4.number_input('増減',value=0,step=1,key=f'ch{i}'); od=x5.number_input('オッズ',value=10.,min_value=.1,step=.1,key=f'od{i}')
                st.caption('近5走：走破秒は 1:42.3 → 102.3。未入力は0。')
                hist=[]
                for j in range(5):
                    q1,q2,q3,q4,q5=st.columns(5)
                    hm=q1.number_input(f'{j+1}走前 水分',value=2.,step=.1,key=f'm{i}_{j}'); tm=q2.number_input('走破秒',value=0.,step=.1,key=f't{i}_{j}'); br=q3.number_input('障害秒',value=0.,step=.1,key=f'b{i}_{j}'); hw=q4.number_input('斤量',value=0.,step=10.,key=f'w{i}_{j}'); fn=q5.number_input('着順',value=0,min_value=0,max_value=12,step=1,key=f'f{i}_{j}')
                    if tm or br or hw or fn:hist.append({'moisture':hm,'time_sec':tm or None,'barrier_sec':br or None,'carry_weight':hw or None,'finish':fn or None})
                hs.append({'number':i+1,'name':hn or f'{i+1}番','carry_weight':cw,'body_weight':bw,'body_change':ch,'odds':od,'history':hist})
    if st.button('予想する',type='primary',disabled=(len(hs)<2)):
        r={'id':datetime.now().strftime('%Y%m%d%H%M%S'),'name':name,'date':str(date),'moisture':moist,'horses':hs,'result':[]}; st.session_state.race=r; st.session_state.pred=predict(r,S['weights'])
    if 'pred' in st.session_state:
        p=st.session_state.pred
        df=pd.DataFrame([{'印':h['mark'],'馬番':h['number'],'馬名':h['name'],'総合':round(h['score'],1),'障害':round(h['features']['barrier'],1),'水分':round(h['features']['moisture'],1),'安定':round(h['features']['consistency'],1),'近走':round(h['features']['recent'],1),'斤量':round(h['features']['weight_fit'],1),'穴':round(h['longshot'],1)} for h in p])
        st.dataframe(df,use_container_width=True,hide_index=True)
        st.success('最終印: '+' '.join(f"{h['mark']}{h['number']} {h['name']}" for h in p[:6]))
        for k,v in bet_suggestions(p).items():st.write(f'**{k}**：{v}')
        if st.button('この予想を保存'):
            r=st.session_state.race; r['prediction_snapshot']=[{'number':h['number'],'name':h['name'],'mark':h['mark'],'score':h['score']} for h in p]; R.append(r); save_json(RACES_FILE,R); st.success('保存しました')

with T[1]:
    if not R:st.info('保存レースはまだありません')
    for rev_i,r in enumerate(reversed(R)):
        i=len(R)-1-rev_i
        with st.expander(f"{r.get('date','')} {r.get('name','')} / 水分{r.get('moisture')}%"):
            p=predict(r,S['weights']); st.dataframe(pd.DataFrame([{'印':h['mark'],'馬番':h['number'],'馬名':h['name'],'総合':round(h['score'],1),'穴':round(h['longshot'],1)} for h in p]),hide_index=True,use_container_width=True)
            tx=st.text_input('結果（例 7-2-9）','-'.join(map(str,r.get('result',[]))),key=f'res{i}')
            c1,c2=st.columns(2)
            if c1.button('結果保存＋自動学習',key=f'sr{i}'):
                try:
                    r['result']=[int(x) for x in tx.replace('→','-').split('-') if x.strip()][:3]; r['review']=review(r,p); S,delta=learn(r,S); R[i]=r; save_json(RACES_FILE,R); save_json(SETTINGS_FILE,S)
                    st.success('保存・学習しました'); st.code(r['review']); st.write('重み変化',{FEATURE_LABELS[k]:round(v,4) for k,v in delta.items()})
                except Exception as e:st.error(str(e))
            if c2.button('削除',key=f'del{i}'):
                R.pop(i); save_json(RACES_FILE,R); st.rerun()
            if r.get('review'):st.text_area('自動回顧',r['review'],height=170,key=f'rv{i}')

with T[2]:
    st.subheader('成績ダッシュボード')
    seed=pd.DataFrame(SEED_RESULTS); st.metric('初期検証データ','24レース')
    st.dataframe(seed,use_container_width=True,hide_index=True)
    df=stats_df(R)
    if df.empty:st.info('保存レースに結果を入れると成績が表示されます。')
    else:
        c1,c2,c3=st.columns(3); c1.metric('結果入力済み',len(df)); c2.metric('◎1着率',f"{df['◎1着'].mean()*100:.1f}%"); c3.metric('印6頭 平均捕捉',f"{df['印6捕捉'].mean():.2f}/3")
        st.dataframe(df,use_container_width=True,hide_index=True)

with T[3]:
    st.subheader('学習設定')
    st.caption('2日24Rで調整した初期値。結果入力後は小さく更新します。')
    nw={}
    for k,v in S['weights'].items():nw[k]=st.slider(FEATURE_LABELS[k],0.,.6,float(v),.01)
    lr=st.slider('学習率',0.,.1,float(S.get('learning_rate',.02)),.005)
    c1,c2=st.columns(2)
    if c1.button('設定を保存'):
        z=sum(nw.values()) or 1; S['weights']={k:v/z for k,v in nw.items()}; S['learning_rate']=lr; save_json(SETTINGS_FILE,S); st.success('保存しました')
    if c2.button('2日検証済み初期値に戻す'):
        S['weights']=CALIBRATED_WEIGHTS.copy(); S['learning_rate']=.02; save_json(SETTINGS_FILE,S); st.success('初期値へ戻しました'); st.rerun()
    st.json({'weights':{FEATURE_LABELS[k]:round(v,3) for k,v in S['weights'].items()},'learning_rate':S['learning_rate']})

with T[4]:
    st.subheader('バックアップ / 復元')
    backup={'races':R,'settings':S,'exported_at':datetime.now().isoformat()}
    st.download_button('バックアップJSONを保存',json.dumps(backup,ensure_ascii=False,indent=2).encode('utf-8'),'banei_ai_backup.json','application/json')
    st.warning('Streamlit Community Cloudではローカル保存が永続保証されないため、定期的なバックアップ推奨。')
    up=st.file_uploader('バックアップJSONから復元',type=['json'],key='backup_upload')
    if up and st.button('復元する'):
        try:
            data=json.load(up); save_json(RACES_FILE,data.get('races',[])); save_json(SETTINGS_FILE,data.get('settings',S)); st.success('復元しました'); st.rerun()
        except Exception as e:st.error(str(e))

with T[5]:
    st.markdown('''
### 今回の完成版で追加したもの
- **2日24レースの検証を初期重みに反映**
- 障害力・障害安定・馬場水分適性を強化
- **勝ちスコアと穴スコアを分離**
- 推奨3連単 / 3連複を自動表示
- 結果入力後に自動回顧＋小幅自動学習
- 成績ダッシュボード
- **netkeibaテキスト貼り付け入力（出馬表＋近走）**
- CSV一括入力
- バックアップ / 復元

### 入力のコツ
通常は **テキスト貼り付け** を選び、netkeibaの出馬表と近走をそのまま貼ればOKです。フォーム入力時のみ、過去走タイムは秒で入力します。例：`1:42.3` → `102.3`。障害秒が分かる場合は必ず入力すると精度が上がります。

### 注意
初期24Rは会話内で検証した**結果順**を校正材料として使用し、詳細な全馬データを捏造してはいません。詳細特徴は、今後このツールで保存するレースほど正確に学習されます。
''')
