"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const values = new Map([["owner_email", "owner@example.com"]]);
const sent = [];
let lockWaits = 0;
let throwOnSend = false;

const props = {
  getProperty: key => values.has(key) ? values.get(key) : null,
  setProperty: (key, value) => values.set(key, String(value)),
  deleteProperty: key => values.delete(key),
  getKeys: () => [...values.keys()]
};
const context = {
  console: { error() {}, log() {} },
  Logger: { log() {} },
  Session: { getEffectiveUser: () => ({ getEmail: () => "" }) },
  PropertiesService: { getScriptProperties: () => props },
  LockService: { getScriptLock: () => ({ waitLock() { lockWaits++; }, releaseLock() {} }) },
  MailApp: {
    getRemainingDailyQuota: () => 100,
    sendEmail(to, subject, body, options) {
      if (throwOnSend) throw new Error("internal mail detail");
      sent.push({ to, subject, body, options });
    }
  },
  Utilities: {
    DigestAlgorithm: { SHA_256: "SHA_256" },
    base64Decode: value => [...Buffer.from(value, "base64")],
    computeDigest: (_algorithm, bytes) => [...crypto.createHash("sha256").update(Buffer.from(bytes)).digest()],
    newBlob: (bytes, mime, name) => ({ bytes, mime, name }),
    formatDate: date => new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit"
    }).format(date).replaceAll("-", "")
  },
  ContentService: {
    MimeType: { JSON: "application/json" },
    createTextOutput(text) { return { text, setMimeType() { return this; } }; }
  }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "apps-script", "Code.gs"), "utf8"), context);

const token = context.SHARED_TOKEN;
const png = Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a,0x00,0x01,0x02,0x03]);
const pngUrl = "data:image/png;base64," + png.toString("base64");
const pngHash = crypto.createHash("sha256").update(png).digest("hex");
const request = overrides => ({ postData: { contents: JSON.stringify({
  token,
  imageBase64: pngUrl,
  id: "CONSENT-20260801-0123456789ABCDEF",
  performerName: "山田 太郎",
  guardianName: "残してはいけない保護者",
  guardianRelation: "母",
  ageCode: "adult",
  ageKind: "本人（18歳以上）",
  when: "2026/08/01 12:34:56",
  place: "GPS座標（下記）",
  coords: "緯度 35.000000 / 経度 139.000000（±10m）",
  consentVersion: "2026-08-01.1",
  consentHash: "a".repeat(64),
  evidenceHash: "b".repeat(64),
  certificateHash: pngHash,
  userAgent: "test",
  ...overrides
}) } });
const response = event => JSON.parse(context.doPost(event).text);

assert.equal(response({ postData: { contents: "null" } }).code, "bad_request");
assert.equal(response(request({ token: "wrong" })).code, "unauthorized");
assert.equal(lockWaits, 0, "認証前にロックを取得しています");
assert.equal(response(request({ id: "" })).code, "invalid_id");
assert.equal(response(request({ id: "CONSENT-20260801-GGGGGGGGGGGGGGGG" })).code, "invalid_id");
assert.equal(lockWaits, 0, "ID検証前にロックを取得しています");
assert.equal(response(request({ imageBase64: "data:image/png;base64,AAAA" })).code, "no_image");
assert.equal(lockWaits, 0, "画像実体検証前にロックを取得しています");

const first = response(request({}));
assert.equal(first.ok, true);
assert.equal(first.status, "sent");
assert.equal(first.certificateHash, pngHash);
assert.equal(sent.length, 1);
assert.equal(sent[0].to, "owner@example.com");
assert.equal(sent[0].body.includes("残してはいけない保護者"), false, "成人メールに保護者情報が混入しています");
assert.equal(sent[0].body.includes("区分: 本人（18歳以上）"), true, "区分表示がageCodeから正規化されていません");
assert.equal(sent[0].body.includes("添付PNG SHA-256: " + pngHash), true);

const duplicate = response(request({}));
assert.equal(duplicate.status, "already_sent");
assert.equal(sent.length, 1, "同じ証票IDを二重送信しています");

const otherPng = Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a,0x09]);
const conflict = response(request({
  imageBase64: "data:image/png;base64," + otherPng.toString("base64"),
  certificateHash: crypto.createHash("sha256").update(otherPng).digest("hex")
}));
assert.equal(conflict.code, "id_conflict");
assert.equal(sent.length, 1);

const beforeHashFailure = lockWaits;
assert.equal(response(request({ id: "CONSENT-20260801-1111111111111111", certificateHash: "0".repeat(64) })).code, "hash_mismatch");
assert.equal(lockWaits, beforeHashFailure, "ハッシュ検証前にロックを取得しています");

throwOnSend = true;
const failed = response(request({ id: "CONSENT-20260801-2222222222222222" }));
throwOnSend = false;
assert.equal(failed.code, "server_error");
assert.equal(failed.message.includes("internal mail detail"), false, "生の例外を返しています");
assert.equal(values.has("sent_CONSENT-20260801-2222222222222222"), false, "送信失敗時の予約が残っています");

console.log("backend: pass");
