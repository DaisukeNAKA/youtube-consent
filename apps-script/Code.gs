/**
 * 出演許諾 証票メール送信バックエンド（Google Apps Script ウェブアプリ）
 * ── 運営者控えのみ送信モード ──
 *
 * 役割: フロント（index.html）からPOSTされた証票PNGを、
 *       デプロイした本人（またはOWNER_EMAILで指定した宛先）に「のみ」メール送信する。
 *
 * ▼ セキュリティ設計の要点 ▼
 *  - 宛先は ownerEmail() で決まる。OWNER_EMAILを明示するか、エディタでsetup()を実行する。
 *    匿名ウェブアプリ実行では本人メールを取得できないため、未設定なら安全に停止する。
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
 *   5) ID・入力長・dataURL・画像サイズ・画像実体の検証
 *   6) code / message 形式のエラー返却
 *   7) 古い記録キーの自動削除（30日超。PropertiesServiceの容量枯渇防止）
 *
 * ▼ 設定 ▼
 *  - OWNER_EMAIL  : ★必須★ 自分のメールアドレスを "" の中に記入（控えの届き先）。
 *                   例) var OWNER_EMAIL = "taro@gmail.com";
 *                   タイプミスが心配な場合は、記入せずエディタ上部の関数選択で「setup」を
 *                   選んで実行すると、自分のアドレスが自動登録される（どちらか一方でOK）。
 *                   ※未設定の場合は誤配せず not_configured エラーで安全に止まる。
 *  - SHARED_TOKEN : フロントの MAIL_TOKEN と必ず同じ値にする（変更しないこと）
 *  - DAILY_CAP    : 1日に送るメール数の上限（Gmail無料枠は約100/日）
 */
var VERSION      = "2.2.0";
var OWNER_EMAIL  = "";
var SHARED_TOKEN = "yt-consent-883d0d5e9919fec7c85d0217";
var DAILY_CAP    = 90;
var TIMEZONE     = "Asia/Tokyo";   // 日次上限の日界（スクリプトのタイムゾーン設定に依存させない）
var MAX_BODY_CHARS = 14 * 1024 * 1024;
var MAX_IMAGE_BYTES = 10 * 1024 * 1024;
var ID_RE = /^CONSENT-\d{8}-(?:[A-Z0-9]{5}|[A-F0-9]{16})$/;  // 旧5桁base36 ID / 新16桁hex ID
var SHA256_RE = /^[a-f0-9]{64}$/;

// タイプミスなしで控え先を登録する補助関数。エディタで「setup」を選んで実行→承認すると
// 自分のアドレスが保存される（Webアプリの匿名実行では本人特定できないため、エディタ実行が必要）。
function setup() {
  var e = Session.getEffectiveUser().getEmail();
  if (!/@.+\./.test(e)) throw new Error("メールアドレスを取得できませんでした。OWNER_EMAILに直接記入してください");
  PropertiesService.getScriptProperties().setProperty("owner_email", e);
  Logger.log("控え先を設定しました: " + e);
}

function ownerEmail() {
  var e = String(OWNER_EMAIL || "").trim();
  if (!e) { try { e = String(PropertiesService.getScriptProperties().getProperty("owner_email") || ""); } catch (ignore) {} }
  if (!e) { try { e = Session.getEffectiveUser().getEmail(); } catch (ignore) { e = ""; } }  // 環境によっては空
  return /@.+\./.test(e) ? e : "";
}

function doPost(e) {
  var lock = null;
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return fail("no_body", "送信データが空です");
    }
    var raw = String(e.postData.contents);
    if (raw.length > MAX_BODY_CHARS) {
      return fail("image_too_large", "証票画像が大きすぎます。撮影し直してください");
    }

    var data;
    try { data = JSON.parse(raw); }
    catch (parseErr) { return fail("bad_request", "送信データの形式が不正です"); }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return fail("bad_request", "送信データの形式が不正です");
    }

    // 安価な検証はロック取得前に行い、無効リクエストで送信処理を詰まらせない。
    if (String(data.token || "") !== SHARED_TOKEN) {
      return fail("unauthorized", "認証エラー（合言葉が一致しません）");
    }

    var id = String(data.id || "").trim();
    if (!ID_RE.test(id)) {
      return fail("invalid_id", "証票IDを確認できません。証票を作り直してください");
    }

    var dataUrl = String(data.imageBase64 || "");
    var mimeMatch = dataUrl.match(/^data:image\/(png|jpeg);base64,/);
    if (!mimeMatch) {
      return fail("no_image", "画像データがありません（dataURL形式が不正）");
    }
    var b64 = dataUrl.slice(mimeMatch[0].length);
    if (!b64) return fail("no_image", "画像データが空です");
    if (Math.floor(b64.length * 3 / 4) > MAX_IMAGE_BYTES) {
      return fail("image_too_large", "証票画像が大きすぎます。撮影し直してください");
    }

    var name = cleanText(data.performerName, 80);
    var guardian = cleanText(data.guardianName, 80);
    var relation = cleanText(data.guardianRelation, 30);
    var ageKind = cleanText(data.ageKind, 60);
    var ageCode = cleanText(data.ageCode, 10);
    var when = cleanText(data.when, 32);
    var place = cleanText(data.place, 120);
    var coords = cleanText(data.coords, 120);
    var userAgent = cleanText(data.userAgent, 500);
    var consentVersion = cleanText(data.consentVersion, 40);
    var consentHash = String(data.consentHash || "").toLowerCase();
    var evidenceHash = String(data.evidenceHash || "").toLowerCase();
    var suppliedCertHash = String(data.certificateHash || "").toLowerCase();
    if ([name, guardian, relation, ageKind, ageCode, when, place, coords, userAgent, consentVersion].some(function(v) { return v === null; })) {
      return fail("invalid_field", "入力内容が長すぎます。証票を作り直してください");
    }
    if (!name || !when || !ageKind) return fail("invalid_field", "証票の記録項目が不足しています");
    if (ageCode !== "adult" && ageCode !== "minor") {
      ageCode = ageKind.indexOf("18歳未満") >= 0 ? "minor" : (ageKind.indexOf("18歳以上") >= 0 ? "adult" : "");
    }
    if (!ageCode) return fail("invalid_field", "出演者の区分を確認できません");
    if (ageCode === "minor" && !guardian) return fail("invalid_field", "保護者氏名を確認できません");
    if (ageCode === "adult") { guardian = ""; relation = ""; }
    ageKind = ageCode === "minor" ? "18歳未満（保護者同意あり）" : "本人（18歳以上）";
    if ((consentHash && !SHA256_RE.test(consentHash)) ||
        (evidenceHash && !SHA256_RE.test(evidenceHash)) ||
        (suppliedCertHash && !SHA256_RE.test(suppliedCertHash))) {
      return fail("invalid_field", "証票の確認情報が不正です");
    }

    // 宛先の確定（空なら設定不備として即エラー）
    var owner = ownerEmail();
    if (!owner) {
      return fail("not_configured", "送信先メールを特定できません。Code.gs冒頭のOWNER_EMAILに自分のメールを設定して再デプロイしてください");
    }

    var mime = "image/" + mimeMatch[1];
    var ext = mimeMatch[1] === "jpeg" ? ".jpg" : ".png";
    var bytes;
    try { bytes = Utilities.base64Decode(b64); }
    catch (decodeErr) { return fail("no_image", "証票画像を読み取れません。証票を作り直してください"); }
    if (!bytes || !bytes.length || bytes.length > MAX_IMAGE_BYTES || !matchesImageSignature(bytes, mime)) {
      return fail("no_image", "証票画像を確認できません。証票を作り直してください");
    }
    var actualCertHash = sha256Hex(bytes);
    if (suppliedCertHash && suppliedCertHash !== actualCertHash) {
      return fail("hash_mismatch", "証票の整合性を確認できません。証票を作り直してください");
    }
    var blob = Utilities.newBlob(bytes, mime, safe(id) + ext);

    lock = LockService.getScriptLock();
    try { lock.waitLock(15000); } catch (lockErr) { return fail("busy", "混み合っています。少し待って再送してください"); }
    var props = PropertiesService.getScriptProperties();

    // 同じ証票IDは二重送信しない。
    var sentRecord = props.getProperty("sent_" + id);
    if (sentRecord) {
      try {
        var previous = JSON.parse(sentRecord);
        if (previous.hash && previous.hash !== actualCertHash) {
          return fail("id_conflict", "同じ証票IDで異なる画像が指定されています。証票を作り直してください");
        }
      } catch (ignore) {}
      return json({ ok: true, status: "already_sent", message: "operator copy already sent", owner: maskEmail(owner), certificateHash: actualCertHash });
    }

    // 送信上限チェック（自前の日次上限 ＋ Gmail残枠）。宛先は運営者1件のみ。
    var day = Utilities.formatDate(new Date(), TIMEZONE, "yyyyMMdd");
    var countKey = "count_" + day;
    var used = parseInt(props.getProperty(countKey) || "0", 10);
    if (!isFinite(used) || used < 0) used = 0;
    if (used === 0) pruneOldKeys(props);   // 日付が変わった最初の送信で古い記録を掃除
    if (used + 1 > DAILY_CAP) return fail("daily_limit", "本日の送信上限に達しました");
    if (MailApp.getRemainingDailyQuota() < 1) return fail("quota_exceeded", "Gmailの本日の送信上限に達しました");

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
      (consentVersion ? "同意文面版: " + consentVersion + "\n" : "") +
      (consentHash ? "同意文面SHA-256: " + consentHash + "\n" : "") +
      (evidenceHash ? "証跡SHA-256: " + evidenceHash + "\n" : "") +
      "添付PNG SHA-256: " + actualCertHash + "\n" +
      (userAgent ? "端末(UA): " + userAgent + "\n" : "") +
      "──────────────\n\n" +
      "このメールは運営者控えのみです。出演者・保護者/署名者には自動送信していません。\n" +
      "出演者へ控えが必要な場合は、添付の証票を運営者が個別にお渡しください。\n";

    // 冪等キーを「送信前」に予約する。送信直後～記録前に実行が中断（GAS実行上限killなど）
    // しても、再送時にこのキーで弾けるため二重送信を防げる。送信自体が失敗したらロールバックする。
    props.setProperty("sent_" + id, JSON.stringify({ at: new Date().toISOString(), pending: true, hash: actualCertHash }));

    try {
      // (★) 宛先は ownerEmail() 固定。to/cc/bcc をクライアントから受け付けない。
      MailApp.sendEmail(owner, subject, body, {
        attachments: [blob],
        name: "YouTube出演許諾"
      });
    } catch (sendErr) {
      props.deleteProperty("sent_" + id);   // 送信失敗時は予約を取り消して再送可能にする
      throw sendErr;
    }

    // 記録確定（日次カウント＋冪等キー）
    props.setProperty(countKey, String(used + 1));
    props.setProperty("sent_" + id, JSON.stringify({ at: new Date().toISOString(), hash: actualCertHash }));

    return json({ ok: true, status: "sent", message: "operator copy sent", owner: maskEmail(owner), certificateHash: actualCertHash });
  } catch (err) {
    try { console.error("doPost failed", err && err.stack ? err.stack : err); } catch (ignore) {}
    return fail("server_error", "サーバ側で処理できませんでした。少し待って再送してください");
  } finally {
    if (lock) { try { lock.releaseLock(); } catch (ignore) {} }
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
      var countMatch = keys[i].match(/^count_(\d{8})$/);
      var sentMatch = keys[i].match(/^sent_CONSENT-(\d{8})-(?:[A-Z0-9]{5}|[A-F0-9]{16})$/);
      if (/^sent_/.test(keys[i]) && !sentMatch) props.deleteProperty(keys[i]);
      else {
        var m = countMatch || sentMatch;
        if (m && Number(m[1]) < cutoff) props.deleteProperty(keys[i]);
      }
    }
  } catch (ignore) {}
}

function cleanText(value, maxLength) {
  var s = String(value || "").replace(/[\u0000-\u001f\u007f]/g, " ").trim();
  return s.length <= maxLength ? s : null;
}
function matchesImageSignature(bytes, mime) {
  function b(i) { return (bytes[i] + 256) % 256; }
  if (mime === "image/png") return bytes.length >= 8 && b(0) === 0x89 && b(1) === 0x50 && b(2) === 0x4e && b(3) === 0x47 && b(4) === 0x0d && b(5) === 0x0a && b(6) === 0x1a && b(7) === 0x0a;
  return bytes.length >= 3 && b(0) === 0xff && b(1) === 0xd8 && b(2) === 0xff;
}
function sha256Hex(bytes) {
  var digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes);
  return digest.map(function(v) { return ((v + 256) % 256).toString(16).padStart(2, "0"); }).join("");
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
