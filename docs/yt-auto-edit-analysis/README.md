# しゅうへい氏「YouTube自動編集スキル」の逆算・再現・検証レポート

作成日: 2026-09-28 ／ 対象: Brain「AIに動画を渡すだけ『YouTube自動編集スキル』｜編集ソフト不要【Claude Code・Codex対応】」（2,980円、v5）
成果物: `skills/yt-auto-edit/`（確定スキル一式 v3）、本フォルダ（仕様・検証・サンプル出力）

---

## 1. 結論

1. **スキルの正体**は「ffmpeg ＋ Whisper（Mac は mlx_whisper）＋ Remotion を Claude Code／Codex から回す手順書（SKILL.md）＋ 見た目の設定（settings.json）＋ 補助スクリプト」である。編集の判断（どこを切るか、見出しの文言、画面を出す区間）は LLM が transcript を読んで決め、見た目は Remotion の1スタイル（白1行字幕・左上の斜め見出し帯・丸ワイプ）で固定される。3プラン（A/B/C）は「見出しと画面収録・ワイプをどれだけ出すか」の違いに過ぎない。
2. **再現度**: 参考動画3本＋本人11分動画のフレームを計測し、v1→v2→v3 の3反復で12点の誤りを修正した結果、字幕・見出し帯・丸ワイプ・画面インセット・Bロールの幾何は計測上 ±0.01H 以内で一致した（`review/検証2_v2v3.md` の表）。字幕分割規則（意味の切れ目・句読点なし・半角英数・相槌の除外）、SRT を焼き込みとは別に文単位で出す点、YouTube 向けラウドネス（-14 LUFS）、成果物構成（01_試作／02_完成版／字幕.srt／qc_report／Codex_アップロード指示.txt）も一致させた。
3. **ユニコ素材での実行**: ユニコ（NSC東京31期）の「10分ラジオ #8 メルカリの怖い話」（TikTok ライブ録画、横向き記録→正立化、冒頭5分）に対し、プランBで 40秒試作 → 本編（283秒、見出し7本、Bロール1枚）を生成。自動検品は字数・表示時間・音量・黒フレーム・口元同期のすべてで合格（`samples/qc_report_*.md`）。

---

## 2. 根拠（一次情報。`sources/` に本文を保存）

| 情報源 | 得られた事実 |
|---|---|
| Brain 商品ページ無料部（v5, 9/27更新）`sources/brain_yt_api_body.txt` | 入力3種／出力（mp4＋SRT＋自動検品＋settings.json）／5手順（40秒試作→本編）／内部6工程（文字起こし＋カット、字幕分割、同期、見出し＋丸ワイプ合成、音量正規化、自動検品）／スタイル1種（白1行句読点なし・左上斜め帯・丸ワイプ）／3プラン／言葉で変えられる項目／標準外（SE・BGM・図解・サムネ・ダイジェスト・アップロード）／環境（Apple Silicon, FFmpeg, Python, 音声認識, Node.js, Remotion）／実測（40秒試作4分・4分本編9分、逆さま素材で22分・48分） |
| 前身「ショート動画丸投げくん」Brain `sources/brain_short_api_body.txt` | Whisper誤変換の文脈補正・意味の切れ目で分割・行頭NG文字回避・言い直し/フィラー検知カット・無音>1秒→0.5秒・音量正規化・自動QC・「◯枚目を△△に」修正・vocabulary.json・mlx_whisper/faster-whisper 自動切替・初回環境チェック |
| X記事「Opus 5.5の動画編集力がやばい」`sources/x_article_opus55.txt` | 7分素材→4分本編、作業9分、週枠2%、パスを貼って依頼、40秒試作→OK→本編、画面収録とカメラの切替、小さい見出し |
| X投稿（Claude Code と Codex の使い分け）`sources/x_shupeiman_2104070038382879199.txt`＋スクショ4枚 | 02_完成版／YouTube_ダイジェスト付き_BGM入り_4K.mp4／Codex_アップロード指示.txt／サムネ候補01 Greg型〜05／SRT（句読点あり・文単位）／非公開アップ・収益化は前回と同じ・Spotify下書き |
| note記事（Codex版）`sources/note_codex.txt` | Remotion、見出しは上部・キャプションは顎の下、モックA/B/C（Aの斜め見出しを採用）、Bロールをじわっと動かす、参考動画を分析→モック→23秒試作→本番 |
| 参考動画（本人30秒4K/1080p、takkatw 42秒、carley 12秒）＋X記事フレーム4枚 | 字幕: 字高0.044〜0.054H、下端余白0.059〜0.077H、本人は縁取りなし影のみ／見出し帯: 高さ0.075〜0.087H、傾き8.4〜9.2°、文字も傾く／丸ワイプ: 左下、直径0.20〜0.26H、インセット左端に円中心／インセット: 本人は左176px・上30px・下端895px・角丸12、takkatwは幅0.743W中央／Bロール: 話者40%＋すりガラス＋角丸カード静止、全画面ディゾルブ0.33s／ラウドネス -14 LUFS |

---

## 3. 逆算したスキルの構造（確定 v3）

```
入力: 人物動画（必須） ＋ 画面収録・別録り音声・写真（任意）  ← パスを貼る
 ├ check_env.sh   初回のみ環境チェック（不足はコピペ用コマンドを提示）
 ├ probe.py       長さ/fps/回転/縦横（逆さま記録の正規化、60fps→30fps）
 ├ sync.py        音声エンベロープ相互相関で画面収録・別録り音声を同期
 ├ transcribe.py  Whisper（mlx/faster 自動切替）単語タイムスタンプ＋vocabulary.json
 ├ plan_cuts.py   無音>1.0s→0.5s、フィラー・言い直し候補   ─┐
 │  ▶ エージェントが transcript を読み edit_plan.json を書く ←┘ （keep／見出し／画面区間／Bロール／字幕mute）
 ├ captions.py    1行≤18字・意味の切れ目・句読点なし・半角英数・相槌除外・落とした語の間は字幕なし
 ├ make_srt.py    SRT は文単位・句読点あり（焼き込みとは別データ）
 ├ cut_media.py   keep 連結・同期・loudnorm(-14 LUFS/TP -1)
 ├ build_timeline.py → timeline.json（Remotion の inputProps）
 ├ render.sh      Remotion（--muted 描画＋cut.mp4 音声を mux＝口元同期ずれ0）
 └ qc.py          字数・表示時間・重なり・ラウドネス・黒/フリーズ・口元同期
出力: 01_試作/試作_40秒.mp4 → 修正は言葉で → 02_完成版/YouTube_本編_1080p.mp4, 字幕.srt, qc_report.md, settings.json,
      タイトル案.md, 概要欄.md, Codex_アップロード指示.txt（＋サムネ指示.md は依頼時）
```

見た目の確定値（1080p比率。4Kは2倍）は `../../skills/yt-auto-edit/settings.default.json`、根拠と計測は `SPEC.md`（v1→v3 追補つき）。

---

## 4. 検証ループ（2回以上）

| 反復 | 入力 | 主な誤り（正解との差分） | 反映 |
|---|---|---|---|
| v1 仮説 → 試作40秒 | ユニコ 5分 | 丸ワイプ既定が右下（実動画は全て左下）／インセット中央（本人は非中央）／帯の傾き12°で文字直立（実際は8.5°で文字も傾く）／字幕に黒縁（本人は影のみ）／Bロール拡大・単体フェード（実際は静止・全画面ディゾルブ）／SRTが焼き込みと同一（実際は文単位・句読点あり）／字幕がセグメントをまたいで詰まる／min_dur 0.8（実測0.63）／縦素材背景／出力ファイル名／**音声が42ms遅れる（AACプライミング）** | `SPEC_v2_delta.md` → v2 |
| v2 → 試作40秒 | 同 | 話者交代で「私も使いますよメルカリさ」が1行になる／画面インセット（16:9収録）が字幕帯と20px重なる | v3 |
| v3 → 試作40秒 → 本編5分 | 同 | 計測差分なし。QC合格（字数・表示時間・音量・黒/フリーズ・口元同期） | 確定 |

反証専任エージェントの反証（24項目）は `review/measurements_summary.json`、比較画像は `review/compare_v1_*.jpg`（v1）、`review/compare_v3_*.jpg`（v3）。

---

## 5. 置いた前提

1. ユニコの Drive 原素材（DJI 8〜17GB、iPhone 0.2〜3GB）は Drive MCP の 10MB 上限で取得できないため、同コンビが公開している TikTok ライブ録画（縦720x1280に横向き記録→transpose で 1280x720 に正立化、冒頭5分）を「撮ったまま素材」として使った。TikTok ライブのオーバーレイ（番組名・名前タグ）は素材側に焼き込まれている。
2. 本人の SKILL.md 本体（Brain 有料部・セットアップ手順書）は未閲覧。挙動・成果物・記述から逆算した仮説であり、文言レベルの一致は保証しない。
3. 「正解」は公開されている本人・購入者の**出力**のみで元素材がないため、カット判断の一致は検証できない。比較したのは見た目の幾何、字幕規則、成果物構成、音量、同期。
4. 環境: 本コンテナは 4コアCPU・GPUなし。faster-whisper medium（int8）、Remotion は headless_shell＋swangle。速度は Brain 実測（M2 Air）と比べられない。
5. YouTube（bot判定）から本人の自動編集済み動画本体は取得できず、X の 30秒版と記事内フレームで代替した。

---

## 6. 残論点

1. **丸ワイプの既定位置**: Brain 文言は「右下」、実動画（本人・takkatw）は全て「左下」。v3 は左下を既定にし、右下は設定で切替。
2. **見出し帯の形**: 本人・takkatw は斜め帯（文字も傾く）、carley（Windows）は角丸・文字直立・アニメなし。バージョン差か環境差か未確定。両方を settings で用意。
3. **SRT の時刻付け**: 「句読点あり・文単位・焼き込みと別」までは確認済み。時刻の丸め方は推定。
4. **無音詰め 1.0s→0.5s・フィラー除去**は前身ショート版の記述からの流用仮説。閾値は settings で可変。
5. **Drive 大容量素材**: 次回は 10MB 以下の 720p プロキシ、または共有リンク（許諾済みのもの）を用意すれば原素材で検証できる。
6. **処理速度**: 本コンテナで 40秒試作≈3分、5分本編≈1時間超。Apple Silicon＋mlx_whisper なら Brain 実測に近づく見込み（未計測）。
7. **サムネ生成**: 本人運用（01 Greg型〜05）は Brain 標準外。テンプレ（`templates/サムネ指示.md`）のみ用意し、画像生成は別途。

---

## 7. ファイル一覧

- `SPEC.md` … 逆算仕様書（v1 本文＋v2 差分＋v3 追補）、`SPEC_v2_delta.md` … 検証1で確定した修正
- `review/検証1_v1.md`, `review/検証2_v2v3.md` … 反復ごとの比較表、`review/measurements_summary.json` … 反証レビューの計測、`review/measure.py`, `review/compose.py` … 計測・比較シート生成
- `review/compare_v1_*.jpg`, `review/compare_v3_*.jpg` … 正解 vs 成果物の並置画像
- `samples/` … ユニコ素材での実行結果（`edit_plan.json`, `captions.json`, `字幕.srt`, `qc_report_*.md`, `タイトル案.md`, `概要欄.md`, `Codex_アップロード指示.txt`, `vocabulary.json`, `試作_40秒_v3.mp4`, `スモーク_画面収録＋ワイプ＋Bロール_v3.mp4`, `frames/`）
- `sources/` … 一次情報の本文（Brain 無料部2件、X記事、X投稿4件、note）
- `../../skills/yt-auto-edit/` … 確定スキル（`SKILL.md`, `README.md`, `settings.default.json`, `vocabulary.json`, `scripts/`, `remotion/`, `templates/`）。導入は `README.md`、フォントは `scripts/check_env.sh` が取得。

---

## 8. 使い方（要約）

1. `skills/yt-auto-edit` を `~/.claude/skills/`（Codex は `~/.codex/skills/`）に置き、`bash scripts/check_env.sh` の指示どおり ffmpeg／Node／Python／whisper／`cd remotion && npm install`／フォントを入れる。
2. Claude Code で「この動画を YouTube 動画にして。プランBで、まず40秒の試作を作って」＋ 素材のパス（Finder の「パス名をコピー」）＋ 出力先。
3. 試作を見て「◯分◯秒の字幕を△△に」「丸ワイプを小さめに」「帯を右上に」などと言葉で直す → 「この設定で本編を作って」。
4. `02_完成版/Codex_アップロード指示.txt` を Codex に貼れば、非公開アップロード・字幕・前回と同じ収益化設定まで任せられる（Claude なら Computer Use／Claude in Chrome）。
