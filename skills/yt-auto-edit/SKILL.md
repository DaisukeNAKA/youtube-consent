---
name: yt-auto-edit
description: 撮ったままの動画（人物・画面収録・別録り音声）をパスで受け取り、字幕・見出し・丸ワイプ入りのYouTube横動画(16:9)とSRT・検品結果を作る。トリガー語:「YouTube編集」「YouTube動画にして」「本編を作って」「40秒の試作」「プランB」「プランA/C」「前回と同じ設定で」「◯分◯秒の字幕を直して」「丸ワイプを小さめに」「サムネの指示を書いて」。編集ソフト不要。Claude Code / Codex 両対応、Mac(mlx_whisper)/Windows・Linux(faster-whisper)。
---

# yt-auto-edit — 撮ったままの動画を YouTube 横動画にする（v2）

このスキルは「素材のパス」と「出力先」を受け取り、次を作る。

- `YouTube_本編_1080p.mp4`（16:9。4K 出力なら `YouTube_本編_4K.mp4`。白い1行字幕・左上の斜め見出し帯・**左下**の丸ワイプ）
- `字幕.srt`（YouTube Studio にそのまま読み込める。焼き込み字幕とは**別に** `make_srt.py` が文単位で作る）
- `qc_report.md`（自動検品: 字数・表示時間・音量・映像の途切れ・**口元同期ずれ**）
- `settings.json`（見た目・配置の永続化。次回「前回と同じ設定で」）
- おまけ: `タイトル案.md` / `概要欄.md` / `Codex_アップロード指示.txt` / `サムネ指示.md`

**編集スタイルは1種類だけ**（字幕: 白・1行・句読点なし・縁取りなし＋影／見出し: 左上の白い斜め帯／丸ワイプ: 左下）。言葉で変えられるのは「丸ワイプの位置と大きさ」「字幕の色・縁取り」「見出し帯の左右・角丸」「帯と文字の色」「画面収録の配置プリセット」のみ。凝った演出は受けない（→ 12. 標準外）。

> Brain の説明文は「右下の丸ワイプ」だが、本人の実動画（4K/1080p とも）は**左下**（円中心 W×0.085, H×0.72）。既定は実動画に合わせて左下。ユーザーが「右下に」と言えば `wipe.position` を変える。

---

## 0. 最初に決める変数（すべての工程で使う）

```bash
SKILL="$HOME/.claude/skills/yt-auto-edit"   # このスキルの置き場所（Codex なら ~/.codex/skills/yt-auto-edit 等。README 参照）
PY=python3.11                                # check_env.sh が「実行時は PYTHON=…」と表示したもの。無ければ python3
OUT="/Users/xxx/Movies/20260928_AppleWatchUltra"   # 出力先（プロジェクトフォルダ）。命名は YYYYMMDD_題名
W="$OUT/work"                                 # 中間ファイル置き場
CAMERA="/path/to/人物.MOV"                     # 主素材（必須。人物 or 音声つき動画）
SCREEN="/path/to/画面収録.mov"                  # 任意
AUDIO="/path/to/別録り.wav"                     # 任意
```

**プロジェクトフォルダの命名**: `YYYYMMDD_題名`（例 `20260928_AppleWatchUltra`、`20260928_三角関数講義`）。ユーザーが出力先を指定しなければ、素材と同じ階層にこの名前で作る。題名は撮影日と主題が一目で分かる 4〜12 文字。空白は使わない。

**パスの扱い（Claude Code / Codex 共通）**
- Finder「パス名をコピー」で貼られるパスには空白・日本語・`[ ]` が入る。シェルでは必ず `"$CAMERA"` のように**二重引用符**で囲む。ワイルドカード展開を避けるため `[wght]` を含むフォント名なども引用符で囲む。
- Windows で `C:\Users\...` が来たら、WSL では `/mnt/c/Users/...` に直す（`wslpath -u 'C:\Users\...'`）。PowerShell 上では実行しない（WSL2 または Git Bash を使う）。
- `~` は引用符の中では展開されないので、`"$HOME/..."` に置き換える。
- 出力先が存在しなければ `mkdir -p "$W"`。既存の `work/` があれば「前回の続きか、作り直しか」を確認する。
- 中間ファイルは `OUT/work` に置き、成果物は `OUT/01_試作` と `OUT/02_完成版` に分ける（→ 9. 成果物一覧）。

---

## 1. 環境チェック（初回のみ／エラーが出たとき）

```bash
bash "$SKILL/scripts/check_env.sh"
```

- 終了コード 0 なら次へ。1 なら画面に出た「不足分のインストール」ブロックを**そのままユーザーに提示**し、実行を頼む（`sudo` や `brew install` は勝手に実行しない）。
- Mac (Apple Silicon): `brew install ffmpeg node python@3.11`、`pip install mlx-whisper`、`cd "$SKILL/remotion" && npm install`。
- Windows: WSL2 + Ubuntu 推奨。`sudo apt-get install -y ffmpeg`、Node 22（nodesource）、`pip install faster-whisper`。ネイティブ Windows なら `winget install Gyan.FFmpeg OpenJS.NodeJS.LTS Python.Python.3.11`。
- Linux/コンテナで GPU が無いとき: `export REMOTION_BROWSER=<chromium headless_shell のパス>`（render.sh が `--browser-executable` に渡す）。
- 2回目以降は `check_env.sh` を省略してよいが、`transcribe.py` / `render.sh` が失敗したらまずここに戻る。

---

## 2. 素材の受領と確認

ユーザーから受け取るもの: 素材パス（人物／画面収録／別録り音声のうち手元にあるもの）、出力先、希望プラン（A/B/C。未指定なら B を提案）。

```bash
mkdir -p "$W"
$PY "$SKILL/scripts/probe.py" "$CAMERA" "$SCREEN" "$AUDIO" --out "$W/probe.json"   # 存在するファイルだけ渡す
```

`probe.json` で確認して、ユーザーに1〜2行で報告する:
- `duration`（長さ）, `fps`, `display_width/height`, `aspect`（`16:9` / `9:16` / `other`）, `rotation`。
- **fps の正規化**: 出力は既定 30fps（`settings.fps`）。画面収録は 60fps（Mac の画面収録・iPhone）で来ることが多いが、`cut_media.py` が `screen_cut.mp4` を出力タイムラインの fps（カメラ素材に追従、通常 30/29.97）に揃えるので、事前変換は不要。カメラが 60fps のときは `cut_media.py --fps 30` で固定するか、`settings.fps: 30` のまま `build_timeline.py --fps 30`（レンダー負荷が半分になる）。
- **回転メタデータの正規化**: スマホ・一眼を逆さま／縦向きに固定して撮った素材は `rotation` に 90/180/270 が入る（「上下逆さま」= 180）。`cut_media.py` が ffmpeg の autorotate で映像に焼き込み、出力には `rotate=0` を付けるので、そのまま渡してよい。`display_width/height` は回転後の値。probe で `rotation: 180` なのに映像がまだ逆さまなら、素材のメタデータが壊れているので `ffmpeg -i in.MOV -vf "vflip,hflip" -c:a copy fixed.MOV` で直してから渡す。
- 縦素材（9:16）なら「縦動画は高さいっぱい中央配置、背景は**濃紺 #101627**（`vertical_source.background: navy` 既定。ぼかし `blur` は代替）」で作ると伝える。
- 4K 入力でも既定は 1080p 出力。4K が欲しいと言われたら `settings.resolution: "4K"`（完成版は `YouTube_本編_4K.mp4` になる）。
- `.LRF`（DJI の低解像度プロキシ）や `.HEIC` は素材として使わない。同名の `.MP4` / `.jpg` を探す。

**同期（素材が2つ以上あるとき。1つでも実行して sync.json を作る）**

```bash
$PY "$SKILL/scripts/sync.py" --camera "$CAMERA" --screen "$SCREEN" --audio "$AUDIO" --out "$W/sync.json"
# 無いものは引数ごと省く。ズレの上限が分かるなら --max-lag 30
```

- `screen_offset` / `audio_offset` は「カメラ時刻 t に対応するそのファイルの時刻 = t + offset」。以降の `src_*` は**すべてカメラ時刻**で書く。
- 相関が弱い（sync.py が stderr に出す `score=` が 0.3 未満）ときは、両方の音声にある「手を叩く音」「最初の一言」を聞いて手で確認し、必要なら `sync.json` の offset を手で直す。

---

## 3. 文字起こし

```bash
$PY "$SKILL/scripts/transcribe.py" "$CAMERA" --out "$W/transcript.json" --model medium --vocab "$SKILL/vocabulary.json"
# 別録り音声の方が音が良いなら "$AUDIO" を渡す（その場合 sync.json の audio_offset 分だけ時刻がずれるので、
# transcript の時刻をカメラ基準に直す: s - audio_offset。迷ったらカメラの音声で起こす）
```

- エンジンは自動選択（Mac Apple Silicon + mlx_whisper があれば `mlx`、それ以外は `faster`）。手動なら `--engine faster|mlx`。
- モデル: 既定 `medium`。試作を急ぐなら `small`、固有名詞が多いなら `large-v3`（Mac なら `large-v3-turbo`）。
- `vocabulary.json` に固有名詞（`words`）と誤変換の直し（`corrections`）を入れておくと initial_prompt と置換に使われる。**新しい固有名詞や誤変換に気づいたら、その場で追記する**（README「辞書の育て方」）。
- 出力 `transcript.json`: `segments[].{start,end,text,words[].{w,s,e,p}}`。`p`（確信度）が低い語は字幕確認のときに重点的に見る。
- `transcript.json` は「補正後の全文（句読点あり・フィラーあり）」として SRT の元にもなる（→ 5章）。誤変換に気づいたら `transcript.json` の `text`/`words[].w` を直す（`corrections` に入れて transcribe をやり直してもよい）。

---

## 4. カット候補と編集方針（edit_plan.json）— エージェントの判断が要る工程

```bash
[ -f "$W/settings.json" ] || cp "$SKILL/settings.default.json" "$W/settings.json"
$PY "$SKILL/scripts/plan_cuts.py" --transcript "$W/transcript.json" --audio "$CAMERA" --settings "$W/settings.json" --out "$W/cuts_auto.json"
```

`cuts_auto.json` には `silences`（無音）、`keep_auto`（無音>1.0s を 0.5s に詰めた採用区間）、`filler_candidates`（えー/えっと/あの/まあ/なんか）、`retake_candidates`（同じ言い回しの繰り返し=言い直し）が入る。**これは候補**。エージェントが `transcript.json` を通読し、以下の基準で `edit_plan.json` を確定する。

### 4.1 除外する区間（keep から外す）
| 種類 | 見つけ方 | 扱い |
|---|---|---|
| 言い直し | `retake_candidates`、または直前とほぼ同じ文が続く | **前の言い方を捨て、後の言い方を残す**（最後に言った方が完成形） |
| フィラー | `filler_candidates`（文頭の えー/えっと/あの/まあ/なんか） | `cuts.remove_fillers: true` なら外す。文中の「なんか」「まあ」は意味を持つことがあるので残す |
| 準備時間 | 冒頭・末尾の無音、カメラ操作音、「よし」「じゃあ始めます」「録れてるかな」 | 冒頭は**最初の本題の一言から**、末尾は最後の言葉の直後 +0.3s で切る |
| 来客・電話・通知 | 「ちょっと待って」「はい、もしもし」「すみません」＋長い無音、別人の声 | 前後まとめて外す。復帰後の「えー、で、」も外す |
| 雑談・脱線 | 話題の見出しに入らない話が 15 秒以上続く | 外す。ただし本題への橋渡しになる 1 文は残す |
| 沈黙 | `silences` | >1.0s は自動で 0.5s に詰まる。考え込みの「…」が 3 秒以上なら区間ごと外す |
| 失敗テイク | 「もう一回」「やり直し」「カット」 | その発言と直前の失敗部分を外す |

- `keep` は**昇順・非重複**の `{src_start, src_end}` 配列。区間の境目は単語境界（`words[].s/e`）に合わせ、前後に 0.1〜0.2s の余裕を持たせる（語尾が切れるのを防ぐ）。
- 迷ったら**残す**。試作で確認してもらえる。
- **映像は残すが字幕だけ出したくない区間**（相槌・笑い・「はい」「うん」だけの間、映像で見せたい間）は keep から外さず `caption_mute[]` に書く（→ 4.6）。フィラー・相槌として自動で落とした語の発話中も字幕は出ない（前のキューを伸ばして埋めない: `caption.no_fill_over_dropped`）。

### 4.2 見出し（headings）— 話題の切れ目ごとに1本
- 切れ目の見つけ方: 「次に」「で、もう一つ」「じゃあ実際に」などの転換語、話題の名詞が変わる場所、画面収録に切り替わる場所。
- 見出し文: **6〜14文字**の体言止め／短文。例: `実物はこんなに小さい` `元素材は7分の撮りっぱなし` `三角関数の講義を作ってみた` `中学生でも分かるレベル` `テスト動画`。
  - 話者の言葉をそのまま縮める（言い換えすぎない）。数字・英字は半角。句読点なし。「〜について」「〜の話」は削る。
  - 1本の帯は **20秒〜2分**表示。10秒未満の話題は前後に吸収する。本編 5 分で 3〜6 本が目安。
  - 冒頭の挨拶（0〜数秒）に帯は不要。最初の本題から出す。
- `headings[].src_start/src_end` はカメラ時刻。keep の外にはみ出してよい（build_timeline が出力時刻に写像し、切り落とす）。
- 帯は**画面収録の区間中も出たまま**（`heading.show_during_screen: true` 既定。本人動画で確認）。画面の上端と帯が重なるのが嫌なら false。
- 帯の見た目（既定）: 白い平行四辺形、帯ごと `skewX(-8.5°)`（文字も傾く擬似斜体）、文字色 `#182028`、左からスライドイン 0.25s、アウトは即消え。`shape: "rounded"` にすると角丸 20px・文字直立・文字色 `#000`・アニメなし（carley 型）。
- プラン A では headings を空にする（付けたいときは 1〜2 本まで）。

### 4.3 画面収録を出す区間（screen）と丸ワイプ
- `screen[]` は「画面収録をインセット表示する」区間。**その間だけ丸ワイプ**（プラン B/C で自動）。
- インセットのプリセット `screen.preset`:
  - `author`（既定。本人動画）: 濃紺 `#101627` 背景に幅 W×0.875、上余白 H×0.028、左端 W×0.092（**中央ではない**。右に寄っている）、角丸 12px。
  - `takkatw`: 幅 W×0.743、上余白 40px、**中央**配置、角丸なし。
- 出すのは「操作している／画面の文字を読ませたい」場面のみ。目安: 話者が「ここを押すと」「この画面で」「見てください」と言った 1 秒前から、その話題が終わるまで。
- 画面の文字が読めないほど小さい（1080p で 20px 未満）場合は、その区間を短くして声で説明させるか、ユーザーに「拡大した収録」を頼む。
- 画面収録が無いのに `screen` を書かない。`SCREEN` が無ければ `screen: []`。
- 丸ワイプ（既定）: 左下、円中心 (W×0.085, H×0.72)、直径 H×0.22（小さめ 0.16）、縁なし、出始め 0.2s フェードイン。中身はカメラ映像を `wipe.focus` を中心に円形クロップ。

### 4.4 プランの選び方
| プラン | 選ぶ条件 | headings | screen / 丸ワイプ |
|---|---|---|---|
| **A シンプルトーク** | 画面収録が無い／人物と声が中心（レビュー・体験談・雑談） | 0〜2 本 | 画面は必要な場面だけ。丸ワイプなし |
| **B 見出し付き解説**（既定） | 話題が 3 つ以上／解説・講座・レビュー＋操作あり | 話題ごと | 操作中だけ画面＋丸ワイプ |
| **C 画面実演＋丸ワイプ** | 全体の 6 割以上が操作画面（チュートリアル・デモ） | 話題ごと（任意） | ほぼ全編画面。画面中は常に丸ワイプ |

ユーザーが指定しないときは B を提案し、理由を 1 行添える。

### 4.5 写真・スクショ（v5 B ロール、任意）
`broll[]`: `{"file":"…png","src_start":50.0,"src_end":56.0,"kind":"vertical|photo|web"}`。
- `vertical`（縦長スクショ／SNS 投稿）: 話者を左 W×0.40 に、右側に角丸 30px・影付きのカードを中心 (0.70W, 0.51H)・最大高 0.62H で**静止**表示（拡大しない）。
- `photo`（縦写真）: 全画面すりガラス上に中央配置し、ゆっくり拡大 1.00→1.06（拡大は `photo` だけ: `broll.zoom_kinds`）。
- `web`（Web ページ画像）: ページ背景色のまま全画面。
- 切り替えは**レイアウト全体のディゾルブ 0.33s**（`broll.transition: dissolve`, `duration: 0.33`）。表示は 4〜8 秒、話者がその画像に言及している間だけ。

### 4.6 書く
```jsonc
// $W/edit_plan.json
{"plan":"B",
 "keep":[{"src_start":3.2,"src_end":45.0},{"src_start":47.5,"src_end":120.0}],
 "headings":[{"text":"実物はこんなに小さい","src_start":3.2,"src_end":45.0}],
 "screen":[{"src_start":20.0,"src_end":35.0}],
 "broll":[],
 "caption_mute":[{"src_start":60.0,"src_end":63.5}],   // 映像は残すが字幕を出さない区間（カメラ時刻）
 "caption_overrides":[],
 "notes":"冒頭0-3.2sは準備時間、45-47.5sは言い直し（後を採用）、60-63.5sは笑いのみ→字幕なし"}
```
`notes` に「何を・なぜ外したか」を残す（試作の説明とユーザーの修正に使う）。`caption_mute` は焼き込み字幕にだけ効く（SRT は全文が原則。SRT からも落とすなら `make_srt.py --apply-mute`）。

---

## 5. 40秒の試作（「まず40秒の試作を作って」）

```bash
[ -f "$W/settings.json" ] || cp "$SKILL/settings.default.json" "$W/settings.json"
$PY "$SKILL/scripts/captions.py"       --transcript "$W/transcript.json" --plan "$W/edit_plan.json" --settings "$W/settings.json" --out "$W/captions.json"
$PY "$SKILL/scripts/make_srt.py"       --transcript "$W/transcript.json" --plan "$W/edit_plan.json" --settings "$W/settings.json" --out "$W/字幕.srt" --limit-seconds 40
$PY "$SKILL/scripts/cut_media.py"      --plan "$W/edit_plan.json" --sync "$W/sync.json" --settings "$W/settings.json" --workdir "$W" --limit-seconds 40
$PY "$SKILL/scripts/build_timeline.py" --plan "$W/edit_plan.json" --captions "$W/captions.json" --settings "$W/settings.json" --probe "$W/probe.json" --sync "$W/sync.json" --out "$W/timeline.json" --limit-seconds 40
mkdir -p "$OUT/01_試作"
bash "$SKILL/scripts/render.sh" "$W" "$OUT/01_試作/試作_40秒.mp4"
cp "$W/字幕.srt" "$OUT/01_試作/字幕.srt"
$PY "$SKILL/scripts/qc.py" --timeline "$W/timeline.json" --video "$OUT/01_試作/試作_40秒.mp4" --captions "$W/captions.json" --settings "$W/settings.json" \
  --source "$CAMERA" --plan "$W/edit_plan.json" --cut-media "$W/cut_media.json" --sync "$W/sync.json" --out "$OUT/01_試作/qc_report.md"
```

- `--limit-seconds 40` は「keep の先頭から 40 秒」。冒頭が挨拶だけなら、見出し・画面・丸ワイプが 1 回ずつ入る区間になるよう keep の並びを一時的に工夫してもよい（ただし本編では元に戻す）。
- captions.py は全尺で作ってよい（試作の切り出しは cut_media / build_timeline 側が行う）。
- **焼き込み字幕と SRT は別物**:
  - `captions.json`（焼き込み）= 1行・句読点なし・冗長語なし・最短 0.6s。`captions.py` が作る。
  - `字幕.srt`（YouTube にアップする字幕）= 補正後 `transcript.json` の**文単位・句読点あり・冗長語あり**を、keep 区間だけ出力時刻に写像したもの。`make_srt.py` が作る。試作では `--limit-seconds 40` を付ける。`captions.py --srt` は互換用で、正式な SRT は `make_srt.py`。
- **処理時間の目安**（Brain の実測: 試作 4〜22 分、本編 9〜48 分。素材の長さ・Mac の世代・Whisper のモデルで変わる）。この 4 コア CPU 環境では render だけで 40 秒 ≈ 2〜4 分。始める前に「◯分ほどかかります」と伝える。`REMOTION_CONCURRENCY=2` で落ち着かせられる。
- 1 回のやり直しは工程 5 全体を再実行（captions → make_srt → cut_media → build_timeline → render）。edit_plan だけ直したときも同じ。

---

## 6. 試作の確認観点（ユーザーに提示する 4 つ）

試作ができたら、パスと一緒に**この 4 点だけ**確認を頼む（長い説明は不要）:

1. **声と口元の同期** — ズレていれば sync.json の offset を ±0.05〜0.2s 直して再レンダー（`audio_offset` を増やすと音が遅れる）。`qc_report.md` の「口元同期ずれ」（|ずれ| > 0.04s で警告）も見る。
2. **字幕の正誤** — 誤変換・固有名詞。直し方は「◯分◯秒の字幕を△△に」。
3. **画面の文字が読めるか** — 読めなければ画面区間を短くする／収録の拡大を頼む／`screen.preset: takkatw`（幅は狭いが中央）ではなく `author`（幅 87.5%）にする。
4. **丸ワイプが邪魔でないか** — 邪魔なら「小さめ」「右下」。

あわせて `qc_report.md` の NG 行（字数超過・短すぎる表示・音量の逸脱・黒フレーム・同期ずれ）を要約して添える。

---

## 7. 言葉での修正の受け方（→ settings / edit_plan への写像）

修正は**ファイルを開かせず**、言葉で受けて自分で反映する。反映したら工程 5 を再実行。

| ユーザーの言い方 | 反映先 | 値 |
|---|---|---|
| 「◯分◯秒の字幕を△△に」「◯秒のところ、××じゃなくて△△」 | `edit_plan.caption_overrides[]` | `{"out_time": 秒, "text": "△△"}`（動画上の時刻）。素材時刻で言われたら `{"src_time": 秒, "text": "△△"}`。SRT にも反映したいなら `transcript.json` の該当語も直す |
| 「◯秒の字幕を消して」 | `caption_overrides[]` | `{"out_time": 秒, "text": ""}`（空文字＝削除） |
| 「◯分◯秒〜◯分◯秒は字幕なしで」「ここは字幕出さないで」 | `edit_plan.caption_mute[]` | `{"src_start": 秒, "src_end": 秒}`（カメラ時刻に直す。映像はそのまま） |
| 「△△は毎回××に直して」「△△は固有名詞」 | `vocabulary.json` | `corrections["△△"]="××"` / `words[]` に追加 → transcribe からやり直すか、captions 以降だけ再実行して overrides で当てる |
| 「字幕を短めに」「1行が長い」 | `settings.caption.max_chars` | 18 → 14〜16 |
| 「字幕を大きく／小さく」 | `settings.caption.size_ratio` | 0.048 → 0.056 / 0.042 |
| 「字幕を黄色に」「字幕の色を◯◯に」 | `settings.caption.color` | `#FFE500`（黄）/ 指定色の HEX |
| 「字幕に縁取りを」「黒い縁を付けて」 | `settings.caption.style` | `"outline"`（黒縁 H×0.004＋影）。戻すなら `"shadow"`（縁なし＋影、既定） |
| 「字幕をもう少し上に」 | `settings.caption.bottom_ratio` | 0.069 → 0.09 |
| 「丸ワイプを小さめに」/「標準に戻して」 | `settings.wipe.size` | `"small"` / `"standard"` |
| 「丸ワイプを右下に」「左下に戻して」 | `settings.wipe.position` | `"bottom-right"` / `"bottom-left"`（既定）。`top-left`/`top-right` も可。中心座標は左右・上下に鏡映される |
| 「丸ワイプの顔がずれてる」 | `settings.wipe.focus` | `{"x":0.5,"y":0.35}` を顔の位置（0〜1）に |
| 「画面収録を中央に」「takkatw みたいに」 | `settings.screen.preset` | `"takkatw"`（幅 74%・中央・角丸なし）。戻すなら `"author"`（幅 87.5%・左寄せ・角丸 12px） |
| 「画面収録中は見出しを消して」 | `settings.heading.show_during_screen` | `false` |
| 「見出し帯を右に」「左に戻して」 | `settings.heading.position` | `"top-right"` / `"top-left"` |
| 「帯を角丸に（文字は直立）」「斜めやめて」 | `settings.heading.shape` | `"rounded"`（角丸 20px・文字直立・文字色 #000・アニメなし）。戻すなら `"skew"` |
| 「帯の傾きを弱く／強く」 | `settings.heading.skew_deg` | -8.5 → -5 / -12 |
| 「帯の色を◯◯に」「帯の文字を白に」 | `settings.heading.band_color` / `text_color` | HEX |
| 「見出しの文言を△△に」「◯分◯秒からの見出しを△△に」 | `edit_plan.headings[].text` | 該当帯の text を差し替え（範囲もずらせる） |
| 「◯分◯秒〜◯分◯秒は画面を出して／出さないで」 | `edit_plan.screen[]` | 区間の追加／削除（src 時刻に直して書く） |
| 「◯分◯秒のところカットして」「ここは要らない」 | `edit_plan.keep[]` | 区間を分割して外す。`notes` に理由を追記 |
| 「縦動画の背景をぼかしに」 | `settings.vertical_source.background` | `"blur"`（既定は `"navy"`） |
| 「写真の切り替えをパッと」 | `settings.broll.transition` | `"none"`（既定はディゾルブ 0.33s） |
| 「無音の詰めを弱く」「間を残して」 | `settings.cuts.silence_threshold` / `silence_keep` | 1.0/0.5 → 1.5/0.8 |
| 「フィラーは残して」 | `settings.cuts.remove_fillers` | `false` |
| 「音が小さい／大きい」 | `settings.audio.lufs` | -14 → -13 / -16（YouTube 基準は -14） |
| 「4Kで」 | `settings.resolution` | `"4K"`（比率で保持されるので見た目は同じ。完成版名は `YouTube_本編_4K.mp4`） |
| 「前回と同じ設定で」 | 前回の `02_完成版/settings.json` を `$W/settings.json` にコピー | — |

- 「◯分◯秒」は**試作動画上の時刻**（`out_time`）として受ける。`captions.json` の `cues[]` から該当キューを引き、`src_start` も控えておく。
- settings.json は既定値との**差分だけ**書いてもよい（読み込み時に `settings.default.json` とマージされる。旧 v1 のキーだけの settings.json でも v2 の既定が補われて動く）。
- 対応できない要望（帯の形を増やす、字幕 2 行、アニメーション追加、BGM）は「このスキルでは 1 種類のスタイルだけ」と伝え、代替（色・位置・大きさ）を提案する。

---

## 8. 本編（「この設定で本編を作って」）

```bash
FINAL="YouTube_本編_1080p.mp4"   # settings.resolution が "4K" なら YouTube_本編_4K.mp4
$PY "$SKILL/scripts/captions.py"       --transcript "$W/transcript.json" --plan "$W/edit_plan.json" --settings "$W/settings.json" --out "$W/captions.json"
$PY "$SKILL/scripts/make_srt.py"       --transcript "$W/transcript.json" --plan "$W/edit_plan.json" --settings "$W/settings.json" --out "$W/字幕.srt"
$PY "$SKILL/scripts/cut_media.py"      --plan "$W/edit_plan.json" --sync "$W/sync.json" --settings "$W/settings.json" --workdir "$W"
$PY "$SKILL/scripts/build_timeline.py" --plan "$W/edit_plan.json" --captions "$W/captions.json" --settings "$W/settings.json" --probe "$W/probe.json" --sync "$W/sync.json" --out "$W/timeline.json"
mkdir -p "$OUT/02_完成版"
bash "$SKILL/scripts/render.sh" "$W" "$OUT/02_完成版/$FINAL"
cp "$W/字幕.srt" "$OUT/02_完成版/字幕.srt"
cp "$W/settings.json" "$OUT/02_完成版/settings.json"
$PY "$SKILL/scripts/qc.py" --timeline "$W/timeline.json" --video "$OUT/02_完成版/$FINAL" --captions "$W/captions.json" --settings "$W/settings.json" \
  --source "$CAMERA" --plan "$W/edit_plan.json" --cut-media "$W/cut_media.json" --sync "$W/sync.json" --out "$OUT/02_完成版/qc_report.md"
```

- 本編は `--limit-seconds` 無し。処理時間は Brain 実測で 9〜48 分（10 分の素材、4 コア CPU の render ≈ 20〜40 分）。先に「◯分かかります」と伝え、バックグラウンドで回す。
- 一括で回したいときは `bash "$SKILL/scripts/run_pipeline.sh" --camera "$CAMERA" --screen "$SCREEN" --out "$OUT" --settings "$W/settings.json" --plan "$W/edit_plan.json"`（`--limit 40` で試作）。完成版名・SRT・QC の引数は上と同じものが使われる。ただし edit_plan の判断は必ず自分で行う。
- `qc_report.md` に NG があれば、直せるもの（字数超過→caption_overrides で分割、音量→lufs、同期ずれ→sync.json の offset）を直して再レンダーし、直せないもの（素材由来の黒フレーム等）はユーザーに報告する。

---

## 9. 成果物一覧（ユーザーに返す形）

```
OUT/  （= YYYYMMDD_題名）
├─ 01_試作/ 試作_40秒.mp4, 字幕.srt, qc_report.md
├─ 02_完成版/ YouTube_本編_1080p.mp4（4K なら YouTube_本編_4K.mp4）, 字幕.srt, settings.json, qc_report.md,
│            タイトル案.md, 概要欄.md, Codex_アップロード指示.txt, サムネ指示.md
└─ work/ probe.json, sync.json, transcript.json, cuts_auto.json, edit_plan.json,
         captions.json, timeline.json, cut.mp4, cut_media.json, screen_cut.mp4（中間。消してよい）
```

最後の報告は「成果物のパス／長さ／カットした量（素材 7:12 → 本編 4:48）／QC の要点／字幕は最後に通しで確認してほしい旨」の 5 行以内。

---

## 10. 自動検品（QC）の見方

`qc.py` が確認するのは機械的なものだけ:
- 字幕: 字数（max_chars 超過）、表示時間（min_dur 0.6s 未満 / max_dur 超過）、キューの重なり、字幕のカバー率。
- 音量: 統合ラウドネス I = -14 ± 1 LUFS、トゥルーピーク TP ≤ -1.0 dBTP（AAC の峰超過 +0.1 dB は許容）。**LRA は表示のみで合否に使わない**。
- 映像: 黒フレーム、フリーズ、映像と音声の尺一致。
- **口元同期ずれ**（`--source` と `--plan` を渡したとき）: keep 区間ごとに出力音声と素材音声のエンベロープ相互相関でカット由来のずれを推定し、|ずれ| > 0.04s を警告。出たら `render.sh` の既定 `RENDER_AUDIO=mux`（音声は cut.mp4 を無変換多重化）になっているか、sync.json の offset を疑う。

**字幕の文章が全部正しいか・通しで違和感がないかは保証しない**。必ず「最後にご自身で通しで確認してください」と添える。

---

## 11. タイトル案・概要欄・アップロード指示文・サムネ指示

本編ができたら `templates/` を元に 4 ファイルを `02_完成版/` に書く。

- `タイトル案.md`: 5 案（数字・断定・ネガ/ポジ対比・疑問・体験型）。headings と冒頭 30 秒の字幕から作る。
- `概要欄.md`: 要約 3 行 → 目次（`timeline.json` の `headings[].start` を `mm:ss` に。先頭は `00:00`）→ リンク枠（URL はユーザーから受け取ったもののみ）→ ハッシュタグ 3〜5 個。テンプレの HTML コメントは削除する。
- `Codex_アップロード指示.txt`: テンプレの `{{…}}` を埋める（チャンネル名/ID、動画パス `02_完成版/YouTube_本編_1080p.mp4`、選んだタイトル、概要欄パス、SRT パス、サムネパス、公開設定=非公開、収益化=前回と同じ、Spotify=下書き）。ユーザーはこれを Codex に貼ってアップロードを頼む。Claude 側で頼まれたら Computer Use / Claude in Chrome / MCP で同じ内容を実行する（公開ボタンは押さない）。
- `サムネ指示.md`（`templates/サムネ指示.md`）: サムネ候補 5 型（01 Greg 型=顔大＋見出し 3〜6 字＋黄色帯／02 数字ドン／03 ビフォーアフター／04 物体クローズ／05 テキスト主体）を**画像生成 AI に貼る指示文**として埋める。顔写真は本編の `cut.mp4` から表情の良いフレームを `ffmpeg -ss <秒> -i "$W/cut.mp4" -frames:v 1 "$OUT/02_完成版/サムネ用_顔.png"` で切り出して添える。見出し語は headings / タイトル案から 3〜6 字に詰める。サムネの生成そのものは標準外（→ 12）。

---

## 12. 標準工程に含まれないもの

BGM・効果音・図解・サムネイル生成・ダイジェスト（ショート）・YouTube へのアップロードは**このスキルの外**。頼まれたら「スキル標準外だが別対応できる」と伝えて個別に行う（サムネは `サムネ指示.md` を画像生成 AI に貼る、ショートは別スキル、アップロードは Codex 推奨／Claude なら Computer Use・Claude in Chrome・MCP）。勝手に付け足さない。

---

## 13. Claude Code / Codex、Mac / Windows の差

| 項目 | Claude Code | Codex |
|---|---|---|
| スキルの置き場 | `~/.claude/skills/yt-auto-edit` または `<project>/.claude/skills/yt-auto-edit` | `~/.codex/skills/yt-auto-edit`、または AGENTS.md から `SKILL.md` を参照 |
| 実行 | Bash ツールで上のコマンドをそのまま | シェル実行で同じ。長い render は `&` ではなくフォアグラウンドで待つか、分割 |
| 権限 | `brew`/`sudo`/`pip install` は提示のみ | 同じ。サンドボックスで書き込み不可なら OUT を作業ディレクトリ内に |

| 項目 | Mac (Apple Silicon) | Windows (WSL2) / Linux |
|---|---|---|
| Whisper | `mlx_whisper`（`pip install mlx-whisper`）。無ければ faster-whisper | `faster_whisper`（CPU: int8。GPU があれば `--device cuda --compute float16`） |
| パッケージ | Homebrew | apt / winget |
| Chromium | Remotion が自動DL | 自動DL。GPU 無しは `REMOTION_BROWSER` + render_timeline.sh の `--gl=swangle` |
| パス | `/Users/…`（空白・日本語あり） | `/mnt/c/Users/…`（`wslpath` で変換）。NTFS 上は render が遅いので OUT は WSL 側の `~/` 推奨 |
| フォント | `remotion/public/fonts/NotoSansJP[wght].ttf` を共通で使用（OS フォントに依存しない） | 同左 |

---

## 14. よくある失敗と対処

- **`transcribe.py` が遅い／落ちる**: `--model small` で試作 → 本編で `medium`。メモリ不足なら `--compute int8`。
- **render が "font ... missing"**: `check_env.sh` の [5] のコマンドでフォントを DL。
- **render が Chromium 起動で失敗**（Linux）: `REMOTION_BROWSER` を headless_shell に。`REMOTION_EXTRA="--gl=swangle"`。
- **字幕が口より早い/遅い**: cut_media の後に captions を作り直していない → 工程 5 を頭から再実行。
- **音が全体に 0.04s ほど遅れる（QC の同期ずれ警告）**: Remotion 経由の音声は AAC プライミング分遅れる。`RENDER_AUDIO=mux`（既定）で render.sh を実行しているか確認。
- **画面収録が 60fps でカクつく／レンダーが遅い**: `screen_cut.mp4` は出力 fps に揃う。カメラも 60fps なら `cut_media.py --fps 30` と `build_timeline.py --fps 30`。
- **映像が上下逆さま／横倒し**: probe の `rotation` を見る。通常は cut_media が正規化する。直らなければ `-vf "vflip,hflip"`（180°）や `transpose=1`（90°）で素材を直してから渡す。
- **丸ワイプに顔が入っていない**: `wipe.focus.y` を 0.25〜0.45 で調整（縦素材は 0.3 付近）。
- **画面収録がズレる**: `sync.py --max-lag 60` で再計算、または手で `screen_offset` を直す。
- **SRT に句読点がある／フィラーが残っている**: 仕様どおり（SRT は補正後 transcript の全文）。焼き込み字幕（`captions.json`）は句読点なし・冗長語なし。
- **出力先に日本語があり npx が失敗**: `render.sh` は `OUT/work` をシンボリックリンクで `remotion/public/work` に見せるので通常は問題ない。失敗したら OUT を ASCII パスにして最後に移動。
