# MIFA VPN Core

> **MIFA VPN Core v1.0.0** — simplified self-hosted VPN platform based on the proven production configuration of MIFA server 91.

The previous **MIFA VPN Platform** architecture used Xray together with Grafana, Prometheus, Loki and Promtail. That platform proved stable in production, but the monitoring stack was later removed to reduce operational complexity and digital noise.

MIFA VPN Core keeps only the components that are actively used.

## Architecture

```text
Internet
  │
  ├── TCP 8443 ─────────► Xray VLESS + Reality + Vision
  ├── TCP 50273 ────────► Xray VLESS + Reality + Vision
  │
  └── TCP 443 ──────────► nginx + TLS
                            │
                            ├── XHTTP ─► Unix socket ─► Xray
                            └── WS    ─► Unix socket ─► Xray (legacy)

Telegram ───────────────► MIFA Admin Bot ─► Xray config
```

## Included

- Xray / VLESS / Reality
- XHTTP over nginx/TLS
- WebSocket compatibility transport
- nginx
- Let's Encrypt / Certbot
- Telegram administration bot
- optional new-IP notifier
- safe Xray config apply with rollback
- backup / restore
- health checks

## Removed from the old platform

- Grafana
- Prometheus
- Loki
- Promtail
- xray-exporter
- Docker monitoring stack
- Xray Stats/Metrics API

## Supported production layout

| Transport | Endpoint | Purpose |
|---|---:|---|
| VLESS + Reality | `8443/tcp` | primary Reality transport |
| VLESS + Reality | `50273/tcp` | alternate Reality transport |
| VLESS + XHTTP + TLS | `443/tcp` | domain TLS transport |
| VLESS + WebSocket + TLS | `443/tcp` | legacy compatibility |

## Quick install

On a clean Debian/Ubuntu server (Python 3.8+):

```bash
sudo ./install.sh --domain vpn.example.com
```

Optional Certbot email:

```bash
sudo ./install.sh --domain vpn.example.com --email admin@example.com
```

The installer pins Xray to `25.8.3` by default to reproduce the production baseline. Override it with:

```bash
XRAY_VERSION=25.8.3 sudo -E ./install.sh --domain vpn.example.com
```

After install, fill Telegram credentials and at least one access-control field (`ADMIN_IDS` or `ALLOWED_CHAT_ID`):

```bash
sudo nano /etc/mifa/bot.env
sudo systemctl restart mifa-xray-bot
```

## Telegram commands

```text
/add <alias>
/del <alias>
/list
/key <alias> [8443|50273|xhttp|ws|all]
/info
/status
/restart
```

New users are created correctly per transport:

- Reality TCP → `flow=xtls-rprx-vision`
- XHTTP → no Reality flow field
- WebSocket → no Reality flow field

## Backup

```bash
sudo ./scripts/backup.sh
```

Backups contain production secrets and are written with mode `0600`. **Never commit them to Git.**

Restore onto a machine where MIFA VPN Core is already installed:

```bash
sudo ./scripts/restore.sh /root/mifa-backups/mifa-backup-YYYYMMDD-HHMMSS.tar.gz
```

See [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md).

## Security

Never commit:

- Reality private keys
- Telegram bot tokens
- user UUIDs from production
- `/etc/mifa/*.env`
- backups
- Let's Encrypt private keys

The admin bot fails closed unless `ADMIN_IDS` and/or `ALLOWED_CHAT_ID` is configured.

The repository contains templates only.

## Legacy project

The original MIFA VPN Platform is considered feature-complete and archived. MIFA VPN Core is the maintained simplified architecture.
