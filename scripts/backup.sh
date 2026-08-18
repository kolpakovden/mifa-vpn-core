#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
OUT_DIR=${MIFA_BACKUP_DIR:-/root/mifa-backups}
STAMP=$(date +%Y%m%d-%H%M%S)
OUT=${1:-${OUT_DIR}/mifa-backup-${STAMP}.tar.gz}
mkdir -p "$(dirname "$OUT")"
DOMAIN=""
if [[ -f /etc/mifa/xhttp.env ]]; then source /etc/mifa/xhttp.env || true; fi
DOMAIN=${DOMAIN:-}
paths=(usr/local/etc/xray/config.json etc/mifa/state.env etc/mifa/bot.env etc/mifa/xhttp.env etc/mifa/ws.env etc/mifa/notify.env etc/mifa/core-version etc/logrotate.d/xray)
if [[ -n "$DOMAIN" ]]; then
  [[ -e "/etc/nginx/sites-available/$DOMAIN" ]] && paths+=("etc/nginx/sites-available/$DOMAIN")
  [[ -d "/var/www/$DOMAIN" ]] && paths+=("var/www/$DOMAIN")
  [[ -d "/etc/letsencrypt" ]] && paths+=("etc/letsencrypt")
fi
existing=(); for p in "${paths[@]}"; do [[ -e "/$p" ]] && existing+=("$p"); done
[[ ${#existing[@]} -gt 0 ]] || { echo "Nothing to back up" >&2; exit 1; }
tar -C / -czf "$OUT" "${existing[@]}"
chmod 600 "$OUT"
sha256sum "$OUT" > "$OUT.sha256"; chmod 600 "$OUT.sha256"
echo "Backup: $OUT"
echo "SHA256: $(cut -d' ' -f1 "$OUT.sha256")"
echo "WARNING: backup contains production secrets. Keep it private."
