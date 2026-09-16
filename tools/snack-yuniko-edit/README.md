# スナックゆに子 本編編集パイプライン

`スナックゆに子` の収録原本（DJI MP4）から、以下を自動で行う ffmpeg ベースの編集ツールです。
本アプリ（出演許諾 証票作成アプリ）とは独立したユーティリティで、`index.html` 等には影響しません。

- 不要区間のカット（原本秒で指定）
- 左上にトークテーマを常時表示（テロップなし／BIZ UDGothic Bold／白文字＋濃紫アウトライン＋ピンクのアクセントバー）
- SE・ED 音源の配置と ED の音楽・映像フェードアウト
- 台詞の整音（ハイパス／FFT ノイズ除去／ディエッサー／コンプ／EQ／2 パス loudnorm／リミッター）
- QA（仕様・ラウドネス・黒画面・無音・コンタクトシート）

## 使い方

```bash
pip install faster-whisper gdown numpy scipy soundfile
# ffmpeg 7 系（libass 有効ビルド）が必要
python3 transcribe.py raw.MP4 --out work/transcript.json          # 文字起こし（単語タイムスタンプ付き）
python3 se_detect.py raw.MP4 ./se work/se_hits.json               # 収録中に鳴らした SE の位置検出
python3 edit_pipeline.py plan.json --out out.mp4 --workdir work --fonts-dir ./fonts
```

`plan_example.json` が編集プランの例です（フォントは `fonts/BIZUDGothic-Bold.ttf` を配置）。

## #29 を母艦 Mac で再現する（推奨手順）

ローカルの Claude Code（または ターミナル）で次を実行すると、Drive から素材を取り、同一プランで完パケを作り、`~/Downloads/スナックゆに子_29_完パケ.mp4` に保存します。

```bash
cd ~/Movies && git clone -b claude/confident-babbage-jpimz9 https://github.com/DaisukeNAKA/youtube-consent.git snack_yuniko_repo
bash ~/Movies/snack_yuniko_repo/tools/snack-yuniko-edit/reproduce_29.sh
```

- 原本 `DJI_20260915135827_0021_D.MP4` が Mac 上にある場合は、そのパスを第1引数に渡すと Drive からの取得（10.9GB）を省略できます。
- 必要なもの: Homebrew の ffmpeg（無ければ自動導入）、Python 3（macOS 標準）。フォント（BIZ UDGothic Bold）と SE は自動取得します。
- 動作確認済みの出力仕様: 1920×1080 / 30fps / H.264 / AAC 48kHz、約 −13 LUFS。QA は `~/Movies/snack_yuniko_29/work/qa_report.json`。

### ローカルの Claude Code に貼る指示文

> GitHub の DaisukeNAKA/youtube-consent のブランチ claude/confident-babbage-jpimz9 を ~/Movies/snack_yuniko_repo にクローン（既にあれば pull）し、tools/snack-yuniko-edit/reproduce_29.sh を実行して「スナックゆに子 #29」の完パケを作ってください。原本 DJI_20260915135827_0021_D.MP4 がこの Mac 上にあればそのパスを第1引数に渡し、無ければ引数なしで実行（Drive から自動取得）。完成品は ~/Downloads/スナックゆに子_29_完パケ.mp4 に出ます。途中で確認を挟まず最後まで進め、エラーが出たら内容と対処案を報告してください。
