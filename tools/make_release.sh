#!/bin/bash
# Publish a GitHub release of this port: tag -> dist zip -> release -> asset upload.
# usage: make_release.sh <tag> [notes.md]
#   <tag>      e.g. v0.2.0-port190
#   [notes.md] release notes (markdown); without it a default note is generated
# The GitHub token comes from Git Credential Manager into a shell variable and is
# piped to curl through stdin configs (-K -): never on the command line, never logged.
set -eu
cd "$(dirname "$0")/.."
TAG=${1:?usage: make_release.sh <tag> [notes.md]}
NOTES=${2:-}
REPO=Paimonshen/SavageWind190
BRANCH=port-190

# 1. the dist zip (builds the whole ordered chain when missing)
ZIP=$(ls build/dist/SavageWind-*-windows.zip 2>/dev/null | head -1 || true)
if [ -z "$ZIP" ]; then
    echo "[release] no dist zip; building the chain (this takes a while)"
    export PATH="/c/msys64/ucrt64/bin:/c/msys64/usr/bin:$PATH"
    [ -f build/deps-win/lib/libavcodec.dll.a ] || make deps-windows
    make gen-helper
    bash tools/fetch_zig.sh
    make dist RELEASE=1
    ZIP=$(ls build/dist/SavageWind-*-windows.zip | head -1)
fi
echo "[release] asset: $ZIP ($(du -h "$ZIP" | cut -f1))"

# 2. tag and push it (retry: github connectivity comes and goes here)
git tag -a "$TAG" -m "release $TAG" 2>/dev/null || echo "[release] tag exists"
for i in 1 2 3 4 5; do git push mine "$TAG" && break; echo "[release] tag push retry $i"; sleep 20; done

# 3. token + retrying API helper; CT (env) adds a Content-Type for asset uploads
CRED=$(printf "protocol=https\nhost=github.com\n\n" | GCM_INTERACTIVE=never GIT_TERMINAL_PROMPT=0 git credential fill)
PAT=$(printf '%s\n' "$CRED" | sed -n 's/^password=//p')
[ -n "$PAT" ] || { echo "[release] FAIL: no stored GitHub credential"; exit 1; }
api() {  # api <method> <url> <payload-file>
    local method=$1 url=$2 payload=$3 out code
    out=$(mktemp)
    {
        printf 'header = "Authorization: token %s"\n' "$PAT"
        echo 'header = "Accept: application/vnd.github+json"'
        [ -n "${CT:-}" ] && printf 'header = "Content-Type: %s"\n' "$CT"
    } > "$out.cfg"
    for i in 1 2 3 4 5; do
        code=$(curl -sS --ssl-no-revoke -K "$out.cfg" -o "$out" -w "%{http_code}" \
            -X "$method" "$url" --data-binary "@$payload" || echo 000)
        case "$code" in 200|201|422) break;; esac
        echo "[release] api $method -> $code, retry $i"; sleep 20
    done
    cat "$out"; rm -f "$out" "$out.cfg"
}

# 4. create the release
if [ -n "$NOTES" ]; then BODY=$(cat "$NOTES");
else BODY=$(printf 'Savage Wind 0.2.0-alpha.2 (upstream test) ported and verified for BOTW 1.9.0.\n\n- verified: full boot, Vulkan rendering, ~54 fps average, full shader precompilation (13,997 shaders)\n- no game files included: bring your own 1.9.0 dump (exefs/ + romfs/); the zip recompiles the game code locally on first setup\n- source and docs: the %s branch (README has the complete guide)' "$BRANCH");
fi
printf '{"tag_name":"%s","target_commitish":"%s","name":"%s","prerelease":true,"body":%s}' \
    "$TAG" "$BRANCH" "$TAG" "$(BODY="$BODY" python -c 'import json,os; print(json.dumps(os.environ["BODY"]))')" > /tmp/rel_payload.json
RESP=$(api POST "https://api.github.com/repos/$REPO/releases" /tmp/rel_payload.json)
RID=$(printf '%s' "$RESP" | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*$')
URL=$(printf '%s' "$RESP" | grep -o '"html_url": *"[^"]*"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')
echo "[release] release id=${RID:-none} url=${URL:-none}"
[ -n "$RID" ] || { printf '%s\n' "$RESP" | head -5; exit 1; }

# 5. upload the asset
CT="application/zip" api POST "https://uploads.github.com/repos/$REPO/releases/$RID/assets?name=$(basename "$ZIP")" "$ZIP" >/dev/null
echo "[release] done: ${URL}"
rm -f /tmp/rel_payload.json
