#!/usr/bin/env bash
set -u
fail=0
check_service(){ local svc=$1; if systemctl is-active --quiet "$svc"; then echo "[OK] $svc"; else echo "[FAIL] $svc"; fail=1; fi; }
check_service xray; check_service nginx
if [[ -f /etc/mifa/bot.env ]] && grep -Eq '^BOT_TOKEN=.+$' /etc/mifa/bot.env && grep -Eq '^(ADMIN_IDS|ALLOWED_CHAT_ID)=.+$' /etc/mifa/bot.env; then
  check_service mifa-xray-bot
else
  echo "[SKIP] mifa-xray-bot (token/ACL not configured)"
fi
if /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json >/dev/null 2>&1; then echo "[OK] xray config"; else echo "[FAIL] xray config"; fail=1; fi
if nginx -t >/dev/null 2>&1; then echo "[OK] nginx config"; else echo "[FAIL] nginx config"; fail=1; fi
for p in 80 443 8443 50273; do if ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)$p$"; then echo "[OK] tcp/$p listening"; else echo "[FAIL] tcp/$p not listening"; fail=1; fi; done
for s in /dev/shm/mifa-xhttp.socket /dev/shm/mifa-ws.socket; do [[ -S "$s" ]] && echo "[OK] $s" || { echo "[FAIL] $s"; fail=1; }; done
exit $fail
