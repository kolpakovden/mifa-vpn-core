#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAD_CONFIG=0
[[ -f /usr/local/etc/xray/config.json ]] && HAD_CONFIG=1
DOMAIN=""; EMAIL=""; FORCE_CONFIG=0
XRAY_VERSION=${XRAY_VERSION:-25.8.3}
REALITY_TARGET=${REALITY_TARGET:-www.github.com:443}
SNI_POOL=${SNI_POOL:-www.techadvisor.com,www.lemonde.fr,www.spiegel.de,www.corriere.it,www.github.com,www.medium.com,www.quora.com,www.researchgate.net,www.academia.edu,www.arxiv.org}
usage(){ echo "Usage: $0 --domain vpn.example.com [--email admin@example.com] [--force-config]"; }
while [[ $# -gt 0 ]]; do case "$1" in --domain) DOMAIN=${2:?}; shift 2;; --email) EMAIL=${2:?}; shift 2;; --force-config) FORCE_CONFIG=1; shift;; -h|--help) usage; exit 0;; *) echo "Unknown option: $1" >&2; usage; exit 1;; esac; done
[[ -n "$DOMAIN" ]] || { usage; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl openssl nginx certbot python3-certbot-nginx python3 python3-venv python3-pip
if ! command -v xray >/dev/null 2>&1 || [[ "$(xray version 2>/dev/null | head -1)" != *"$XRAY_VERSION"* ]]; then
  bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install --version "$XRAY_VERSION"
fi
mkdir -p /etc/mifa /opt/mifa/bot /usr/local/etc/xray /var/log/xray /var/lib/mifa "/var/www/$DOMAIN"
chown nobody:nogroup /var/log/xray; chmod 755 /var/log/xray
[[ -e /var/log/xray/access.log ]] || install -m 0644 -o nobody -g nogroup /dev/null /var/log/xray/access.log
PRIVATE=""; PUBLIC=""; SHORT=""
# Reuse existing transport paths during in-place migration; generate them only on a clean host.
if [[ -z "${XHTTP_PATH:-}" && $HAD_CONFIG -eq 1 ]]; then
  XHTTP_PATH=$(python3 - <<'__READ_XH__'
import json
try:
 c=json.load(open('/usr/local/etc/xray/config.json'))
 for i in c.get('inbounds',[]):
  x=i.get('streamSettings',{}).get('xhttpSettings',{}).get('path','')
  if x: print(x.strip('/')); break
except Exception: pass
__READ_XH__
)
fi
if [[ -z "${WS_PATH:-}" && $HAD_CONFIG -eq 1 ]]; then
  WS_PATH=$(python3 - <<'__READ_WS__'
import json
try:
 c=json.load(open('/usr/local/etc/xray/config.json'))
 for i in c.get('inbounds',[]):
  x=i.get('streamSettings',{}).get('wsSettings',{}).get('path','')
  if x: print(x.strip('/')); break
except Exception: pass
__READ_WS__
)
fi
XHTTP_PATH=${XHTTP_PATH:-mifa-xh-$(openssl rand -hex 6)}
WS_PATH=${WS_PATH:-mifa-ws-$(openssl rand -hex 6)}
XHTTP_PATH=${XHTTP_PATH#/}; XHTTP_PATH=${XHTTP_PATH%/}
WS_PATH=${WS_PATH#/}; WS_PATH=${WS_PATH%/}
if [[ $HAD_CONFIG -eq 0 || $FORCE_CONFIG -eq 1 ]]; then
  KEYS=$(xray x25519)
  PRIVATE=$(printf '%s\n' "$KEYS" | sed -nE 's/^(PrivateKey|Private key|Private):[[:space:]]*//p' | head -1)
  [[ -n "$PRIVATE" ]] || { echo "Unable to parse Xray private key" >&2; exit 1; }
  DERIVED=$(xray x25519 -i "$PRIVATE" 2>/dev/null || true)
  PUBLIC=$(printf '%s\n' "$DERIVED" | sed -nE 's/^(PublicKey|Public key|Public):[[:space:]]*//p' | head -1)
  SHORT=$(openssl rand -hex 8)
  SNI_JSON=$(python3 - "$SNI_POOL" <<'__SNI_PY__'
import json,sys
print(json.dumps([x.strip() for x in sys.argv[1].split(',') if x.strip()]))
__SNI_PY__
)
  python3 - "$BASE_DIR/xray/config.template.json" /usr/local/etc/xray/config.json "$PRIVATE" "$SHORT" "$XHTTP_PATH" "$WS_PATH" "$REALITY_TARGET" "$SNI_JSON" <<'__RENDER_PY__'
import sys
from pathlib import Path
src,dst,priv,sid,xh,ws,target,snis=sys.argv[1:]
s=Path(src).read_text().replace('__REALITY_PRIVATE_KEY__',priv).replace('__REALITY_SHORT_ID__',sid)
s=s.replace('__XHTTP_PATH__',xh).replace('__WS_PATH__',ws).replace('__REALITY_TARGET__',target).replace('__SNI_POOL_JSON__',snis)
Path(dst).write_text(s)
__RENDER_PY__
  chmod 644 /usr/local/etc/xray/config.json; chown root:root /usr/local/etc/xray/config.json
else
  echo "Keeping existing /usr/local/etc/xray/config.json"
  PRIVATE=$(python3 - <<'__READ_PRIV__'
import json
try:
 c=json.load(open('/usr/local/etc/xray/config.json'))
 for i in c.get('inbounds',[]):
  r=i.get('streamSettings',{}).get('realitySettings',{})
  if r.get('privateKey'): print(r['privateKey']); break
except Exception: pass
__READ_PRIV__
)
  if [[ -n "$PRIVATE" ]]; then DERIVED=$(xray x25519 -i "$PRIVATE" 2>/dev/null || true); PUBLIC=$(printf '%s\n' "$DERIVED" | sed -nE 's/^(PublicKey|Public key|Public):[[:space:]]*//p' | head -1); fi
  SHORT=$(python3 - <<'__READ_SHORT__'
import json
try:
 c=json.load(open('/usr/local/etc/xray/config.json'))
 for i in c.get('inbounds',[]):
  ids=i.get('streamSettings',{}).get('realitySettings',{}).get('shortIds',[])
  if ids: print(ids[0]); break
except Exception: pass
__READ_SHORT__
)
fi
SERVER_IP=$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)
cat > /etc/mifa/state.env <<EOF
CONFIG_PATH=/usr/local/etc/xray/config.json
XRAY_CONFIG=/usr/local/etc/xray/config.json
SERVER_IP=${SERVER_IP}
SERVER_HOST=${DOMAIN}
PORTS=8443,50273
XHTTP_PATH=/${XHTTP_PATH}/
WS_PATH=/${WS_PATH}/
DEFAULT_SNI=www.github.com
SNI_POOL=${SNI_POOL}
PUBLIC_KEY=${PUBLIC}
SHORT_ID=${SHORT}
XRAY_SERVICE=xray
XRAY_CFG_OWNER=root
XRAY_CFG_GROUP=root
XRAY_CFG_MODE=644
EOF
chmod 600 /etc/mifa/state.env
cat > /etc/mifa/xhttp.env <<EOF
DOMAIN=${DOMAIN}
XHTTP_PATH=/${XHTTP_PATH}/
XHTTP_SOCKET=/dev/shm/mifa-xhttp.socket
XHTTP_TAG=VlessXHTTP443
EOF
cat > /etc/mifa/ws.env <<EOF
DOMAIN=${DOMAIN}
WS_PATH=/${WS_PATH}/
WS_SOCKET=/dev/shm/mifa-ws.socket
WS_TAG=VlessWS443
EOF
chmod 600 /etc/mifa/xhttp.env /etc/mifa/ws.env
printf '%s\n' "$(cat "$BASE_DIR/VERSION")" > /etc/mifa/core-version
chmod 600 /etc/mifa/core-version
[[ -f /etc/mifa/bot.env ]] || { cp "$BASE_DIR/config/bot.env.example" /etc/mifa/bot.env; chmod 600 /etc/mifa/bot.env; }
[[ -f /etc/mifa/notify.env ]] || { cp "$BASE_DIR/config/notify.env.example" /etc/mifa/notify.env; chmod 600 /etc/mifa/notify.env; }
cp "$BASE_DIR/bot/bot.py" /opt/mifa/bot/bot.py; cp "$BASE_DIR/bot/requirements.txt" /opt/mifa/bot/requirements.txt
python3 -m venv /opt/mifa/bot/venv
/opt/mifa/bot/venv/bin/pip install --upgrade pip
/opt/mifa/bot/venv/bin/pip install -r /opt/mifa/bot/requirements.txt
cp "$BASE_DIR/bot/systemd/mifa-xray-bot.service" /etc/systemd/system/
cp "$BASE_DIR/systemd/mifa-xray-restart.service" /etc/systemd/system/
cp "$BASE_DIR/systemd/mifa-connect-notify.service" /etc/systemd/system/
cp "$BASE_DIR/systemd/mifa-connect-notify.timer" /etc/systemd/system/
install -m 0755 "$BASE_DIR/scripts/check_users.py" /usr/local/bin/mifa-check-users
install -m 0755 "$BASE_DIR/scripts/healthcheck.sh" /usr/local/bin/mifa-healthcheck
install -m 0755 "$BASE_DIR/scripts/backup.sh" /usr/local/bin/mifa-backup
install -m 0755 "$BASE_DIR/scripts/restore.sh" /usr/local/bin/mifa-restore
cat > /etc/logrotate.d/xray <<'EOF'
/var/log/xray/*.log {
    daily
    rotate 7
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
    create 0644 nobody nogroup
}
EOF
[[ -f "/var/www/$DOMAIN/index.html" ]] || cp "$BASE_DIR/web/index.html" "/var/www/$DOMAIN/index.html"
chown -R www-data:www-data "/var/www/$DOMAIN"
BOOT=/etc/nginx/sites-available/$DOMAIN
CERT_FILE=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
KEY_FILE=/etc/letsencrypt/live/$DOMAIN/privkey.pem

# Keep HTTPS continuously available during in-place migration if a certificate already exists.
if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
  sed -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__XHTTP_PATH__/$XHTTP_PATH/g" -e "s/__WS_PATH__/$WS_PATH/g" "$BASE_DIR/nginx/site.template.conf" > "$BOOT"
else
  sed "s/__DOMAIN__/$DOMAIN/g" "$BASE_DIR/nginx/bootstrap-http.template.conf" > "$BOOT"
fi
ln -sfn "$BOOT" "/etc/nginx/sites-enabled/$DOMAIN"; rm -f /etc/nginx/sites-enabled/default
nginx -t; systemctl enable --now nginx

xray run -test -config /usr/local/etc/xray/config.json
systemctl enable xray; systemctl restart xray

if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" ]]; then
  if [[ "${MIFA_SKIP_CERTBOT:-0}" != "1" ]]; then
    args=(certonly --webroot -w "/var/www/$DOMAIN" -d "$DOMAIN" -d "www.$DOMAIN" --agree-tos --non-interactive)
    if [[ -n "$EMAIL" ]]; then args+=(--email "$EMAIL"); else args+=(--register-unsafely-without-email); fi
    certbot "${args[@]}"
    sed -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__XHTTP_PATH__/$XHTTP_PATH/g" -e "s/__WS_PATH__/$WS_PATH/g" "$BASE_DIR/nginx/site.template.conf" > "$BOOT"
    nginx -t; systemctl reload nginx
  else
    echo "Certbot skipped. HTTP bootstrap config remains active."
  fi
else
  echo "Existing TLS certificate found; keeping HTTPS active."
  nginx -t; systemctl reload nginx
fi

systemctl daemon-reload
systemctl enable mifa-xray-bot.service
if grep -Eq '^BOT_TOKEN=.+$' /etc/mifa/bot.env && grep -Eq '^(ADMIN_IDS|ALLOWED_CHAT_ID)=.+$' /etc/mifa/bot.env; then
  systemctl restart mifa-xray-bot.service
else
  systemctl stop mifa-xray-bot.service 2>/dev/null || true
  echo "Telegram bot installed but not started: set BOT_TOKEN and ADMIN_IDS and/or ALLOWED_CHAT_ID in /etc/mifa/bot.env."
fi
/usr/local/bin/mifa-healthcheck || true
cat <<EOF

MIFA VPN Core installed.
Domain: $DOMAIN
Xray: $XRAY_VERSION
Reality ports: 8443,50273
XHTTP path: /$XHTTP_PATH/
WS path: /$WS_PATH/ (legacy)

Next:
  nano /etc/mifa/bot.env
  systemctl restart mifa-xray-bot

Optional new-IP notifier:
  nano /etc/mifa/notify.env
  systemctl enable --now mifa-connect-notify.timer
EOF
