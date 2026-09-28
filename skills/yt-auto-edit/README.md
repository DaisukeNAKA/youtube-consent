# yt-auto-edit（v2）

撮ったままの動画（人物・画面収録・別録り音声）を Claude Code / Codex に渡すと、字幕・見出し帯・丸ワイプ入りの YouTube 横動画（16:9）と SRT・自動検品結果を作るスキルです。編集ソフトは使いません（ffmpeg + Whisper + Remotion）。

エージェント向けの手順は `SKILL.md`、仕様と計測値は `../SPEC.md`（v1）＋本 README 末尾の「v2 の変更点」にあります。この README は「人が入れて動かす」ためのものです。

## ディレクトリ構成

```
yt-auto-edit/
├─ SKILL.md                 エージェントが読む手順書（Agent Skills 形式, 日本語）
├─ README.md                このファイル
├─ settings.default.json    見た目・配置の既定値（字幕/見出し/丸ワイプ/画面/Bロール/カット/音量/QC/SRT/出力）
├─ vocabulary.json          固有名詞・誤変換の辞書（最初は空。育てる）
├─ templates/
│   ├─ タイトル案.md          5案テンプレ（数字・断定・ネガ/ポジ対比・疑問・体験型）
│   ├─ 概要欄.md              要約3行→目次→リンク枠→ハッシュタグ
│   ├─ Codex_アップロード指示.txt  Codex に貼る YouTube/Spotify 保存指示（非公開・下書き）
│   └─ サムネ指示.md          サムネ候補 5 型（Greg型/数字ドン/ビフォーアフター/物体クローズ/テキスト主体）を画像生成 AI に頼む指示文
├─ scripts/
│   ├─ check_env.sh          環境チェック（不足分のインストールコマンドを出す）
│   ├─ probe.py              素材の長さ/fps/回転/縦横 → probe.json
│   ├─ sync.py               カメラ・画面収録・別録り音声の同期 → sync.json
│   ├─ transcribe.py         Whisper 文字起こし（Mac: mlx_whisper / それ以外: faster-whisper）→ transcript.json
│   ├─ plan_cuts.py          無音・フィラー・言い直しの候補 → cuts_auto.json
│   ├─ captions.py           焼き込み字幕の分割・時刻合わせ（caption_mute 対応）→ captions.json
│   ├─ make_srt.py           SRT を補正後 transcript の文単位で別生成 → 字幕.srt
│   ├─ cut_media.py          keep 区間で切り出し（fps/回転を正規化）＋ラウドネス正規化 → cut.mp4, screen_cut.mp4
│   ├─ build_timeline.py     Remotion 用 timeline.json
│   ├─ render.sh             Remotion レンダリング（映像は Remotion、音声は cut.mp4 を無変換多重化）
│   ├─ qc.py                 自動検品（字幕・音量・黒フレーム・口元同期ずれ）→ qc_report.md
│   ├─ run_pipeline.sh       上を一括で回す参考スクリプト
│   └─ common.py, jatext.py  共通部（settings 既定値のマージ、日本語テキスト処理）
└─ remotion/                 Remotion プロジェクト（src/, public/fonts/NotoSansJP[wght].ttf, node_modules/）
```

出力先（OUT = `YYYYMMDD_題名`）の構成は `SKILL.md` 9 章のとおり（`01_試作/`, `02_完成版/`, `work/`）。完成版は `02_完成版/YouTube_本編_1080p.mp4`（4K 出力なら `YouTube_本編_4K.mp4`）。

## 導入 5 分ガイド

### Mac（Apple Silicon）

```bash
# 1. 置く（Claude Code の場合。Codex は下の「配置」参照）
mkdir -p ~/.claude/skills && cp -R yt-auto-edit ~/.claude/skills/

# 2. 土台
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"   # Homebrew が無ければ
brew install ffmpeg node python@3.11

# 3. 音声認識（Apple Silicon は mlx が速い。Intel Mac は faster-whisper）
python3.11 -m pip install mlx-whisper numpy      # Intel: python3.11 -m pip install faster-whisper numpy

# 4. Remotion とフォント
cd ~/.claude/skills/yt-auto-edit/remotion && npm install
mkdir -p public/fonts && curl -L -o 'public/fonts/NotoSansJP[wght].ttf' \
  'https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf'

# 5. 確認
bash ~/.claude/skills/yt-auto-edit/scripts/check_env.sh
```

### Windows（WSL2 + Ubuntu 推奨）/ Linux

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg python3 python3-pip python3-venv
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
python3 -m pip install faster-whisper numpy
cd ~/.claude/skills/yt-auto-edit/remotion && npm install
mkdir -p public/fonts && curl -L -o 'public/fonts/NotoSansJP[wght].ttf' \
  'https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf'
bash ~/.claude/skills/yt-auto-edit/scripts/check_env.sh
```

- Windows のファイルは `/mnt/c/Users/…` で渡します（`wslpath -u 'C:\Users\...'`）。出力先は WSL 側（`~/Movies` など）の方が速いです。
- ネイティブ Windows（Git Bash）は `winget install Gyan.FFmpeg OpenJS.NodeJS.LTS Python.Python.3.11` で動きますが未検証です。
- GPU の無い Linux コンテナで Remotion が Chromium を起動できないときは、`REMOTION_BROWSER=<chromium headless_shell のパス>` を環境変数で渡してください（`scripts/render.sh` が `--browser-executable` に変換します）。

### 初回 Whisper モデル
初回の `transcribe.py` 実行時にモデル（medium ≈ 1.5GB）をダウンロードします。オフラインで使うときは一度オンラインで実行してください。

## 使い方（チャットに貼るだけ）

```
/Users/xxx/Movies/撮影.MOV と /Users/xxx/Movies/画面収録.mov を
/Users/xxx/Movies/20260928_動画名 に出力で、
プランB（見出し付き解説）で、まず40秒の試作を作って
```

試作を見て「1分20秒の字幕を『Apple Watch Ultra』に直して」「丸ワイプを小さめにして」「2分10秒から2分15秒は字幕なしで」と言葉で直し、最後に「この設定で本編を作って」。次回からは「前回と同じ設定で」と新しい素材を渡せば同じ見た目になります（`02_完成版/settings.json` が使われます）。

処理時間の目安（Brain の実測）: 40 秒の試作 4〜22 分、本編 9〜48 分。素材の長さ・Mac の世代・Whisper のモデルで変わります。

手で回したいときは `scripts/run_pipeline.sh --camera A [--screen B] [--audio C] --out OUT [--limit 40] [--plan edit_plan.json] [--settings settings.json]`。ただし `edit_plan.json`（何を残し、どこに見出しを出すか）はエージェントが transcript を読んで決めるものなので、`--plan` 無しだと「無音を詰めただけのプランA」になります。

## Claude Code への配置

どちらか一方に置きます。フォルダ名は `yt-auto-edit`、直下に `SKILL.md` が必要です。

| 置き場所 | パス | 向き |
|---|---|---|
| 個人（全プロジェクト共通） | `~/.claude/skills/yt-auto-edit/` | 普段使い |
| プロジェクト単位 | `<project>/.claude/skills/yt-auto-edit/` | チームで共有・git 管理 |

置いたあと Claude Code を起動し直すと、`SKILL.md` の frontmatter（`name` / `description`）でトリガーされます。`/yt-auto-edit` と打って明示的に呼ぶこともできます。`remotion/node_modules` は 200MB 以上あるので、git 管理するなら `.gitignore` に `remotion/node_modules/` と `remotion/public/work` を入れてください（`npm install` で再現できます）。

## Codex への配置

方法 A（推奨）: スキルディレクトリに置く

```bash
mkdir -p ~/.codex/skills && cp -R yt-auto-edit ~/.codex/skills/
```

方法 B: プロジェクトの `AGENTS.md` から参照する

```markdown
## 動画編集
YouTube 動画の編集を頼まれたら、まず `./skills/yt-auto-edit/SKILL.md` を読み、その手順に従うこと。
スクリプトは `./skills/yt-auto-edit/scripts/`、Remotion は `./skills/yt-auto-edit/remotion/` にある。
```

- Codex はサンドボックス内で書き込み先が制限されることがあります。出力先（OUT）が書けないと言われたら、作業ディレクトリ配下に OUT を作ってください。
- `SKILL.md` の手順は Claude Code / Codex どちらでも同じコマンドです（`SKILL` 変数だけ置き場所に合わせて変えます）。

## 辞書（vocabulary.json）の育て方

`transcribe.py --vocab vocabulary.json` で使われます。中身:

```json
{
  "terms": [],          "replacements": [],
  "words": ["Apple Watch Ultra", "Claude Code", "Remotion"],
  "corrections": {"大航海": "大後悔", "入ってない": "減ってない"}
}
```

- `words`: 固有名詞・製品名・人名。Whisper の initial_prompt に渡され、表記が安定します（`terms` は同じ用途の別名。現行の `transcribe.py` が読むのは `words` / `corrections` なので、追記は必ずこちらに）。
- `corrections`: 「誤変換 → 正しい表記」の置換。transcript に適用されます（`replacements` は別名）。
- 育て方: 試作で「◯分◯秒の字幕を△△に」と直したとき、同じ誤変換が他でも出そうなら `corrections` に、初出の固有名詞なら `words` に追記します。エージェントには「この辞書に追記して」と言えば足ります。
- チャンネル固有の辞書はプロジェクト側 `.claude/skills/yt-auto-edit/vocabulary.json` に、汎用の語は `~/.claude/skills/...` 側に分けると管理しやすいです。
- 増えすぎたら 200 語程度に絞ってください（initial_prompt が長いと認識が鈍ります）。

## settings.json

`settings.default.json` が既定値です。出力先の `work/settings.json` に差分だけ書けば、読み込み時にマージされます。v1 のキーしか無い古い settings.json でも v2 の既定が補われてそのまま動きます。例（丸ワイプ小さめ・右下、字幕を黄色・縁取りあり、画面収録は中央プリセット）:

```json
{"wipe": {"size": "small", "position": "bottom-right"},
 "caption": {"color": "#FFE500", "style": "outline"},
 "screen": {"preset": "takkatw"}}
```

主なキー（1080p 基準。4K は比率／px×2 で保持）:

| キー | 既定 | 意味 |
|---|---|---|
| `caption.style` | `"shadow"` | `shadow`=縁取りなし＋影（offset 2px, blur 5px, 50%）/ `outline`=黒縁（H×0.004）＋影 |
| `caption.size_ratio` / `bottom_ratio` / `min_dur` | 0.048 / 0.069 / 0.6 | 字の高さ、下端からの余白、最短表示 |
| `heading.skew_deg` / `text_color` / `show_during_screen` | -8.5 / `#182028` / true | 帯ごと傾ける角度、文字色、画面収録中も帯を出す |
| `heading.shape` | `"skew"` | `rounded` にすると角丸 20px・文字直立・文字 `#000`・アニメなし |
| `wipe.position` / `diameter_ratio` / `small_ratio` | `"bottom-left"` / 0.22 / 0.16 | 丸ワイプの位置と直径（中心 W×0.085, H×0.72。0.2s フェードイン） |
| `screen.preset` | `"author"` | `author`=幅 87.5%・左寄せ・角丸 12px / `takkatw`=幅 74.3%・中央・角丸なし |
| `vertical_source.background` | `"navy"` | 縦素材の背景。`blur` で素材のぼかし |
| `broll.transition` / `duration` / `zoom_kinds` | `dissolve` / 0.33 / `["photo"]` | Bロール切替のディゾルブ、拡大するのは photo だけ |
| `audio.lufs` / `tp` | -14 / -1.0 | ラウドネス目標 |
| `qc.lufs_tolerance` / `sync_tolerance` / `use_lra` | 1.0 / 0.04 / false | QC の合否（I=-14±1、A/V ずれ >0.04s で警告、LRA は合否に使わない） |
| `srt.max_chars` / `apply_caption_mute` | 40 / false | SRT の 1 キュー上限、caption_mute を SRT にも適用するか |
| `output.final_name` | `YouTube_本編_{res}.mp4` | 完成版ファイル名（`{res}` = 1080p / 4K） |

言葉での指示 → キーの対応表は `SKILL.md` 7 章にあります。

## 標準工程に含まれないもの

効果音・BGM・図解・サムネイル生成・ダイジェスト（ショート）・YouTube へのアップロード。サムネは `02_完成版/サムネ指示.md` を画像生成 AI に貼ると候補が作れます。アップロードは `02_完成版/Codex_アップロード指示.txt` を Codex に貼るのが簡単です（Claude なら Computer Use / Claude in Chrome / MCP）。

## トラブル

`bash scripts/check_env.sh` を実行し、NG の行のインストールコマンドを実行してください。Remotion のフォントが無いとレンダリングは明示的に失敗します（`remotion/README.md` 参照）。そのほかの症状は `SKILL.md` 14 章。

## v2 の変更点（v1 → v2。反証レビューと試作 1 回目の所見）

| # | 項目 | v1 | v2 |
|---|---|---|---|
| A1 | 丸ワイプ | 右下、直径 H×0.20 | **左下**（円中心 W×0.085, H×0.72）、直径 H×0.22（小 0.16）、縁なし、0.2s フェードイン。Brain の文言は右下だが実動画は左下 |
| A2 | 画面収録インセット | 幅 74%・中央 | プリセット `author`（幅 87.5%・上 2.8%・左 9.2%・角丸 12px）既定、`takkatw`（幅 74.3%・上 40px・中央・角丸 0） |
| A3 | 見出し帯 | skew -12°、文字直立 | skew **-8.5°、帯ごと傾ける**（文字も擬似斜体）、文字色 #182028、pad 20/32px、左からスライド 0.25s・アウト即消え、画面収録中も表示。`rounded` は角丸 20px・文字直立・#000・アニメなし |
| A4 | 字幕 | 黒縁 + 影、0.052H、最短 0.8s | **縁取りなし＋ドロップシャドウ**（`caption.style: shadow`）。`outline` で黒縁。0.048H、下余白 0.069H、最短 0.6s |
| A5 | Bロール vertical | ゆっくり拡大 | **静止**（拡大は photo のみ）。カード中心 (0.70W, 0.51H)、最大高 0.62H、角丸 30px、下影 |
| A6 | Bロール切替 | フェード 0.25s | レイアウト全体のディゾルブ 0.33s（10f@30） |
| A7 | 縦素材の背景 | blur | **navy**（#101627）。blur は代替 |
| B1 | SRT | 焼き込みと同じ分割 | `make_srt.py` が補正後 transcript の**文単位・句読点あり・冗長語あり**で別生成（keep 外は落とす） |
| B2 | 落とした語の間 | 前のキューを伸ばして埋める | フィラー/相槌の発話中は**字幕を出さない** |
| B3 | caption_mute | なし | `edit_plan.caption_mute: [{src_start, src_end}]` の区間は字幕化しない |
| C1 | 完成版名 | `本編_1080p.mp4` | `YouTube_本編_1080p.mp4`（4K は `YouTube_本編_4K.mp4`）。プロジェクトフォルダは `YYYYMMDD_題名` |
| C2 | サムネ | 標準外のみ | `templates/サムネ指示.md`（5 候補を画像生成 AI に頼む指示） |
| C3 | QC | I/TP/LRA | `--source`/`--plan` で**口元同期ずれ**（|ずれ| > 0.04s 警告）。LRA は合否から除外、TP ≤ -1.0、I = -14±1 |
| C4 | SKILL.md | — | 60fps 画面収録→30fps、逆さま回転の正規化、処理時間の目安、上記すべての手順化 |
