#!/usr/bin/env python3.11
"""transcribe.py <audio_or_video> --out transcript.json [--model medium --engine auto|faster|mlx --vocab vocabulary.json]
16kHz mono WAV に変換 → 単語タイムスタンプ付き書き起こし（language ja, beam 5, vad_filter, initial_prompt=語彙）。
出力 (SPEC 3.2): {"engine","model","language","audio","segments":[{"start","end","text","words":[{"w","s","e","p"}]}]}"""
import argparse, os, sys, json, platform, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, save_json, load_json, FFMPEG

MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx", "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx", "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx", "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


def to_wav16k(src, dst):
    run([FFMPEG, "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst], capture=True)


def load_vocab(path):
    """vocabulary.json: {"words":["Apple Watch",...]} または ["..."] または {"corrections":{"誤":"正"},"words":[...]}"""
    if not path or not os.path.exists(path):
        return [], {}
    v = load_json(path)
    words, corr = [], {}
    if isinstance(v, list):
        words = [str(x) for x in v]
    elif isinstance(v, dict):
        words = [str(x) for x in (v.get("words") or v.get("vocabulary") or [])]
        corr = dict(v.get("corrections") or v.get("replace") or {})
    return words, corr


def pick_engine(engine):
    if engine == "mlx":
        return "mlx"
    if engine == "faster":
        return "faster"
    # auto: Mac (Apple Silicon) で mlx_whisper が入っていれば mlx、それ以外は faster-whisper
    if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        try:
            import mlx_whisper  # noqa
            return "mlx"
        except Exception:
            pass
    return "faster"


def run_faster(wav, model, prompt, device, compute):
    from faster_whisper import WhisperModel
    if device == "auto":
        device = "cpu"
    if compute == "auto":
        compute = "int8" if device == "cpu" else "float16"
    m = WhisperModel(model, device=device, compute_type=compute, cpu_threads=max(1, os.cpu_count() or 1))
    segs, info = m.transcribe(wav, language="ja", beam_size=5, word_timestamps=True, vad_filter=True,
                              vad_parameters={"min_silence_duration_ms": 500},
                              initial_prompt=prompt or None, condition_on_previous_text=False)
    out = []
    for s in segs:
        words = [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(float(w.probability), 3)}
                 for w in (s.words or [])]
        out.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(), "words": words})
    return out


def run_mlx(wav, model, prompt):
    import mlx_whisper
    repo = MLX_MODELS.get(model, model)
    r = mlx_whisper.transcribe(wav, path_or_hf_repo=repo, language="ja", word_timestamps=True,
                               initial_prompt=prompt or None, condition_on_previous_text=False)
    out = []
    for s in r.get("segments", []):
        words = [{"w": w.get("word", ""), "s": round(float(w["start"]), 3), "e": round(float(w["end"]), 3),
                  "p": round(float(w.get("probability", 0.0)), 3)} for w in (s.get("words") or [])]
        out.append({"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3),
                    "text": str(s.get("text", "")).strip(), "words": words})
    return out


def apply_corrections(segments, corr):
    if not corr:
        return segments
    for s in segments:
        for k, v in corr.items():
            if k in s["text"]:
                s["text"] = s["text"].replace(k, v)
        for w in s["words"]:
            for k, v in corr.items():
                if k in w["w"]:
                    w["w"] = w["w"].replace(k, v)
    return segments


def main():
    ap = argparse.ArgumentParser(description="単語タイムスタンプ付き日本語書き起こし")
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="medium")
    ap.add_argument("--engine", default="auto", choices=["auto", "faster", "mlx"])
    ap.add_argument("--vocab", default=None, help="vocabulary.json")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute", default="auto")
    ap.add_argument("--keep-wav", default=None, help="変換後の16k wav を残すパス")
    a = ap.parse_args()

    words, corr = load_vocab(a.vocab)
    prompt = "、".join(words) + "。" if words else ""
    engine = pick_engine(a.engine)
    tmpdir = tempfile.mkdtemp(prefix="ytae_")
    wav = a.keep_wav or os.path.join(tmpdir, "audio16k.wav")
    t0 = time.time()
    to_wav16k(a.input, wav)
    print(f"[transcribe] engine={engine} model={a.model} wav={wav}", file=sys.stderr)
    if engine == "mlx":
        try:
            segs = run_mlx(wav, a.model, prompt)
        except Exception as e:
            print(f"[transcribe] mlx failed ({e}); fallback to faster-whisper", file=sys.stderr)
            engine = "faster"
            segs = run_faster(wav, a.model, prompt, a.device, a.compute)
    else:
        segs = run_faster(wav, a.model, prompt, a.device, a.compute)
    segs = apply_corrections(segs, corr)
    out = {"engine": "mlx-whisper" if engine == "mlx" else "faster-whisper", "model": a.model, "language": "ja",
           "audio": os.path.abspath(a.input), "vocabulary": words, "segments": segs}
    save_json(a.out, out)
    nw = sum(len(s["words"]) for s in segs)
    print(f"[transcribe] {len(segs)} segments, {nw} words, {time.time()-t0:.1f}s -> {a.out}", file=sys.stderr)
    if not a.keep_wav:
        try:
            os.remove(wav); os.rmdir(tmpdir)
        except Exception:
            pass


if __name__ == "__main__":
    main()
