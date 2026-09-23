# Codex への依頼：スナックゆに子 #29 を YouTube と stand.fm に投稿する

素材はすべてこのフォルダ（tools/snack-yuniko-edit/deliverables/29/）と ~/Downloads にあります。
内容（動画・サムネイル・文言）は変更せず、投稿作業のみ行ってください。認証情報が見つからない、または投稿に本人の操作が必要な場合は、その箇所だけ本人に確認してください。

## 素材
- 完パケ動画: `~/Downloads/スナックゆに子_29_完パケ.mp4`（37分48秒、1920×1080/30fps）
- サムネイル: `thumbnail_29.jpg`（1280×720）
- YouTube タイトル: `youtube_title.txt`
- YouTube 概要欄: `youtube_description.txt`（`{{STANDFM_EPISODE_URL}}` を stand.fm 投稿後の URL に置換して使用）
- YouTube タグ: `youtube_tags.txt`（カンマ区切り）
- stand.fm タイトル: `standfm_title.txt`
- stand.fm 説明文: `standfm_description.txt`（`{{YOUTUBE_URL}}` を YouTube 投稿後の URL に置換して使用）
- チャプター: `chapters_29.txt`（概要欄に含めてあります）

## 手順
1. `cd ~/Movies/snack_yuniko_repo && git pull`
2. 音声版を書き出す（Homebrew の ffmpeg 導入済み）:
   `ffmpeg -y -i "$HOME/Downloads/スナックゆに子_29_完パケ.mp4" -vn -c:a aac -b:a 128k -ar 48000 -ac 2 -movflags +faststart "$HOME/Downloads/スナックゆに子_29_音声.m4a"`
3. stand.fm（チャンネル「スナックゆに子」 https://stand.fm/channels/60f6848304bb1691c1fdd0e4 ）に音声版を投稿:
   - タイトル: standfm_title.txt、説明文: standfm_description.txt（`{{YOUTUBE_URL}}` はいったん「YouTube にも公開予定」と記載し、手順 5 で差し替え）
   - 公開設定: 公開
   - 投稿後のエピソード URL を控える
4. YouTube（チャンネル「ユニコちゃんねる」 UCuwkUkClDI-EX_RO5p-O29A ）に投稿:
   - 動画: 完パケ、タイトル: youtube_title.txt、概要欄: youtube_description.txt の `{{STANDFM_EPISODE_URL}}` を手順 3 の URL に置換、タグ: youtube_tags.txt
   - サムネイル: thumbnail_29.jpg、カテゴリ: エンターテイメント、言語: 日本語、子ども向け: いいえ
   - 再生リスト「スナックゆに子」があれば追加、公開設定: 公開（既存回と同じ）
   - 投稿後の動画 URL を控える
5. stand.fm の説明文の `{{YOUTUBE_URL}}` を手順 4 の URL に更新
6. 完了報告: YouTube URL、stand.fm URL、公開設定、投稿日時を本人に報告
