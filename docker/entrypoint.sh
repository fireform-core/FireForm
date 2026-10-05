#!/bin/sh
set -e

mkdir -p /data/uploads

# Reinstall deps only when the live requirements.txt differs from what the image
# was built with. The image bakes the hash at /opt/req_hash; in dev the live file
# comes from the bind mount. Matching hash => deps already baked in => skip (instant).
BAKED_HASH=$(cat /opt/req_hash 2>/dev/null || echo "none")
LIVE_HASH=$(sha256sum requirements.txt 2>/dev/null | cut -d' ' -f1 || echo "unknown")

if [ "$BAKED_HASH" = "$LIVE_HASH" ]; then
    echo "[entrypoint] dependencies up to date — skipping install"
else
    echo "[entrypoint] requirements.txt changed since image build — syncing deps..."
    if command -v uv > /dev/null 2>&1; then
        UV_TORCH_BACKEND=cpu uv pip install --system -r requirements.txt
    else
        pip install -r requirements.txt
    fi
fi

python3 -m app.db.init_db

exec "$@"
