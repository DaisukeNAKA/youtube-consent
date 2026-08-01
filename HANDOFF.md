# HANDOFF — youtube-consent (AI agent handoff spec)

> Audience: an AI coding agent taking over development. Optimized for machine parsing, not human prose.
> Language: JA for user-facing strings, EN for spec. Read this file completely before any edit.
> Last verified: 2026-08-01 (all "VERIFIED" claims re-checked against live systems on this date).

---

## 1. META

```yaml
project: 出演許諾 証票作成アプリ (YouTube appearance-consent certificate app)
purpose: >
  On-site (filming location) collection of appearance consent from members of the public,
  on the filmer's smartphone. Produces a tamper-evident PNG "証票" (certificate) as legal-ish
  evidence of consent, emailed to the operator only.
repo: https://github.com/DaisukeNAKA/youtube-consent   # PUBLIC
local: /Users/nakatsukadaisuke/youtube-consent
branch: main                                            # single branch, no PR flow, direct push
prod_app: https://daisukenaka.github.io/youtube-consent/
prod_guide: https://daisukenaka.github.io/youtube-consent/guide.html
hosting: GitHub Pages (branch=main, path=/) — auto-deploy on push, 30–60s lag
stack: single-file vanilla HTML/CSS/JS (no build, no deps, no framework, no bundler)
backend: Google Apps Script Web App (per-user deployment; NOT owned/operated centrally)
owner_human: 中塚大輔 (daisuke.n0520@gmail.com) — YouTube channel operator, NON-ENGINEER
audience: the owner + his comedian peers (同期), all non-engineers, iPhone Safari primary
```

**Critical operating context**: the human operator cannot debug code. Any change must fail loudly
with a Japanese, non-technical error message, or not fail at all. Never surface raw exception text.

---

## 2. ARCHITECTURE

```
[iPhone Safari]
  └─ GitHub Pages (static, HTTPS)
       index.html   ← entire SPA: UI + state machine + canvas rendering + mail client
       guide.html   ← standalone visual setup manual for peers
       sw.js        ← service worker, network-first + cache fallback (offline venues)
          │
          └──(POST, cross-origin, text/plain)──> script.google.com/macros/s/<ID>/exec
                                                    apps-script/Code.gs (each user deploys their OWN copy)
                                                       └─ MailApp.sendEmail → that user's own Gmail
```

- **No server owned by us.** No database. No user accounts. No analytics.
- Certificate PNG is generated **client-side** via Canvas 2D and sent as base64 dataURL in the POST body.
  It contains the consent-text version/hash and an evidence hash. GAS independently recomputes the
  attachment PNG SHA-256 and records it in the operator-copy email for later tamper comparison.
- The GAS endpoint URL is stored **per-device** in `localStorage["mailEndpoint"]`. Not in code.
- `Content-Type: text/plain` is deliberate → keeps the POST a CORS "simple request" (no preflight,
  which GAS cannot answer). **Do not change to application/json.**

---

## 3. FILE MAP

| File | Lines | Role | Deploy path |
|---|---|---|---|
| `index.html` | 978 | The entire app (single-file SPA) | Pages, auto |
| `guide.html` | 197 | Visual setup manual for peers (self-contained, inline QR SVG) | Pages, auto |
| `sw.js` | 47 | Service worker (cache `consent-v2`) | Pages, auto |
| `apps-script/Code.gs` | 284 | Mail backend, v2.2.0 | **MANUAL** (see §7) |
| `apps-script/README.md` | 125 | GAS setup runbook (human-facing) | docs only |
| `README.md` | 49 | Repo overview | docs only |
| `tests/smoke.html` | 180 | Browser regression: consent, privacy, evidence, certificate rendering | Pages (localhost-only guard) |
| `tests/invariants.test.js` | 39 | Static enforcement of §4 recipient/security invariants | CI/local |
| `tests/backend.test.js` | 117 | Dependency-free mocked GAS regression tests | CI/local |
| `tests/webdriver_smoke.py` | 63 | Dependency-free Safari WebDriver runner | CI |
| `.github/workflows/smoke.yml` | 84 | Static/GAS/Chrome/Safari CI | GitHub Actions |
| `LICENSE` | 21 | MIT License | repo only |

### 3.1 index.html anchor map (line numbers as of 2026-08-01 audit fix; re-grep before editing)

```
7-115    <style>   CSS custom props + mobile/accessibility/status styles
127-178  #s1  consent, age segment, endpoint settings/status
180-193  #s2  name + conditional guardian fields; NO email inputs (§4.2)
195-211  #s3  camera + immutable live capture stamp
213-224  #s4  signature canvas and minimum-stroke guidance
226-247  #s5  result + recoverable build-error UI
250-976  <script>
  259-276   config/constants/state (CONSENT_VERSION, BACKEND_VERSION, hashes)
  285-318   show/refreshNext/navigation
  320-353   consent gate + age switch privacy clearing
  355-435   endpoint save/copy/version verification/fail-loud status
  437-486   capture invalidation, geolocation generation token, crypto ID, immutable snapshot
  488-564   camera lifecycle, bounded preview-matched photo, immediate stream stop, coordinate-only watermark
  566-634   signature minimum stroke + race-safe resize preservation
  636-791   consent/evidence/certificate hashing + dynamic wrapped certificate layout
  794-817   result buttons
  820-941   mail status/payload/send handling
  944-974   file share/download/reset
```

---

## 4. INVARIANTS — violating any of these is a regression, not a design choice

### 4.1 SECURITY: no arbitrary-recipient mail (highest priority)

The system was **deliberately rebuilt** to remove an open-relay hole. Rules:

- **R1.** The frontend MUST NOT send any recipient address to the backend. The POST payload
  (`mailPayload()`) contains only evidence/config fields: `token, imageBase64, id, performerName,
  guardianName, guardianRelation, ageCode, ageKind, when, place, coords, consentVersion,
  consentHash, evidenceHash, certificateHash, userAgent`. Adding `to`/`cc`/`bcc`/`recipients`/
  `participantEmail`/`guardianEmail` is forbidden.
- **R2.** `Code.gs` MUST NOT read any recipient field from the request. Recipient is `ownerEmail()`
  only (`Code.gs:54-59`), used at the single `MailApp.sendEmail` call (`Code.gs:202`).
- **R3.** GAS deployment access MUST be "全員 / Anyone" (a static site cannot authenticate to GAS).
  Therefore `SHARED_TOKEN` is public by construction. It is an anti-bot speed bump, NOT auth.
  **Do not design anything that assumes the token is secret.**
- **R4.** Residual risk accepted by owner: someone who reads the public HTML can POST and spam
  **the operator's own inbox** up to `DAILY_CAP`. They cannot reach any third party. Do not "fix"
  this by re-introducing client-supplied recipients.
- **R5.** Network-originating values MUST only be inserted with `textContent`/text nodes. `index.html`
  intentionally contains no `innerHTML`. `tests/invariants.test.js` enforces this. A prior XSS existed
  in endpoint status, and a later audit found the same class of bug in geocoder address rendering.

### 4.2 PRIVACY: minimum collection

- Email addresses of 出演者 (performer) / 保護者 (guardian) are **NOT collected**. There are no
  email inputs in `#s2`. Certificates are never auto-sent to the subject. If the subject wants a
  copy, the operator shares the saved PNG manually. Consent text (`index.html:139`) states this.
- Consent text also discloses: photo (容貌), signature, timestamp, and GPS coordinates. Coordinates
  are no longer sent to a reverse-geocoding third party. **If you add any new data collection or
  any new third-party network call, you must update that clause.**

### 4.3 EVIDENTIARY INTEGRITY

- Consent checkbox unlocks only after the doc is read to the end **or** the doc fits without
  scrolling (`checkDocEnd`, `index.html:331-334`). Do not unlock unconditionally.
- Photo watermark is burned at capture time (`burnWatermark`) and is immutable thereafter.
- `startCamera()` calls `invalidateCapturedEvidence()` and clears photo, signature, certificate and
  all hashes. `freezeCaptureContext()` atomically fixes crypto-random ID, shutter time, and a cloned
  GPS snapshot, then invalidates all late geolocation callbacks. The watermark, certificate and mail
  MUST use this same frozen state. **Do not weaken either invalidation.**
- A tap without movement is not a signature. `sigInkLength >= 24` is required before step 4 unlocks.
- Certificate records `CONSENT_VERSION`, exact consent-text SHA-256, and evidence SHA-256. GAS
  recomputes the final attachment PNG SHA-256 and records it in the operator email. These hashes
  detect later file/text changes; they do not prove identity or automatically establish legal validity.
- Never write a transient string (e.g. "位置情報 取得中…") into a permanent artifact. That is what
  `fmtPlace()` (`index.html:481`) exists for. `fmtGeo()` is for live UI only.

### 4.4 FAIL-SAFE OVER CONVENIENCE

- Unconfigured backend must return `not_configured` and send nothing. Never fall back to a
  hardcoded address. (`Code.gs:36` is `""` and must stay `""` in the repo — see §9 D3.)
- Idempotency key is reserved **before** send (`Code.gs:198`) and rolled back on failure
  (`Code.gs:207`), committed after success (`Code.gs:212-213`), so a crash between send and
  record cannot cause a duplicate.

---

## 5. FRONTEND SPEC

### 5.1 state schema (`index.html:265`)

```js
state = {
  step: 1|2|3|4|5,
  age: null|'adult'|'minor',
  scrolledEnd: boolean,          // consent doc read-through gate
  name, guardian, relation: string,
  photo: null|dataURL,           // JPEG q0.92, watermark already burned in
  signature: null|dataURL,       // PNG from canvas#sig
  when: null|Date,               // fixed at shutter time
  geo: null | {lat,lng,acc} | {error:true}, // frozen at shutter; no address/geocoder
  id: null|string,               // "CONSENT-YYYYMMDD-<16 hex chars>"
  consentHash, evidenceHash, certHash: null|string,
  cert: null|dataURL,            // final certificate PNG
  mailed: boolean
}
```

### 5.2 step machine (`show()` @285)

| step | screen | enter side-effects | next-button gate (`refreshNext` @301) |
|---|---|---|---|
| 1 | 確認 | `checkDocEnd()` @+50ms | `scrolledEnd && #agree.checked && age` |
| 2 | 氏名 | — | `name && (age!=='minor' \|\| guardian)` |
| 3 | 撮影 | `startCamera()` (invalidates old photo/signature/cert; starts fresh geolocation) | `state.photo` |
| 4 | 署名 | `initSig()` @+50ms | `state.signature`; label→「証票を作成」 |
| 5 | 完了 | `buildCertificateSafely()` → hashes/render/mail; visible retry/back UI on failure | bar hidden |

`backBtn` visible for steps 2–4 only. Leaving step 3 calls `stopCamera()`.

### 5.3 known async hazards (already mitigated — keep the mitigations)

- **camera generation token** `camGen` (`index.html:489,496-514`): a stale `getUserMedia` resolution must stop
  its own tracks instead of overwriting `stream` (leak → camera LED stays on / device busy).
- **geolocation race** `geoGen` + `freezeCaptureContext()`: late sensor callbacks must not modify a
  captured photo's evidence state.
- **signature resize** (`index.html:615-634`): rotating the device re-inits the canvas at new DPR; the existing
  strokes are re-drawn from a dataURL snapshot.

---

## 6. CERTIFICATE RENDERING (`buildCertificate` @691)

Canvas: `W=1080`, `pad=48`. **Height is computed from wrapped row heights** — this is load-bearing.
A previous fixed-height formula clipped the 朱印 (seal) on virtually every real certificate.

```js
rawRows = [区分, 出演者氏名, (保護者氏名 if minor), 撮影日時, 撮影場所,
           (座標 if geo ok), 証票ID, 同意文面版, 文面SHA-256, 証跡SHA-256]
rowsHeight = sum(max(40, wrappedValueLineCount*30+8))
H = pad + 138 + rowsHeight + 14 + photoH + 40 + 30 + sigH + 30 + 180 + pad
//        ^header       ^wrapped rows               ^photo→label  ^sig box  ^seal+footer
// photoH = (W-2*pad) * photoImg.height/photoImg.width ; sigH = 220
```

**If you add/remove a row or change any vertical spacing, you MUST update this formula and
re-verify both `adult` and `minor` cases.** Values wrap by measured canvas width instead of being
horizontally compressed. `tests/smoke.html` asserts the seal exists and does not touch the bottom.

`drawSeal(ctx, cx, cy, r=150, …)` draws at `y+10 … y+160`, rotated −0.12rad, color `#d4263b`.

---

## 7. BACKEND SPEC (`apps-script/Code.gs`, VERSION 2.2.0)

### 7.1 config head (`Code.gs:35-43`)

```js
var VERSION = "2.2.0";
var OWNER_EMAIL = "";        // REQUIRED per-deployment; repo copy MUST stay "" (§9 D3)
var SHARED_TOKEN = "yt-consent-883d0d5e9919fec7c85d0217";  // must equal index.html MAIL_TOKEN@260
var DAILY_CAP = 90;
var TIMEZONE = "Asia/Tokyo"; // day boundary for the cap; do NOT use Session.getScriptTimeZone()
var MAX_BODY_CHARS = 14 * 1024 * 1024;
var MAX_IMAGE_BYTES = 10 * 1024 * 1024;
```

`ownerEmail()` resolution order: `OWNER_EMAIL` → ScriptProperties `owner_email` (set by running the
`setup()` function in the editor) → `Session.getEffectiveUser().getEmail()` (**returns "" for
anonymous web-app invocations — see §9 D3**) → `""` ⇒ `not_configured`.

### 7.2 doPost pipeline (order matters)

```
postData present                     → fail no_body
body length <= MAX_BODY_CHARS        → fail image_too_large
JSON.parse                           → fail bad_request
token === SHARED_TOKEN               → fail unauthorized
ID format/field lengths/hash format  → fail invalid_id / invalid_field
ownerEmail() non-empty               → fail not_configured
dataURL length/signature/decode/hash  → fail no_image / image_too_large / hash_mismatch
LockService.waitLock(15s)            → fail busy
ScriptProperties["sent_"+id] exists  → ok/already_sent   (idempotency)
daily count + 1 <= DAILY_CAP         → fail daily_limit      (count_YYYYMMDD, Asia/Tokyo)
MailApp.getRemainingDailyQuota() >=1 → fail quota_exceeded
reserve sent_<id> {pending:true}
MailApp.sendEmail(owner, …, {attachments:[blob], name:"YouTube出演許諾"})   ← ONLY send site
  on throw → deleteProperty(sent_<id>) → rethrow → fail server_error
commit count_YYYYMMDD, sent_<id>
→ ok/sent with server-computed certificateHash
finally: lock.releaseLock()
```

`pruneOldKeys()` (`Code.gs:235`) deletes `count_*` / `sent_CONSENT-*` older than 30d, triggered on the first
send of each day (prevents ScriptProperties exhaustion, historically fatal at ~8k sends).

### 7.3 API contract

**Request** — `POST <exec>` , `Content-Type: text/plain;charset=utf-8`, body = JSON:
```json
{"token":"…","imageBase64":"data:image/png;base64,…","id":"CONSENT-…",
 "performerName":"…","guardianName":"","guardianRelation":"","ageCode":"adult|minor",
 "ageKind":"…","when":"YYYY/MM/DD HH:MM:SS","place":"…","coords":"…",
 "consentVersion":"…","consentHash":"<sha256>","evidenceHash":"<sha256>",
 "certificateHash":"<sha256>","userAgent":"…"}
```

**Response**
```json
{"ok":true,"status":"sent","message":"operator copy sent","owner":"da***0@gmail.com","certificateHash":"…"}
{"ok":true,"status":"already_sent","message":"operator copy already sent","owner":"…","certificateHash":"…"}
{"ok":false,"code":"<CODE>","message":"<JA text>"}
GET → {"ok":true,"status":"ready","service":"consent-mailer (owner-only)","version":"2.2.0","owner":"…"}
```
`CODE ∈ {busy,no_body,bad_request,unauthorized,not_configured,no_image,image_too_large,
invalid_id,invalid_field,hash_mismatch,id_conflict,daily_limit,quota_exceeded,server_error}`
Frontend maps these to fixed JA text via `MAIL_ERR`; it never displays server exception/message text.
**Any new code added to Code.gs must also be added to `MAIL_ERR`.**

**Frontend response handling (`sendMail` @888)** — three branches, all must re-enable the button:
1. `data.ok` → success (`already_sent` shown as dedup note)
2. `data.code || data.error` → error text
3. **response body unreadable** → treated as *probably sent* (optimistic), because GAS 302-redirects
   to `script.googleusercontent.com` and the body is not always readable cross-origin. Safe because
   the backend is idempotent. 30s `AbortController` timeout. **Do not make this branch a hard failure.**

---

## 8. RUNBOOKS

### 8.1 Deploy frontend
```bash
git add -A && git commit -m "…" && git push origin main
# GitHub Pages rebuilds in ~30–60s. Verify:
curl -s https://daisukenaka.github.io/youtube-consent/ | grep -c '<unique new string>'
```
Auth: a GitHub token for `x-access-token` is stored in the macOS keychain (osxkeychain helper),
so `git push` works without prompting. Do not write tokens into `.git/config` or any file.

### 8.2 Deploy backend (MANUAL — the human must do this; you cannot)
Editing `apps-script/Code.gs` in the repo changes **nothing** in production. Each user must:
1. paste the new `Code.gs` into their Apps Script project, set `OWNER_EMAIL`, ⌘S
2. デプロイ → **デプロイを管理** → ✏️ → バージョン: **新バージョン** → デプロイ
   (choosing "新しいデプロイ" instead would mint a NEW URL and break their saved setting)
3. verify: open `<exec>` in a browser → expect `{"ok":true,…,"version":"…"}`

**Therefore: any change to the request/response contract is a breaking change for every peer who
has already deployed.** Prefer additive, backward-compatible changes. Bump `VERSION` on every
Code.gs change so deployed versions are identifiable via GET.

### 8.3 Verify frontend locally (browser required — canvas/camera/geo cannot be fully unit-tested)
```bash
# a static server config already exists at ~/.claude/launch.json (name: consent-static, port 8791)
python3 -m http.server 8791 --bind 127.0.0.1 --directory /Users/nakatsukadaisuke/youtube-consent
```
Certificate regression check (run in the page console; stubs photo/signature, asserts seal not clipped):
```js
function stub(w,h,c,l){const x=document.createElement('canvas');x.width=w;x.height=h;const g=x.getContext('2d');
  g.fillStyle=c;g.fillRect(0,0,w,h);g.fillStyle='#000';g.font='40px sans-serif';g.fillText(l,20,60);return x.toDataURL()}
for (const age of ['adult','minor']) {
  Object.assign(state,{photo:stub(1080,1440,'#9ab','P'),signature:stub(600,230,'#fff','S'),
    name:'山田 太郎',age,guardian:'山田 花子',relation:'母',when:new Date(),
    geo:{lat:35.6812,lng:139.7671,acc:12},id:'CONSENT-TEST'});
  await buildCertificate();
  const img=document.querySelector('#resultImg'); await new Promise(r=>img.complete&&img.naturalWidth?r():img.onload=r);
  const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
  const x=c.getContext('2d');x.drawImage(img,0,0);
  const red=(y0,y1)=>{const d=x.getImageData(0,y0,c.width,y1-y0).data;let r=0,t=0;
    for(let i=0;i<d.length;i+=4){t++;if(d[i]>180&&d[i+1]<80&&d[i+2]<90)r++}return r/t};
  console.log(age,{H:c.height, mustBeZero:red(c.height-30,c.height), mustBeNonZero:red(c.height-260,c.height-60)});
}
// PASS = mustBeZero===0 (nothing touching the bottom edge) && mustBeNonZero>0 (seal present)
```
Camera and geolocation require HTTPS or `localhost`. Real-device testing needs a tunnel or Pages.

### 8.4 Automated frontend smoke
```bash
node tests/invariants.test.js
node tests/backend.test.js
python3 -m http.server 8791 --bind 127.0.0.1 --directory /Users/nakatsukadaisuke/youtube-consent
# open http://127.0.0.1:8791/tests/smoke.html
```
`tests/smoke.html` runs only on `localhost` / `127.0.0.1` and checks consent gates, adult privacy
clearing, blank-signature rejection, capture invalidation/snapshot, crypto ID format, no-recipient
payload, recoverable certificate failure, hashes, and adult/minor seal/layout. GitHub Actions runs it
in Chrome and native Safari; static §4 and mocked GAS tests run first. No app runtime dependency or
build step was added.

### 8.5 Verify backend live
```bash
curl -s -L "<exec>"                                            # → ok:true, version, masked owner
curl -s -L -X POST -H 'Content-Type: text/plain' \
     --data '{"token":"WRONG"}' "<exec>"                       # → ok:false code:unauthorized
# NOTE: curl -L on POST follows the 302 as GET; to read the real body, capture the redirect URL
#       (-w '%{redirect_url}') and GET it. A plain `curl -L -X POST` may show an HTML error page.
```

---

## 9. HISTORY OF DECISIONS & FAILED APPROACHES (do not re-litigate / do not repeat)

- **D1 — auto-send to performer/guardian: REMOVED.** v1 collected their emails and sent them the
  certificate. That made the endpoint an open mail relay (public token + `Anyone` access + client-
  supplied recipients ⇒ anyone could send mail as the operator to arbitrary addresses). Replaced by
  operator-copy-only. Do not restore.
- **D2 — recipient allowlist / name-picker: considered, rejected** by the owner in favor of
  per-user GAS deployments (each peer gets their own backend, own Gmail, own quota).
- **D3 — `Session.getEffectiveUser()` auto-detection: TRIED, FAILED.** v2.1 set `OWNER_EMAIL=""` and
  intended the recipient to default to the deploying user. In a web app deployed as
  "execute as me / access anyone", the POST/GET is anonymous and `getEffectiveUser()` returns `""`,
  so every request died with `not_configured`. v2.1.1 restored explicit `OWNER_EMAIL` and added the
  editor-run `setup()` helper. **The repo copy stays `""` on purpose** — an unset backend must fail
  loudly rather than silently mail a stranger's certificates to the author (that exact bug existed
  when the author's address was the default).
- **D4 — consent gate by scroll only: FIXED.** On tall viewports the doc fits without scrolling, so
  the scroll event never fired and the checkbox could never be enabled. Now: end-reached **or**
  no-overflow, evaluated on scroll/resize/load/+300ms.
- **D5 — fixed-height certificate canvas: FIXED.** See §6.
- **D6 — `maximum-scale=1,user-scalable=no`: REMOVED.** Consent text must be zoomable.
- **D7 — full-project adversarial review** (2026-07, 60 parallel agents, 53 findings, 49 confirmed)
  produced the current hardened state. Its fixes are in commit `22d71bf`.
- **D8 — dependency-free cross-browser smoke CI: ADDED/EXPANDED.** `tests/smoke.html` covers consent,
  privacy, evidence-state and certificate rendering. GitHub Actions uses installed Chrome and native
  SafariDriver plus Node/Python standard libraries; no npm package, build system, or app runtime
  dependency was added.
- **D9 — public Nominatim reverse geocoding: REMOVED.** The 2026-08 audit found network-derived XSS,
  capture-time address races, and public-service policy/availability risk. Evidence now freezes GPS
  coordinates only. Do not restore client-side public reverse geocoding.
- **D10 — audit hardening (2026-08-01):** crypto IDs, signature invalidation/minimum stroke, adult
  guardian privacy clearing, consent/evidence/certificate hashes, bounded GAS validation before lock,
  recoverable build errors, Safari CI, awaited/timeout service-worker caching, MIT license.

---

## 10. OPEN BACKLOG (unfixed; ordered by value)

| # | Issue | Where | Notes |
|---|---|---|---|
| B4 | Author email remains in git history | commits before `22d71bf` | HEAD is clean. History rewrite intentionally not done (public repo, forks/clones). |
| B6 | Consent text is a non-lawyer template | `index.html:132-141` (clause 6 = privacy/disclosure @139) | Owner has been told repeatedly to get legal review. Do not represent it as vetted. |
| B9 | Peers running older Code.gs | each peer's GAS | Repo is 2.2.0; every peer must manually redeploy. Frontend connection test warns when version is older than 2.2.0. |

Resolved in D10: B1 (coordinates frozen at shutter), B2 (cannot guarantee browser retention;
fail-loud status + URL-copy backup + every-load version check + guide warning), B5 (4-module QR quiet
zone), B7 (`.gitignore`), B8 (MIT `LICENSE`).

---

## 11. HARD CONSTRAINTS FOR ANY FUTURE CHANGE

1. No build step, no npm, no framework, no external runtime dependency in `index.html`.
   It must stay a single file that works when opened over plain HTTPS static hosting.
2. No CDN/script tags for third-party JS in the app (guide.html likewise). Offline venues matter.
3. Do not add a preflight-triggering request to GAS (no custom headers, no JSON content-type).
4. All user-visible strings: Japanese, non-technical, actionable. No error codes shown raw.
5. Mobile-first: iPhone Safari, one-handed, outdoors, bad signal, possibly offline.
6. Any new third-party network call must be added to the consent text (§4.2). `sw.js` only handles
   same-origin GETs; never cache GAS or other cross-origin evidence traffic.
7. Bump `VERSION` in `Code.gs` and note the migration in `apps-script/README.md` whenever the
   backend changes; remember the human must manually redeploy (§8.2).
8. When you change UI copy, check `guide.html` still matches (it names concrete buttons/steps).

---

## 12. GLOSSARY (JA → meaning in code)

```
証票 (shōhyō)      the generated certificate PNG            → state.cert
出演者              performer / the person consenting        → state.name
保護者              guardian (required when age==='minor')   → state.guardian
同意 / 許諾         consent                                  → #agree, scrolledEnd
朱印                red seal stamp drawn on the certificate  → drawSeal()
控え                the operator's own copy of the record    → owner-only mail
透かし              visible watermark burned into the photo  → burnWatermark()
同期                the owner's comedian peers (the other users of this app)
デプロイを管理      "Manage deployments" (the correct GAS redeploy path, §8.2)
```

---

## 13. FIRST ACTIONS FOR THE INCOMING AGENT

1. `git -C /Users/nakatsukadaisuke/youtube-consent log --oneline -5` and confirm HEAD is `879e147`
   or later; `git status` should be clean except `.DS_Store`.
2. Read `index.html` fully (use the current count in §3) before editing; the line anchors in §3.1
   drift on every edit.
3. Re-run §8.3 certificate check to establish a green baseline **before** making changes.
4. Do not touch §4 invariants without explicit instruction from the owner.
5. Remember: frontend changes go live on push; backend changes require the human to redeploy.
