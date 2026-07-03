/**
 * 出演許諾 証票メール送信バックエンド（Google Apps Script ウェブアプリ）
 *
 * 役割: フロント（index.html）からPOSTされた証票PNGを、
 *       出演者（および保護者）と運営者にメール送信する。
 *       送信元は、このスクリプトを所有するGoogleアカウント（＝運営者のGmail）。
 *
 * ▼ セキュリティ設計（重要） ▼
 *  このウェブアプリは「アクセス: 全員」で公開する必要があり（静的サイトからfetchするため）、
 *  合言葉トークンは公開HTMLに含まれるため“完全な秘密”にはできません。
 *  そこで乱用の被害を限定するために、以下の多重防御を実装しています:
 *   1) SHARED_TOKEN による bot 除け
 *   2) 送信先の一方（運営者控え）はサーバ側で固定（クライアントから変更不可）
 *   3) 証票ID単位の冪等化（同じIDは二重送信しない＝再送しても重複しない）
 *   4) 1日あたりの送信上限（DAILY_CAP）＋ Gmail残枠チェック（枠枯渇＝業務メール停止の防止）
 *   5) LockService による同時実行の直列化
 *  それでも「トークンを知る第三者が、運営者のGmail名義で最大 DAILY_CAP 通/日を送れる」
 *  残余リスクは残ります。より強固にしたい場合は README のセキュリティ節を参照。
 *
 * ▼ 設定 ▼
 *  - OPERATOR_EMAIL : 運営者の控え宛先（固定。クライアントからは変更不可）
 *  - SHARED_TOKEN   : フロントの MAIL_TOKEN と必ず同じ値にする
 *  - DAILY_CAP      : 1日に送る「宛先数」の上限（Gmail無料枠は約100/日）
 */
var OPERATOR_EMAIL = "daisuke.n0520@gmail.com";
var SHARED_TOKEN   = "yt-consent-883d0d5e9919fec7c85d0217";
var DAILY_CAP      = 90;

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    try { lock.waitLock(15000); } catch (lockErr) { return json({ ok: false, error: "busy" }); }

    if (!e || !e.postData || !e.postData.contents) {
      return json({ ok: false, error: "no_body" });
    }
    var data = JSON.parse(e.postData.contents);

    // (1) 合言葉チェック
    if (String(data.token || "") !== SHARED_TOKEN) {
      return json({ ok: false, error: "unauthorized" });
    }

    var id = String(data.id || "");
    var props = PropertiesService.getScriptProperties();

    // (3) 冪等化: 同じ証票IDは二重送信しない
    if (id) {
      var prev = props.getProperty("sent_" + id);
      if (prev) {
        var p = JSON.parse(prev);
        return json({ ok: true, sentTo: p.sentTo, dedup: true });
      }
    }

    // 画像（data URL → base64本体）
    var b64 = String(data.imageBase64 || "").replace(/^data:image\/\w+;base64,/, "");
    if (!b64) return json({ ok: false, error: "no_image" });
    var bytes = Utilities.base64Decode(b64);
    var blob = Utilities.newBlob(bytes, "image/png", safe(id || "consent") + ".png");

    // 宛先（出演者・保護者。形式が正しいものだけ採用）＋ 運営者は常に控えを受領
    var recipients = [];
    if (isEmail(data.signerEmail))   recipients.push(String(data.signerEmail).trim());
    if (isEmail(data.guardianEmail)) recipients.push(String(data.guardianEmail).trim());
    var recipientCount = recipients.length + 1; // + 運営者

    // (4) 送信上限チェック（自前の日次上限 ＋ Gmail残枠）
    var tz = Session.getScriptTimeZone() || "Asia/Tokyo";
    var day = Utilities.formatDate(new Date(), tz, "yyyyMMdd");
    var countKey = "count_" + day;
    var used = parseInt(props.getProperty(countKey) || "0", 10);
    if (used + recipientCount > DAILY_CAP) return json({ ok: false, error: "daily_limit" });
    if (MailApp.getRemainingDailyQuota() < recipientCount) return json({ ok: false, error: "quota_exceeded" });

    // メタ情報
    var name     = String(data.performerName || "出演者");
    var guardian = String(data.guardianName || "");
    var relation = String(data.guardianRelation || "");
    var ageKind  = String(data.ageKind || "");
    var when     = String(data.when || "");
    var place    = String(data.place || "");
    var coords    = String(data.coords || "");

    var guardianLine = guardian ? ("\n保護者: " + guardian + (relation ? "（" + relation + "）" : "")) : "";
    var subject = "【出演許諾 証票】" + name + " 様 / " + id;
    var body =
      name + " 様" + (guardian ? "（保護者 " + guardian + " 様）" : "") + "\n\n" +
      "本日はご出演の許諾をいただき、誠にありがとうございました。\n" +
      "出演許諾の証票（控え）を添付にてお送りします。大切に保管してください。\n\n" +
      "──────────────\n" +
      "証票ID: " + id + "\n" +
      "区分: " + ageKind + "\n" +
      "出演者: " + name + guardianLine + "\n" +
      "撮影日時: " + when + "\n" +
      "撮影場所: " + place + "\n" +
      (coords ? "座標: " + coords + "\n" : "") +
      "──────────────\n\n" +
      "※本メールは出演許諾の記録として自動送信されています。\n" +
      "※内容に心当たりがない場合は、お手数ですが本メールにご返信ください。\n";

    var options = { attachments: [blob], name: "YouTube出演許諾" };

    var sentTo;
    if (recipients.length > 0) {
      options.bcc = OPERATOR_EMAIL;              // 運営者はBCCで控えを受領
      MailApp.sendEmail(recipients.join(","), subject, body, options);
      sentTo = recipients.slice();
      sentTo.push("運営者控え");
    } else {
      MailApp.sendEmail(OPERATOR_EMAIL, subject, body, options);
      sentTo = ["運営者控え"];
    }

    // 記録（日次カウント＋冪等キー）
    props.setProperty(countKey, String(used + recipientCount));
    if (id) props.setProperty("sent_" + id, JSON.stringify({ sentTo: sentTo, at: new Date().toISOString() }));

    return json({ ok: true, sentTo: sentTo });
  } catch (err) {
    return json({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}

// 動作確認用（ブラウザで /exec を開くと {ok:true} が返る）
function doGet() {
  return json({ ok: true, service: "consent-mailer" });
}

function isEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(s || "").trim());
}
function safe(s) {
  return String(s).replace(/[^\w\-.]/g, "_");
}
function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
