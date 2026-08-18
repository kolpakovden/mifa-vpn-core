# Changelog

## 1.0.0 — 2026-08-18

- created MIFA VPN Core from the stable server-91 production architecture
- removed Grafana, Prometheus, Loki, Promtail and Docker monitoring stack
- removed unused Xray Stats/Metrics API
- retained VLESS + Reality on ports 8443 and 50273
- retained XHTTP over nginx/TLS on port 443
- retained WebSocket as legacy compatibility transport
- added safe backup/restore workflow
- moved notification credentials out of scripts and into environment files
- replaced cron-based new-IP checker with an optional systemd timer
- fixed Telegram `/add` behavior so `xtls-rprx-vision` is only applied to Reality TCP inbounds
- added health check and public-config sanitizer
- pinned bot dependencies with Python 3.8+ compatibility markers
- made Telegram admin access fail closed when no ACL is configured
