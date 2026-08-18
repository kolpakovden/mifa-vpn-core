# Migration from MIFA VPN Platform

The old platform is feature-complete and no longer developed.

## Removed

- Docker monitoring compose stack
- Grafana
- Prometheus
- Loki
- Promtail
- xray-exporter
- `internal/monitoring.sh`
- unused Xray metrics/stats API

## Retained

- Xray
- nginx + domain TLS
- Certbot
- Telegram bot
- access logs
- Reality 8443/50273
- XHTTP 443
- WebSocket 443 for compatibility

Do not regenerate existing users during migration. Back up production state and restore it after installing Core on a replacement host.
