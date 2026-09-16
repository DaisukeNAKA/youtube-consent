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
