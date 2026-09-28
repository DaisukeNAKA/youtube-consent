#!/usr/bin/env python3
"""measure.py <video> [--every 1.0] [--out report.json] [--sheet sheet.jpg]
参考動画/自作動画の見た目を機械計測する（1080p換算の比率で出力）:
- 字幕: 下部15%領域の白画素bbox → 字高比, 下端余白比, 中央ずれ, 横幅比
- 見出し帯: 左上(40%x22%)領域の大きな白ブロブ → 高さ比, 左余白比, 上余白比, 傾き(minAreaRect)
- 丸ワイプ: 右下/左下の円検出(Hough) → 直径比, 位置
出力は各フレームの計測と中央値。"""
import cv2, numpy as np, json, argparse, subprocess, os, tempfile
def frames(video, every):
    d=tempfile.mkdtemp(); subprocess.run(['ffmpeg','-v','error','-y','-i',video,'-vf',f'fps=1/{every}',os.path.join(d,'f_%04d.png')],check=True)
    return sorted(os.path.join(d,f) for f in os.listdir(d))
def white(img,thr=235):
    b,g,r=cv2.split(img); return ((b>thr)&(g>thr)&(r>thr)).astype(np.uint8)*255
def cap_metrics(img):
    H,W=img.shape[:2]; m=white(img); y0=int(H*0.85); sub=m[y0:,:]
    # 行ごとの白画素密度で字幕帯を見つける
    rows=(sub>0).sum(1); ys=np.where(rows>W*0.004)[0]
    if len(ys)<8: return None
    top,bot=y0+ys.min(),y0+ys.max(); xs=np.where((sub[ys.min():ys.max()+1]>0).sum(0)>0)[0]
    return {'glyph_h':float((bot-top)/H),'bottom_margin':float((H-1-bot)/H),'center_dx':float(((xs.min()+xs.max())/2-W/2)/W),'width':float((xs.max()-xs.min())/W)}
def head_metrics(img):
    H,W=img.shape[:2]; m=white(img); sub=m[:int(H*0.22),:int(W*0.45)]
    cnts,_=cv2.findContours(sub,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cnts=[c for c in cnts if cv2.contourArea(c)>H*W*0.003]
    if not cnts: return None
    c=max(cnts,key=cv2.contourArea); x,y,w,h=cv2.boundingRect(c); (cx,cy),(rw,rh),ang=cv2.minAreaRect(c)
    # 平行四辺形の傾き: 上辺と下辺の左端xの差
    pts=c.reshape(-1,2); top=pts[pts[:,1]<y+h*0.2]; botp=pts[pts[:,1]>y+h*0.8]
    skew=None
    if len(top) and len(botp):
        skew=float(np.degrees(np.arctan2((top[:,0].min()-botp[:,0].min()),h)))
    roi=img[y:y+h,x:x+w].reshape(-1,3); dark=roi[roi.sum(1)<330]
    return {'band_h':float(h/H),'band_w':float(w/W),'left':float(x/W),'top':float(y/H),'skew_deg':skew,'text_rgb':[int(v) for v in np.median(dark,axis=0)[::-1]] if len(dark) else None}
def wipe_metrics(img):
    H,W=img.shape[:2]; g=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); g=cv2.medianBlur(g,5)
    cs=cv2.HoughCircles(g,cv2.HOUGH_GRADIENT,dp=1.2,minDist=150,param1=110,param2=45,minRadius=int(H*0.06),maxRadius=int(H*0.14))
    if cs is None: return None
    out=[]
    for cx,cy,r in cs[0]:
        if cy>H*0.55 and (cx<W*0.3 or cx>W*0.7): out.append({'cx':float(cx/W),'cy':float(cy/H),'diam':float(2*r/H)})
    return out[:1] or None
def med(vals,key):
    v=[x[key] for x in vals if x and x.get(key) is not None]
    return float(np.median(v)) if v else None
ap=argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('--every',type=float,default=1.0); ap.add_argument('--out'); ap.add_argument('--sheet')
a=ap.parse_args(); fs=frames(a.video,a.every); per=[]
for f in fs:
    img=cv2.imread(f); per.append({'frame':os.path.basename(f),'caption':cap_metrics(img),'heading':head_metrics(img),'wipe':wipe_metrics(img)})
caps=[p['caption'] for p in per]; heads=[p['heading'] for p in per]
summary={'video':a.video,'n_frames':len(fs),'caption_frames':sum(1 for c in caps if c),'heading_frames':sum(1 for h in heads if h),
 'caption':{k:med(caps,k) for k in ['glyph_h','bottom_margin','center_dx','width']},
 'heading':{k:med(heads,k) for k in ['band_h','band_w','left','top','skew_deg']},
 'wipe':{k:med([p['wipe'][0] for p in per if p['wipe']],k) for k in ['cx','cy','diam']}}
print(json.dumps(summary,ensure_ascii=False,indent=1))
if a.out: json.dump({'summary':summary,'frames':per},open(a.out,'w'),ensure_ascii=False,indent=1)
if a.sheet:
    subprocess.run(['ffmpeg','-v','error','-y','-i',a.video,'-vf',f'fps=1/{a.every},scale=480:-1,tile=4x{max(1,(len(fs)+3)//4)}','-frames:v','1','-update','1',a.sheet])
