/**
 * 出演許諾 証票メール送信バックエンド（Google Apps Script ウェブアプリ）
 * ── 運営者控えのみ送信モード ──
 *
 * 役割: フロント（index.html）からPOSTされた証票PNGを、
 *       デプロイした本人（またはOWNER_EMAILで指定した宛先）に「のみ」メール送信する。
 *
 * ▼ セキュリティ設計の要点 ▼
 *  - 宛先は ownerEmail() で決まる: OWNER_EMAIL が空なら「このスクリプトをデプロイした本人」
 *    （Session.getEffectiveUser()）に自動で届く。→ コードを書き換えなくても誤配が起きない。
 *  - クライアントから送られてくる宛先情報（participantEmail / guardianEmail /
 *    recipients / to / cc / bcc 等）は一切読み取らず、完全に無視する。
 *  - したがって、エンドポイントURLとトークンが露出しても、第三者は
 *    「任意の宛先」へは送れない。届くのは運営者本人のメールボックスのみ。
 *  - 乱用されても DAILY_CAP と Gmail 残枠で自動的に止まる。
 *
 *  多重防御:
 *   1) SHARED_TOKEN による bot 除け
 *   2) 証票ID単位の冪等化（同じIDは二重送信しない。キーは送信前に予約し、失敗時は取り消す）
 *   3) 1日あたりの送信上限（DAILY_CAP）＋ Gmail 残枠チェック（日界は日本時間で判定）
 *   4) LockService による同時実行の直列化
 *   5) dataURL の形式検証・添付ファイル名の安全化
 *   6) code / message 形式のエラー返却
 *   7) 古い記録キーの自動削除（30日超。PropertiesServiceの容量枯渇防止）
 *
 * ▼ 設定 ▼
 *  - OWNER_EMAIL  : 通常は空のままでOK（デプロイした本人のGmailに届く）。
 *                   別のアドレスで受け取りたい場合のみ "xxx@example.com" を設定。
 *  - SHARED_TOKEN : フロントの MAIL_TOKEN と必ず同じ値にする（変更しないこと）
 *  - DAILY_CAP    : 1日に送るメール数の上限（Gmail無料枠は約100/日）
 */
var VERSION      = "2.1";
var OWNER_EMAIL  = "";
var SHARED_TOKEN = "yt-consent-883d0d5e9919fec7c85d0217";
var DAILY_CAP    = 90;
var TIMEZONE     = "Asia/Tokyo";   // 日次上限の日界（スクリプトのタイムゾーン設定に依存させない）

function ownerEmail() {
  var e = String(OWNER_EMAIL || "").trim();
  if (!e) { try { e = Session.getEffectiveUser().getEmail(); } catch (ignore) { e = ""; } }
  return /@.+\./.test(e) ? e : "";
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    try { lock.waitLock(15000); } catch (lockErr) { return fail("busy", "混み合っています。少し待って再送してください"); }

    if (!e || !e.postData || !e.postData.contents) {
      return fail("no_body", "送信データが空です");
    }

    var data;
    try { data = JSON.parse(e.postData.contents); }
    catch (parseErr) { return fail("bad_request", "送信データの形式が不正です"); }

    // (1) 合言葉チェック
    if (String(data.token || "") !== SHARED_TOKEN) {
      return fail("unauthorized", "認証エラー（合言葉が一致しません）");
    }

    // 宛先の確定（空なら設定不備として即エラー）
    var owner = ownerEmail();
    if (!owner) {
      return fail("not_configured", "送信先メールを特定できません。Code.gs冒頭のOWNER_EMAILに自分のメールを設定して再デプロイしてください");
    }

    var id = String(data.id || "");
    var props = PropertiesService.getScriptProperties();

    // (2) 冪等化: 同じ証票IDは二重送信しない
    if (id && props.getProperty("sent_" + id)) {
      return json({ ok: true, status: "already_sent", message: "operator copy already sent", owner: maskEmail(owner) });
    }

    // (5) 画像（dataURL）の形式検証 → base64本体を取り出す（MIMEは実体に合わせる）
    var dataUrl = String(data.imageBase64 || "");
    var mimeMatch = dataUrl.match(/^data:image\/(png|jpeg);base64,/);
    if (!mimeMatch) {
      return fail("no_image", "画像データがありません（dataURL形式が不正）");
    }
    var mime = "image/" + mimeMatch[1];
    var ext = mimeMatch[1] === "jpeg" ? ".jpg" : ".png";
    var b64 = dataUrl.replace(/^data:image\/\w+;base64,/, "");
    if (!b64) return fail("no_image", "画像データが空です");
    var bytes = Utilities.base64Decode(b64);
    var blob = Utilities.newBlob(bytes, mime, safe(id || "consent") + ext); // ファイル名の安全化

    // (3) 送信上限チェック（自前の日次上限 ＋ Gmail残枠）。宛先は運営者1件のみ。
    var day = Utilities.formatDate(new Date(), TIMEZONE, "yyyyMMdd");
    var countKey = "count_" + day;
    var used = parseInt(props.getProperty(countKey) || "0", 10);
    if (used === 0) pruneOldKeys(props);   // 日付が変わった最初の送信で古い記録を掃除
    if (used + 1 > DAILY_CAP) return fail("daily_limit", "本日の送信上限に達しました");
    if (MailApp.getRemainingDailyQuota() < 1) return fail("quota_exceeded", "Gmailの本日の送信上限に達しました");

    // メタ情報（すべて運営者の記録用。宛先には一切使わない）
    var name      = String(data.performerName || "出演者");
    var guardian  = String(data.guardianName || "");
    var relation  = String(data.guardianRelation || "");
    var ageKind   = String(data.ageKind || "");
    var when      = String(data.when || "");
    var place     = String(data.place || "");
    var coords    = String(data.coords || "");
    var userAgent = String(data.userAgent || "");

    var subject = "【出演許諾 証票（運営者控え）】" + name + " 様 / " + id + " / " + when;
    var guardianBody = guardian ? ("保護者/署名者: " + guardian + (relation ? "（" + relation + "）" : "") + "\n") : "";
    var body =
      "出演許諾の証票（運営者控え）です。\n\n" +
      "──────────────\n" +
      "証票ID: " + id + "\n" +
      "区分: " + ageKind + "\n" +
      "出演者: " + name + "\n" +
      guardianBody +
      "撮影日時: " + when + "\n" +
      "撮影場所: " + place + "\n" +
      (coords ? "座標: " + coords + "\n" : "") +
      (userAgent ? "端末(UA): " + userAgent + "\n" : "") +
      "──────────────\n\n" +
      "このメールは運営者控えのみです。出演者・保護者/署名者には自動送信していません。\n" +
      "出演者へ控えが必要な場合は、添付の証票を運営者が個別にお渡しください。\n";

    // 冪等キーを「送信前」に予約する。送信直後～記録前に実行が中断（GAS実行上限killなど）
    // しても、再送時にこのキーで弾けるため二重送信を防げる。送信自体が失敗したらロールバックする。
    if (id) props.setProperty("sent_" + id, JSON.stringify({ at: new Date().toISOString(), pending: true }));

    try {
      // (★) 宛先は ownerEmail() 固定。to/cc/bcc をクライアントから受け付けない。
      MailApp.sendEmail(owner, subject, body, {
        attachments: [blob],
        name: "YouTube出演許諾"
      });
    } catch (sendErr) {
      if (id) props.deleteProperty("sent_" + id);   // 送信失敗時は予約を取り消して再送可能にする
      throw sendErr;
    }

    // 記録確定（日次カウント＋冪等キー）
    props.setProperty(countKey, String(used + 1));
    if (id) props.setProperty("sent_" + id, JSON.stringify({ at: new Date().toISOString() }));

    return json({ ok: true, status: "sent", message: "operator copy sent", owner: maskEmail(owner) });
  } catch (err) {
    return fail("server_error", String(err));
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}

// 動作確認用（ブラウザで /exec を開くと {ok:true, owner:"da***e@gmail.com"} が返る）
// アプリの「接続テスト」もこれを使い、控え先メール（伏せ字）を表示して設定ミスを防ぐ。
function doGet() {
  var owner = ownerEmail();
  if (!owner) {
    return json({ ok: false, code: "not_configured", message: "送信先メールを特定できません。Code.gs冒頭のOWNER_EMAILに自分のメールを設定して再デプロイしてください" });
  }
  return json({ ok: true, status: "ready", service: "consent-mailer (owner-only)", version: VERSION, owner: maskEmail(owner) });
}

// 30日より古い記録キー（count_YYYYMMDD / sent_CONSENT-YYYYMMDD-…）を削除（容量枯渇防止）
function pruneOldKeys(props) {
  try {
    var cutoff = Number(Utilities.formatDate(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), TIMEZONE, "yyyyMMdd"));
    var keys = props.getKeys();
    for (var i = 0; i < keys.length; i++) {
      var m = keys[i].match(/^count_(\d{8})$/) || keys[i].match(/^sent_CONSENT-(\d{8})-/);
      if (m && Number(m[1]) < cutoff) props.deleteProperty(keys[i]);
    }
  } catch (ignore) {}
}

function safe(s) {
  return String(s).replace(/[^\w\-.]/g, "_");
}
// 控え先メールの伏せ字化（例: daisuke.n0520@gmail.com → da***0@gmail.com）
function maskEmail(e) {
  e = String(e || "");
  var at = e.indexOf("@");
  if (at < 1) return "***";
  var name = e.slice(0, at), dom = e.slice(at);
  var head = name.slice(0, Math.min(2, name.length));
  var tail = name.length > 3 ? name.slice(-1) : "";
  return head + "***" + tail + dom;
}
function fail(code, message) {
  return json({ ok: false, code: code, message: message });
}
function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
