#!/usr/bin/env python3
"""Dependency-free W3C WebDriver runner used for the Safari CI smoke test."""

import json
import sys
import time
import urllib.error
import urllib.request


APP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/tests/smoke.html"
DRIVER_URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:4444"


def command(method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        DRIVER_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json;charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


for attempt in range(30):
    try:
        command("GET", "/status")
        break
    except (OSError, urllib.error.URLError):
        if attempt == 29:
            raise
        time.sleep(0.5)

created = command("POST", "/session", {
    "capabilities": {"alwaysMatch": {"browserName": "safari"}}
})
value = created.get("value", created)
session_id = value.get("sessionId") or created.get("sessionId")
if not session_id:
    raise RuntimeError("Safariセッションを開始できません: " + json.dumps(created, ensure_ascii=False))

try:
    command("POST", f"/session/{session_id}/url", {"url": APP_URL})
    report = None
    for _ in range(60):
        result = command("POST", f"/session/{session_id}/execute/sync", {
            "script": "return {status:document.documentElement.dataset.status||'',result:(document.querySelector('#result')||{}).textContent||''};",
            "args": [],
        }).get("value", {})
        if result.get("status") in ("pass", "fail"):
            report = result
            break
        time.sleep(0.25)
    if not report or report.get("status") != "pass":
        raise RuntimeError("Safariスモークテスト失敗: " + json.dumps(report, ensure_ascii=False))
    print("safari smoke:", report["result"])
finally:
    try:
        command("DELETE", f"/session/{session_id}")
    except Exception:
        pass
