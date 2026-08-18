# Architecture

MIFA VPN Core follows the stable production topology of server 91 while removing unused monitoring components.

## Traffic

- `8443/tcp` → Xray VLESS/Reality/Vision
- `50273/tcp` → Xray VLESS/Reality/Vision
- `443/tcp` → nginx TLS termination
  - XHTTP path → `/dev/shm/mifa-xhttp.socket`
  - WebSocket path → `/dev/shm/mifa-ws.socket`
- `80/tcp` → ACME/bootstrap/HTTPS redirect

## Control plane

`mifa-xray-bot.service` runs the Telegram administration bot. Config changes use: backup → atomic write → Xray config test → restart → rollback on failure.

## Compatibility

WebSocket is retained for existing clients, but Reality and XHTTP are the primary transports.
