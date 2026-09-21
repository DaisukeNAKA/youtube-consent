#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np, soundfile as sf, json
x, sr = sf.read('raw_f32.wav', dtype='float32', always_2d=True)
W = int(sr*0.05); m = x.shape[0]//W
b = x[:m*W].reshape(m,W,2).astype(np.float64)
db = 20*np.log10(np.sqrt((b**2).mean(axis=1))+1e-12)
R = {}
# --- 回り込み量: 一方が主で話しているときの他方との差
for t,o in ((0,1),(1,0)):
    sel = (db[:,t] > -30) & (db[:,t]-db[:,o] > 0)
    R[f"bleed_ch{t}_talking"] = {"median_separation_db": round(float(np.median(db[sel,t]-db[sel,o])),1),
                                 "p25": round(float(np.percentile(db[sel,t]-db[sel,o],25)),1),
                                 "p75": round(float(np.percentile(db[sel,t]-db[sel,o],75)),1),
                                 "n": int(sel.sum())}
# --- どちらも話していない区間の割合と、同時発話率
both = (db[:,0] > -32) & (db[:,1] > -32)
R["overlap_pct"] = round(float(both.mean()*100),1)
# --- 歪み: 有声音の高次倍音エネルギー比を、レベル帯別に比較
def harmonic_noise_ratio(seg, sr):
    """基本周波数を推定し、倍音間に落ちるエネルギー（=歪み・雑音）の比率を返す"""
    seg = seg - seg.mean()
    win = seg*np.hanning(len(seg))
    sp = np.abs(np.fft.rfft(win, 4*len(win)))**2
    fr = np.fft.rfftfreq(4*len(win), 1/sr)
    band = (fr>70)&(fr<400)
    if not band.any(): return None
    # 自己相関でF0
    ac = np.fft.irfft(np.abs(np.fft.rfft(win, 2*len(win)))**2)[:len(win)]
    lo,hi = int(sr/400), int(sr/70)
    if hi>=len(ac): return None
    f0 = sr/ (lo+int(np.argmax(ac[lo:hi])))
    if not (70 < f0 < 400): return None
    tot = sp[(fr>f0*0.5)&(fr<5000)].sum()
    if tot<=0: return None
    harm = 0.0
    k=1
    while f0*k < 5000:
        q=(fr>f0*k-f0*0.15)&(fr<f0*k+f0*0.15)
        harm += sp[q].sum(); k+=1
    return float(10*np.log10(max(tot-harm,1e-20)/max(harm,1e-20))), f0
for c in (0,1):
    s = x[:,c].astype(np.float64)
    res={}
    for lo,hi in ((-34,-28),(-28,-24),(-24,-20),(-20,-17),(-17,-14),(-14,-11)):
        q=np.where((db[:,c]>=lo)&(db[:,c]<hi)&(db[:,c]-db[:,1-c]>10))[0]
        if len(q)<40: continue
        vals=[]
        for k in q[::max(1,len(q)//300)]:
            r = harmonic_noise_ratio(s[k*W:(k+1)*W], sr)
            if r: vals.append(r[0])
        if len(vals)>=25:
            res[f"{lo}..{hi}"]={"n":len(vals),"inharmonic_to_harmonic_db":round(float(np.median(vals)),2)}
    R[f"distortion_ch{c}"]=res
print(json.dumps(R, ensure_ascii=False, indent=1, default=float))
