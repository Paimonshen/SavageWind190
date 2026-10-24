#!/bin/bash
# Patient GitHub uploader: waits for connectivity, creates the private repo, pushes port-190.
# The PAT is fetched from Git Credential Manager into a shell variable; never printed or logged.
set -u
cd "$(dirname "$0")/.."
TMP="${TMPDIR:-/tmp}/sw_repo"
mkdir -p "$TMP"
echo '{"name":"SavageWind190","private":true,"description":"BOTW 1.9.0 static-recomp port on SavageWindRecomp (MIT upstream): extraction front-door, port docs, verified boot on Vulkan"}' > "$TMP/payload.json"

for i in $(seq 1 60); do
  code=$(curl -sS --ssl-no-revoke --connect-timeout 8 -o /dev/null -w "%{http_code}" https://api.github.com/zen 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo "[upload] github reachable (try $i), creating repo"
    CRED=$(printf "protocol=https\nhost=github.com\n\n" | GCM_INTERACTIVE=never GIT_TERMINAL_PROMPT=0 git credential fill 2>/dev/null)
    PAT=$(printf '%s\n' "$CRED" | sed -n 's/^password=//p')
    if [ -z "$PAT" ]; then echo "[upload] FAIL: no stored credential"; exit 1; fi
    { printf 'header = "Authorization: token %s"\n' "$PAT"; echo 'header = "Accept: application/vnd.github+json"'; } \
      | curl -sS --ssl-no-revoke -K - -o "$TMP/resp.json" -w "create: HTTP %{http_code}\n" -X POST -d @"$TMP/payload.json" https://api.github.com/user/repos
    grep -o '"full_name": *"[^"]*"' "$TMP/resp.json" | head -1
    # 201 created / 422 already exists are both fine
    git remote remove mine 2>/dev/null
    git remote add mine https://github.com/Paimonshen/SavageWind190.git
    for j in 1 2 3; do
      if git push -u mine port-190 2>&1 | tail -3; then
        echo "[upload] push OK"
        git ls-remote --heads mine | head -3
        rm -f "$TMP/payload.json" "$TMP/resp.json"
        exit 0
      fi
      echo "[upload] push retry $j"; sleep 20
    done
    echo "[upload] FAIL: repo may exist but push failed"; exit 1
  fi
  echo "[upload] try $i: github unreachable ($code), waiting 60s"
  sleep 60
done
echo "[upload] FAIL: github unreachable for an hour"
exit 1
