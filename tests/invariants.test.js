"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const index = fs.readFileSync(path.join(root, "index.html"), "utf8");
const gas = fs.readFileSync(path.join(root, "apps-script", "Code.gs"), "utf8");
const sw = fs.readFileSync(path.join(root, "sw.js"), "utf8");

const token = source => source.match(/(?:MAIL_TOKEN|SHARED_TOKEN)\s*=\s*"([^"]+)"/)[1];
assert.equal(token(index), token(gas), "フロントとGASのトークンが一致していません");
assert.match(index, /const MAIL_ENDPOINT_DEFAULT\s*=\s*""/, "既定のGAS宛先URLは空でなければなりません");
assert.match(gas, /var OWNER_EMAIL\s*=\s*""/, "リポジトリのOWNER_EMAILは空でなければなりません");
assert.match(index, /"Content-Type":"text\/plain;charset=utf-8"/, "GAS POSTはプリフライトを起こさないtext/plainが必要です");

const payload = index.slice(index.indexOf("function mailPayload"), index.indexOf("async function sendMail"));
for (const forbidden of ["participantEmail", "guardianEmail", "recipients", "\"to\"", "\"cc\"", "\"bcc\""]) {
  assert.equal(payload.includes(forbidden), false, `フロントpayloadに禁止宛先フィールド ${forbidden} があります`);
}

const doPost = gas.slice(gas.indexOf("function doPost"), gas.indexOf("function doGet"));
for (const forbidden of [/data\.participantEmail\b/, /data\.guardianEmail\b/, /data\.recipients\b/, /data\.to\b/, /data\.cc\b/, /data\.bcc\b/]) {
  assert.equal(forbidden.test(doPost), false, `GASが禁止宛先フィールド ${forbidden} を参照しています`);
}
assert.equal((gas.match(/MailApp\.sendEmail\(/g) || []).length, 1, "メール送信箇所は1つだけでなければなりません");
assert.match(gas, /MailApp\.sendEmail\(owner,/, "メール宛先はownerEmail由来のowner固定でなければなりません");
assert.doesNotMatch(gas, /fail\("server_error",\s*String\(err\)\)/, "生の例外を利用者へ返してはいけません");

assert.equal(/nominatim/i.test(index + sw), false, "公開Nominatimへの依存が残っています");
assert.equal(index.includes("Math.random"), false, "証票IDにMath.randomを使ってはいけません");
assert.equal(index.includes("innerHTML"), false, "ネットワーク値を誤挿入しやすいinnerHTMLを使ってはいけません");
assert.match(sw, /await cache\.put\(/, "Service Workerのキャッシュ更新を完了まで待つ必要があります");

const scripts = [...index.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(match => match[1]).filter(Boolean);
for (const source of scripts) new Function(source);

console.log("invariants: pass");
