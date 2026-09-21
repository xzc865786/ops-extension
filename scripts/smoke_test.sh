#!/usr/bin/env bash
# Smoke against a running Ops Extension backend (default http://127.0.0.1:8090)
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8090}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

echo "== health =="
curl -sf "$BASE/ext/api/health" | tee /dev/stderr | grep -q '"ok":true'

if [[ "${DEV_AUTH_BYPASS:-}" == "true" ]]; then
  echo "== bootstrap (dev bypass) =="
  TOKEN=$(python3 -c 'import json; print("dev:"+json.dumps({"id":1,"username":"smoke","email":"s@e.com","role":"admin","status":"active"}))')
  curl -sf -c "$COOKIE_JAR" -D - -o /dev/null \
    "$BASE/ext/auth/bootstrap?token=${TOKEN}&next=/ext/app/admin/tickets" | grep -qi "302\|location" || true
else
  echo "Set DEV_AUTH_BYPASS=true for local smoke without Sub2API, or pass a real token via TOKEN=..."
  if [[ -z "${TOKEN:-}" ]]; then
    echo "Skipping authenticated smoke (no TOKEN)."
    exit 0
  fi
  curl -sf -c "$COOKIE_JAR" -D - -o /dev/null \
    "$BASE/ext/auth/bootstrap?token=${TOKEN}&next=/ext/app/tickets"
fi

echo "== me =="
curl -sf -b "$COOKIE_JAR" "$BASE/ext/api/v1/auth/me" | tee /dev/stderr

echo "== create ticket =="
TID=$(curl -sf -b "$COOKIE_JAR" -H 'Content-Type: application/json' \
  -d '{"title":"smoke","description":"smoke test","category":"OTHER"}' \
  "$BASE/ext/api/v1/tickets" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "ticket id=$TID"

echo "== admin list =="
curl -sf -b "$COOKIE_JAR" "$BASE/ext/api/v1/admin/tickets" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("total", d["total"])'

echo "SMOKE OK"
