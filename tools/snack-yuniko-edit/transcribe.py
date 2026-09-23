#!/usr/bin/env python3
"""faster-whisper で単語タイムスタンプ付き文字起こし。出力: JSON(segments/words) と txt。"""
import sys, json, time, argparse
from faster_whisper import WhisperModel
ap = argparse.ArgumentParser()
ap.add_argument("audio"); ap.add_argument("--out", required=True)
ap.add_argument("--model", default="large-v3"); ap.add_argument("--beam", type=int, default=5)
ap.add_argument("--start", type=float, default=None); ap.add_argument("--duration", type=float, default=None)
ap.add_argument("--prompt", default="スナックゆに子。りっちゃんと中塚サンフラワーのユニコのラジオ。")
a = ap.parse_args()
t0 = time.time()
model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=4)
audio = a.audio
if a.start is not None or a.duration is not None:
    import subprocess, tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", str(a.start)] if a.start else []) + ["-i", a.audio] + (["-t", str(a.duration)] if a.duration else []) + ["-ac", "1", "-ar", "16000", tmp]
    subprocess.run(cmd, check=True); audio = tmp
segs, info = model.transcribe(audio, language="ja", beam_size=a.beam, word_timestamps=True,
                              vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                              initial_prompt=a.prompt, condition_on_previous_text=False)
out = {"language": info.language, "duration": info.duration, "segments": []}
offset = a.start or 0.0
lines = []
for s in segs:
    d = {"start": round(s.start + offset, 3), "end": round(s.end + offset, 3), "text": s.text,
         "words": [{"w": w.word, "s": round(w.start + offset, 3), "e": round(w.end + offset, 3), "p": round(w.probability, 3)} for w in (s.words or [])]}
    out["segments"].append(d)
    lines.append(f"{d['start']:8.2f} {d['end']:8.2f} {s.text.strip()}")
    print(lines[-1], flush=True)
json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(a.out.rsplit(".", 1)[0] + ".txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"done in {time.time()-t0:.1f}s for {info.duration:.1f}s audio", file=sys.stderr)
