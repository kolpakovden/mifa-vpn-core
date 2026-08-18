#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
BACKUP=${1:-}
[[ -n "$BACKUP" && -f "$BACKUP" ]] || { echo "Usage: $0 /path/to/mifa-backup.tar.gz" >&2; exit 1; }
if [[ -f "$BACKUP.sha256" ]]; then (cd "$(dirname "$BACKUP")" && sha256sum -c "$(basename "$BACKUP").sha256"); fi
while IFS= read -r p; do case "$p" in /*|../*|*/../*|*/..) echo "Unsafe path in backup: $p" >&2; exit 1;; esac; done < <(tar -tzf "$BACKUP")
tar -C / -xzf "$BACKUP"
chmod 600 /etc/mifa/*.env 2>/dev/null || true
chmod 644 /usr/local/etc/xray/config.json 2>/dev/null || true
chown root:root /usr/local/etc/xray/config.json 2>/dev/null || true
/usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json
nginx -t
systemctl daemon-reload
systemctl restart xray nginx
systemctl restart mifa-xray-bot 2>/dev/null || true
echo "Restore completed."
/usr/local/bin/mifa-healthcheck || true
