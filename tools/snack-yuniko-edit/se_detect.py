#!/usr/bin/env python3
"""原本音声に対して SE/ED 音源の出現位置を正規化相互相関で検出する。"""
import sys, os, json, numpy as np, subprocess
from scipy.signal import fftconvolve
def load(path, sr=16000):
    return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',path,'-ac','1','-ar',str(sr),'-f','f32le','-']), dtype=np.float32)
sr = 16000
src, se_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
x = load(src, sr); res = {"source": src, "len_s": len(x)/sr, "hits": {}}
for f in sorted(os.listdir(se_dir)):
    if not f.lower().endswith('.wav') or f.startswith('._'): continue
    t = load(os.path.join(se_dir, f), sr)[:int(sr*3.0)]
    t = t - t.mean(); t /= (np.linalg.norm(t) + 1e-9)
    corr = fftconvolve(x, t[::-1], mode='valid')
    energy = np.sqrt(fftconvolve(x**2, np.ones(len(t)), mode='valid') + 1e-9)
    ncc = corr / energy
    peaks = []; last = -1e9
    for i in np.where(ncc > 0.3)[0]:
        if i - last > sr:
            j = i + int(np.argmax(ncc[i:i+sr])); peaks.append({"t": round(j/sr, 2), "ncc": round(float(ncc[j]), 3)}); last = j
    top = int(np.argmax(ncc))
    res["hits"][f] = {"peaks": peaks, "max": {"t": round(top/sr, 2), "ncc": round(float(ncc[top]), 3)}}
    print(f, "max", res["hits"][f]["max"], "peaks", peaks[:30], flush=True)
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
