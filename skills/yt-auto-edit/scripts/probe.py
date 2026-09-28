#!/usr/bin/env python3.11
"""probe.py <files...> --out probe.json
ffprobe で 長さ/fps/解像度/回転/音声有無/アスペクト(16:9|9:16|other) を出す。
出力: {"files":[{...}], "primary": <最初のファイルの辞書>}"""
import argparse, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import probe_media, save_json


def main():
    ap = argparse.ArgumentParser(description="ffprobe で素材のメタ情報を集める")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    files = []
    for f in a.files:
        if not os.path.exists(f):
            print(f"[probe] not found: {f}", file=sys.stderr)
            sys.exit(2)
        d = probe_media(f)
        files.append(d)
        print(f"[probe] {os.path.basename(f)}: {d['duration']}s {d['display_width']}x{d['display_height']} "
              f"{d['fps']}fps rot={d['rotation']} audio={d['has_audio']} aspect={d['aspect']}", file=sys.stderr)
    save_json(a.out, {"files": files, "primary": files[0] if files else None})
    print(f"[probe] wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
