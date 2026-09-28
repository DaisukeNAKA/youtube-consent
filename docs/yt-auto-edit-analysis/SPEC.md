# yt-auto-edit スキル 仕様書（逆算仮説 v1 → v3 確定）
作成日: 2026-09-28。対象: しゅうへい氏 Brain「AIに動画を渡すだけ『YouTube自動編集スキル』｜編集ソフト不要【Claude Code・Codex対応】」(2,980円, v5) の再現。
根拠: Brain商品ページ無料部（$S/ref/brain_yt_api_body.txt）、前身「ショート動画丸投げくん」(brain_short_api_body.txt)、X記事、note記事(note_codex.txt)、参考動画3本のフレーム計測。

## 0. 環境（この作業コンテナ）
- SCRATCH = /tmp/claude-0/-home-user-youtube-consent/f3ff735b-c06f-5609-baca-e73cb409618e/scratchpad （以下 $S）
- 参考動画: $S/media/ref_takkatw_42s_1080p.mp4, ref_shupeiman_30s_1080p.mp4, ref_shupeiman_30s_4k.mp4, ref_carley_12s_1080p.mp4。フレーム: $S/media/frames/*.png
- 参考書き起こし: $S/media/ref_transcripts.json
- ユニコ素材（テスト入力）: $S/unico/*.mp4|*.LRF
- ffmpeg 6.1 (/usr/bin/ffmpeg), python3.11 + faster-whisper(medium/small モデルDL済), opencv, Pillow, numpy
- node 22, npm。Remotion一式は $S/remotion-skill/node_modules にインストール済み（remotion, @remotion/cli, @remotion/google-fonts, @remotion/media-utils, react, react-dom, typescript）。Chromium: /opt/pw-browsers 配下（Remotionには --browser-executable で渡す）。CPU 4コア, GPUなし。
- フォント: /usr/share/fonts/opentype/noto/NotoSansCJK-*.ttc（システム）。Remotion用には Noto Sans JP の TTF を https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf からDLして public/fonts/ に置く。

## 1. スキルの入出力（Brain記載の事実）
- 入力: 撮ったままの「人物の動画」「画面収録」「別録り音声」のうち手元にあるもの。パス（Finder「パス名をコピー」）と出力先をチャットに貼る。
- 出力: YouTube横動画(16:9) mp4 + 字幕ファイル(SRT) + 自動検品結果 + settings.json（見た目・配置の永続化。次回「前回と同じ設定で」）。
- 手順(5): 撮る → 「プランB（見出し付き解説）で、まず40秒の試作を作って」 → 試作確認（声と口元の同期／字幕の正誤／画面の文字が読めるか／丸ワイプが邪魔でないか） → 言葉で修正（「◯分◯秒の字幕を△△に直して」「丸ワイプを小さめにして」） → 「この設定で本編を作って」。
- スキル内部工程(6): ①文字起こし＋無駄な部分のカット ②字幕の分割＋表示時刻の合わせ込み ③カメラ・画面収録・別録り音声の同期 ④見出しと丸ワイプの合成 ⑤音量をYouTube向けに揃える処理と書き出し ⑥自動検品（字数・表示時間・音量・映像の途切れを機械的に確認）。
- 編集スタイル(1種): 白い字幕（1行・句読点なし）／左上の斜めの見出し帯／右下の丸ワイプ（自分の顔を丸く切り抜いて重ねる）。
- 画面構成プラン(3): A シンプルトーク（人物と声中心。画面は必要な場面だけ）／B 見出し付き解説（話題ごとに見出し。操作中は丸ワイプ）／C 画面実演＋丸ワイプ（操作画面中心。画面を映している間は丸ワイプ）。
- 言葉で変えられる: 丸ワイプの位置(右下/左下)と大きさ(標準/小さめ)、字幕の色、見出し帯の左右、帯・文字の色。見出しの形は1種類。
- v5 (9/27): 写真/スクショを「白っぽいすりガラス背景の上に角丸カード」で表示。縦長スクショ/SNS投稿は話者の横に大きく並べる。縦写真は画面いっぱいのすりガラス上でゆっくり拡大。Webページ画像はページ背景色のまま全画面。
- 標準工程に含まれない: 効果音・BGM・図解・サムネイル・ダイジェスト・YouTubeアップ（別途AIに頼む。アップはCodex推奨）。
- 前身ショート版の内部（流用前提）: Whisper誤変換の文脈補正／意味の切れ目で分割／行頭NG文字回避／言い直し・フィラー検知カット／無音>1秒→0.5秒に詰める（既定オン）／音量正規化／自動QC／「◯枚目を△△に」修正／vocabulary.json 辞書／Mac=mlx_whisper, Windows=faster-whisper 自動切替／初回のみ環境チェック。
- 動作環境: Apple Silicon Mac 前提。FFmpeg, Python, 音声認識, Node.js, Remotion。Homebrew。

## 2. 見た目の計測値（参考動画のフレーム計測, 1080p基準。比率で保持し4Kは2倍）
### 2.1 字幕（caption）
- フォント: Noto Sans JP 相当の太いゴシック（weight 800-900）。白 #FFFFFF、黒縁取り約 3-4px(1080p) ＋ 弱いドロップシャドウ。背景ボックスなし。
- 字高 49-59px → font-size ≈ 56px (=H×0.052)。1行、中央揃え。グリフ下端から画面下端まで 65-79px (=H×0.065〜0.073) → bottom margin ratio 0.068。
- 文字数: 観測 5〜20文字/行（「AIを使っているの めっちゃ早いんですよね」20字含スペース）。上限 20、推奨 ≤18。
- 句読点なし。読点相当の切れ目は半角スペース（例「丸2日 画面常時オンだったんですよ」）。数字・英字は半角（8%, 49%, 1時間, Apple Watch）。
- 表示: 各キューは次のキュー開始まで持続（隙間 ≤0.6s は埋める）。最短 0.8s、最長 4.0s 目安。意味の切れ目で分割（助詞・接続の後、「〜ですよ」「〜けど」など文末で切る）。
- 例（正解データ, ref_shupeiman）: もうめちゃくちゃ大後悔です／これはネタバレですけど／早く買っておけばよかった／Apple WatchとApple Watch Ultraは／別物です／別商品と言っても過言ではない／丸2日 画面常時オンだったんですよ／それで充電いらずでした／要するに37%から／8%しか減ってないですよ／1時間走ってですよ／GPSオンで画面オンで／なんと49%もあるんですよ／すごくないですか／この朝8時から／常時オンで寝る前49%
  - Whisper生出力との差: 「大航海」→「大後悔」（文脈補正）、「入ってない」→「減ってない」、「なので」「から」等の冗長語を削除、長文を2つに分割。
- SRT（YouTube Studio画面）は「もう、めちゃくちゃ大後悔です」のように読点が残る場合あり（低確度）。焼き込み字幕は句読点なし。
### 2.2 見出し帯（heading band）
- 位置: 左上。左余白 ≈ 56〜87px (W×0.03〜0.045)、上余白 ≈ 48〜60px (H×0.045〜0.055)。
- 形: 白 #FFFFFF の帯。takkatw/しゅうへい本人動画では左右の辺が斜めの平行四辺形（skewX ≈ -12°、角は直角）。carley動画では角丸長方形（skewなし）。→ settings.heading.shape = "skew"(既定) | "rounded"。
- 帯高さ ≈ 90px (H×0.083)。文字: 濃紺〜黒 #1C2230 付近、太字、font-size ≈ 44px (H×0.041)。左右パディング ≈ 36px、上下 ≈ 22px。
- 文字は回転せず水平。帯はトピック区間の間表示し続ける（takkatw: 「三角関数の講義を作ってみた」→「中学生でも分かるレベル」と話題ごとに切替）。イン/アウトは短いスライド or フェード(0.25s)。
- 見出し文は 6〜14文字程度の体言止め/短文（例: 実物はこんなに小さい／元素材は7分の撮りっぱなし／三角関数の講義を作ってみた／テスト動画）。
### 2.3 丸ワイプ（circle wipe）
- 直径 ≈ 220px (H×0.20)。「小さめ」= H×0.15。位置既定=右下、余白 ≈ 40〜50px。takkatwは左下（画面収録の外側余白に配置）。
- 中身: カメラ映像を顔中心で円形クロップ（object-fit: cover, 位置は settings.wipe.focus で調整）。縁取りなし〜細い白縁、弱い影。
- 表示条件: プランB=画面収録を映している間、プランC=画面中心の間。プランA=なし。
### 2.4 画面収録の配置（プランB/C）
- 濃紺背景 #101627 の上に、画面収録を幅 W×0.74（1425px）、上余白 H×0.037（40px）で中央配置（高さ≈895px→下端 935px）。角丸 ≈12px。字幕は下の余白に置く（帯の上に重ならない）。
- 画面収録が16:9でない/縦の場合も同様に内側配置。
### 2.5 縦素材（9:16 の撮影素材）
- 高さいっぱい・中央配置（幅≈607px @1080p）。背景: (a) 濃紺 #101627（takkatw） (b) 素材自体をぼかして拡大したすりガラス（carley, v5）。既定 "blur"、代替 "navy"。
### 2.6 写真/スクショ（v5 Bロール）
- 縦長スクショ: 画面左 W×0.40 にカメラ映像（顔中心クロップ、全高）、右側は すりガラス（カメラをぼかし＋白70%）上に角丸カード（radius ≈ 30px @1080p、影付き）を中央配置。カードはゆっくり拡大 (1.00→1.06)。フェードイン/アウト 0.25s。
- 縦写真: 全画面すりガラス上に中央配置、ゆっくり拡大。Webページ画像: ページ背景色で全画面表示（余白はその色）。
### 2.7 カット・音
- ジャンプカット（トランジションなし）。無音 >1.0s → 0.5s に詰める（前0.25s＋後0.25s残す）。言い直し・フィラー（えー/えっと/あの/まあ/なんか の文頭）を候補として検出しエージェントが確定。
- ラウドネス: ITU-R BS.1770 統合 -14 LUFS、TP -1 dBTP、LRA 11（ffmpeg loudnorm 2パス）。
- 出力: H.264 (libx264, crf 18, yuv420p), AAC 192k, 30fps（素材fpsに追従可）, 1080p既定。4K は本人動画で使用（4K入力時）。

## 3. 実装インターフェース（この再現実装）
ディレクトリ: $S/skill/yt-auto-edit/
- SKILL.md（エージェント向け手順。日本語）
- settings.default.json（見た目の既定値。下記スキーマ）
- scripts/check_env.sh, scripts/probe.py, scripts/transcribe.py, scripts/sync.py, scripts/plan_cuts.py, scripts/captions.py, scripts/build_timeline.py, scripts/cut_media.py, scripts/render.sh, scripts/qc.py, scripts/make_srt.py（captions.pyに同居可）
- remotion/（Remotionプロジェクト: src/index.ts, src/Root.tsx, src/Main.tsx, components/Caption.tsx, HeadingBand.tsx, CircleWipe.tsx, ScreenInset.tsx, BrollCard.tsx, public/fonts/）
- templates/（タイトル案.md, 概要欄.md, Codex_アップロード指示.txt のテンプレ）
- vocabulary.json（空の辞書）

### 3.1 作業ディレクトリ（出力先 = OUT）
OUT/work/{probe.json, transcript.json, sync.json, cuts_auto.json, edit_plan.json, captions.json, timeline.json, cut.mp4, screen_cut.mp4}
OUT/01_試作/試作_40秒.mp4（＋ 字幕.srt）
OUT/02_完成版/{本編_1080p.mp4, 字幕.srt, settings.json, qc_report.md, タイトル案.md, 概要欄.md, Codex_アップロード指示.txt}

### 3.2 transcript.json（transcribe.py 出力）
{"engine":"faster-whisper","model":"medium","language":"ja","audio":"<path>","segments":[{"start":0.0,"end":2.9,"text":"…","words":[{"w":"もう","s":0.08,"e":0.30,"p":0.9}]}]}

### 3.3 sync.json（sync.py 出力）: {"camera":"<path>","screen":"<path>|null","audio":"<path>|null","screen_offset":1.234,"audio_offset":-0.05}
（offset = カメラ時刻 t に対応する当該ファイル時刻は t + offset）

### 3.4 cuts_auto.json（plan_cuts.py 出力）: {"silences":[{"start":..,"end":..}],"keep_auto":[{"src_start":..,"src_end":..}],"filler_candidates":[{"start":..,"end":..,"text":"えっと"}],"retake_candidates":[{"start":..,"end":..,"reason":"repeat"}]}

### 3.5 edit_plan.json（エージェント=LLMが確定して書く）
{"plan":"B","keep":[{"src_start":3.2,"src_end":45.0}],"headings":[{"text":"…","src_start":10.0,"src_end":40.0}],"screen":[{"src_start":20.0,"src_end":35.0}],"broll":[{"file":"…png","src_start":50.0,"src_end":56.0,"kind":"vertical|photo|web"}],"caption_overrides":[{"src_time":12.3,"text":"…"}],"notes":"…"}
- keep は昇順・非重複。src_* はカメラ（主音声）時刻。

### 3.6 captions.json（captions.py 出力。出力タイムライン時刻）
{"max_chars":18,"cues":[{"start":0.0,"end":2.1,"text":"もうめちゃくちゃ大後悔です","src_start":0.08,"src_end":2.2}]}

### 3.7 timeline.json（build_timeline.py 出力 → Remotion の inputProps）
{"fps":30,"width":1920,"height":1080,"durationInFrames":3702,"video":"cut.mp4","screen":"screen_cut.mp4"|null,"sourceAspect":"16:9"|"9:16","style":{…settings…},"captions":[{"start":0.0,"end":2.1,"text":"…"}],"headings":[{"start":..,"end":..,"text":"…"}],"screenSegments":[{"start":..,"end":..}],"broll":[{"start":..,"end":..,"file":"…","kind":"vertical"}]}
- パスは OUT/work からの相対。Remotionは public/ 配下の staticFile を使うため、render.sh が OUT/work を remotion/public/work にシンボリックリンクする。

### 3.8 settings.default.json
{"version":"v1","resolution":"1080p","fps":30,
 "caption":{"font":"Noto Sans JP","weight":900,"size_ratio":0.052,"bottom_ratio":0.068,"color":"#FFFFFF","stroke_color":"#000000","stroke_ratio":0.0037,"shadow":true,"max_chars":18,"min_dur":0.8,"max_dur":4.0,"gap_fill":0.6,"punctuation":false},
 "heading":{"position":"top-left","shape":"skew","skew_deg":-12,"band_color":"#FFFFFF","text_color":"#1C2230","size_ratio":0.041,"margin_x_ratio":0.045,"margin_y_ratio":0.055,"pad_x_ratio":0.019,"pad_y_ratio":0.02,"anim":"slide"},
 "wipe":{"position":"bottom-right","size":"standard","diameter_ratio":0.20,"small_ratio":0.15,"margin_ratio":0.04,"border":false,"focus":{"x":0.5,"y":0.35}},
 "screen":{"layout":"inset","bg":"#101627","width_ratio":0.74,"top_ratio":0.037,"radius_ratio":0.011},
 "vertical_source":{"background":"blur","blur_px":40,"dim":0.35},
 "broll":{"style":"frosted-card","speaker_width_ratio":0.40,"card_radius_ratio":0.028,"zoom_to":1.06,"fade":0.25,"glass_white":0.70,"blur_px":40},
 "cuts":{"silence_threshold":1.0,"silence_keep":0.5,"remove_fillers":true},
 "audio":{"lufs":-14,"tp":-1,"lra":11},
 "output":{"codec":"libx264","crf":18,"preset":"medium","audio_bitrate":"192k"}}

## 4. エージェント（SKILL.md）の振る舞い
1. 初回: check_env.sh。不足があればコピペ用コマンドを提示（Mac: brew install ffmpeg node python; pip install mlx-whisper(Mac)/faster-whisper; npm i in remotion）。
2. 素材パスと出力先を受け取る。probe.py で長さ/fps/回転/縦横を把握。複数素材は sync.py で同期。
3. transcribe.py → transcript.json。vocabulary.json を適用。
4. plan_cuts.py → cuts_auto.json。エージェントが transcript を読み、言い直し/雑談/電話/準備時間などを除外し、話題ごとの見出しと画面表示区間を決めて edit_plan.json を書く（プラン A/B/C）。
5. 試作: 冒頭〜40秒相当（keep の先頭から40秒）で captions → build_timeline → cut_media → render → 01_試作。ユーザーに確認観点4つを提示。
6. 修正指示を受けたら edit_plan / settings / caption_overrides に反映して再レンダー。
7. 「この設定で本編を作って」→ 全尺で実行 → 02_完成版 + SRT + qc_report + settings.json + タイトル案/概要欄（テンプレ）+ Codex_アップロード指示.txt。
8. 標準外（BGM/SE/サムネ/ダイジェスト/アップロード）は依頼があれば別対応。


---
# SPEC v2 差分（反証レビューと試作1回目の結果を反映）
根拠: skill/review/measurements_summary.json（反証レビューの独自計測）, runs/unico_v1/01_試作（試作1回目）
## A. 見た目
A1. 丸ワイプの既定位置は「左下」。実動画(takkatw, 本人11分動画のX記事フレーム)は全て左下。Brain文言の「右下」は併記のみ。円中心=(W×0.085, H×0.72)、直径=H×0.22（takkatw 0.20〜本人 0.26）。インセット左端に円中心が重なる。縁なし。0.2s フェードイン。
A2. 画面収録インセット2プリセット。既定 'author': 幅 W×0.875、上 H×0.028(30px)、左 W×0.092(176px)（非中央、左にワイプ余白）、角丸 12px、背景 #101627。代替 'takkatw': 幅 W×0.743、上 40px、中央、角丸 0。
A3. 見出し帯: skewX -8.5°（帯コンテナごと。文字も擬似斜体）。左上、上余白 H×0.045〜0.065（既定 0.055）、左余白 W×0.045。帯高≈H×0.083、文字≈H×0.041、pad 上下≈20px 左右≈32px、文字色 #182028。イン=左からスライド 0.25s、アウト=即。画面収録中も表示（本人動画準拠）。'rounded'（carley/Windows）: 角丸20px、文字直立、#000、アニメなし。
A4. 字幕: 既定は縁取りなし＋弱いドロップシャドウ(offset 2px, blur 5px, α0.5)。縁取り(0.004H)はオプション 'outline'。min_dur 0.6s、bottom_ratio 0.069、size_ratio 0.048。
A5. 縦長スクショ(kind=vertical)は静止。拡大は kind=photo のみ。カード中心 (0.70W,0.51H)、最大高 0.62H、角丸30px、下影。
A6. Bロール切替はレイアウト全体のディゾルブ 0.33s(10f)。
A7. 縦素材背景の既定は navy #101627。blur は代替。
## B. 字幕生成
B1. SRT は焼き込みキューと別データ（文単位・句読点あり・冗長語あり）。補正後 transcript から出力時刻へ写像して生成（make_srt.py）。
B2. 字幕から落とした語（フィラー/相槌）の発話中は字幕なし（gap_fill で伸ばさない）。
B3. edit_plan.caption_mute で字幕を作らない区間を指定（画面収録内の別音声など）。
B4. 試作1回目の所見: Whisperセグメント境界を切れ目として優先／相槌だけのセグメントは字幕化しない／「あ、」「え、」を文頭フィラー扱い／語の途中(よ|く)で切らない／「な」「さ」で始まる行を作らない（captions.py v2 で実装済み）。
## C. 成果物・運用
C1. 出力名: <素材と同階層>/YYYYMMDD_題名/02_完成版/YouTube_本編_1080p.mp4（4Kなら _4K）。01_試作/試作_40秒.mp4 は維持。
C2. templates/サムネ指示.md（サムネ候補 01 Greg型〜05）。画像生成は標準外、頼まれたら。
C3. QC に口元同期（出力音声×素材音声の相互相関、|ずれ|>40ms 警告）を追加。LRA は合否に使わない。TP ≤ -1.0、I=-14±1。
C4. 60fps画面収録→30fps、上下逆さま回転メタデータの正規化、処理時間目安（Brain実測: 試作4〜22分、本編9〜48分）を SKILL.md に明記。

## v3 追補（検証2で確定）
- 画面インセット（author プリセット）: 下端が H×0.83 を超える場合は上余白・左余白・アスペクトを保ったまま縮小する（16:9 収録では幅 0.80W・下端 895px）。本人動画の下端 895px と takkatw の 927px の双方と整合し、字幕帯と重ならない。
- 字幕分割: Whisper セグメント末尾の連結文字列（例「ますよ」）が文末表現ならトークンが1文字でも切る（話者交代の取りこぼし対策）。
- QC: 試作の尺で末尾が切れたキューは「表示時間不足」の対象外。
- 確定既定値は yt-auto-edit/settings.default.json（version v3）。

## v3.1 追補（5分本編のQCで確定）
- 字幕: 表示が短く（min_dur 未満かつ ≤6字）前後との間が 0.4s 未満で字数上限に収まるキューは前（優先）または後ろへ併合。行頭NG文字で始まるキューも同様（引用の「って」は許容）。Whisper セグメント末尾の文末表現（2文字以上一致: ながら／から／けど 等）で必ず切る。
- 音量: loudnorm の目標 TP に audio.tp_headroom（既定 0.5 dB）を足して -1.5 dBTP を狙う。AAC 符号化後の峰超過（+0.3 dB 観測）でも -1.0 dBTP を守るため。参考動画の実測 TP は -1.6〜-2.5。
- QC: 表示時間不足は 0.3s 未満のみ「要修正」、0.3s 以上 min_dur 未満は「確認推奨」（直後に落とした相槌・フィラーや次キューがあり伸ばせないケースが二人トークでは頻出）。
