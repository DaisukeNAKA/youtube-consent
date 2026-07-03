/**
 * 出演許諾 証票メール送信バックエンド（Google Apps Script ウェブアプリ）
 * ── 運営者控えのみ送信モード ──
 *
 * 役割: フロント（index.html）からPOSTされた証票PNGを、
 *       サーバ側で固定した運営者アドレス（OWNER_EMAIL）に「のみ」メール送信する。
 *
 * ▼ セキュリティ設計の要点 ▼
 *  - 宛先はこのファイル内の定数 OWNER_EMAIL に固定。
 *  - クライアントから送られてくる宛先情報（participantEmail / guardianEmail /
 *    recipients / to / cc / bcc 等）は一切読み取らず、完全に無視する。
 *  - したがって、エンドポイントURLとトークンが露出しても、第三者は
 *    「任意の宛先」へは送れない。届くのは運営者本人のメールボックスのみ。
 *  - 乱用されても DAILY_CAP と Gmail 残枠で自動的に止まる。
 *
 *  既存の多重防御は維持:
 *   1) SHARED_TOKEN による bot 除け
 *   2) 証票ID単位の冪等化（同じIDは二重送信しない＝再送しても重複しない）
 *   3) 1日あたりの送信上限（DAILY_CAP）＋ Gmail 残枠チェック
 *   4) LockService による同時実行の直列化
 *   5) dataURL の形式検証・PNG添付ファイル名の安全化
 *   6) code / message 形式のエラー返却
 *
 * ▼ 設定 ▼
 *  - OWNER_EMAIL  : 運営者の宛先（唯一の送信先。クライアントからは変更不可）
 *  - SHARED_TOKEN : フロントの MAIL_TOKEN と必ず同じ値にする
 *  - DAILY_CAP    : 1日に送るメール数の上限（Gmail無料枠は約100/日）
 */
var OWNER_EMAIL  = "daisuke.n0520@gmail.com";
var SHARED_TOKEN = "yt-consent-883d0d5e9919fec7c85d0217";
var DAILY_CAP    = 90;

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

    var id = String(data.id || "");
    var props = PropertiesService.getScriptProperties();

    // (2) 冪等化: 同じ証票IDは二重送信しない
    if (id && props.getProperty("sent_" + id)) {
      return json({ ok: true, status: "already_sent", message: "operator copy already sent" });
    }

    // (5) 画像（dataURL）の形式検証 → base64本体を取り出す
    var dataUrl = String(data.imageBase64 || "");
    if (!/^data:image\/(png|jpeg);base64,/.test(dataUrl)) {
      return fail("no_image", "画像データがありません（dataURL形式が不正）");
    }
    var b64 = dataUrl.replace(/^data:image\/\w+;base64,/, "");
    if (!b64) return fail("no_image", "画像データが空です");
    var bytes = Utilities.base64Decode(b64);
    var blob = Utilities.newBlob(bytes, "image/png", safe(id || "consent") + ".png"); // ファイル名の安全化

    // (3) 送信上限チェック（自前の日次上限 ＋ Gmail残枠）。宛先は運営者1件のみ。
    var tz = Session.getScriptTimeZone() || "Asia/Tokyo";
    var day = Utilities.formatDate(new Date(), tz, "yyyyMMdd");
    var countKey = "count_" + day;
    var used = parseInt(props.getProperty(countKey) || "0", 10);
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
      // (★) 宛先は OWNER_EMAIL 固定。to/cc/bcc をクライアントから受け付けない。
      MailApp.sendEmail(OWNER_EMAIL, subject, body, {
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

    return json({ ok: true, status: "sent", message: "operator copy sent" });
  } catch (err) {
    return fail("server_error", String(err));
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}

// 動作確認用（ブラウザで /exec を開くと {ok:true} が返る）
function doGet() {
  return json({ ok: true, status: "ready", service: "consent-mailer (owner-only)" });
}

function safe(s) {
  return String(s).replace(/[^\w\-.]/g, "_");
}
function fail(code, message) {
  return json({ ok: false, code: code, message: message });
}
function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
