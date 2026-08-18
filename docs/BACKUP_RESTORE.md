# Backup and restore

## Create a production backup

```bash
sudo mifa-backup
```

Default destination: `/root/mifa-backups/mifa-backup-YYYYMMDD-HHMMSS.tar.gz` plus a `.sha256` sidecar.

The archive can include Xray users and Reality private key, Telegram credentials, transport paths, nginx site state, web root and Let's Encrypt material. Treat it as a secret and keep it outside Git.

## Restore

1. Install the same MIFA VPN Core release on the replacement machine.
2. Copy the backup and `.sha256` file.
3. Run `sudo mifa-restore /root/mifa-backups/<backup>.tar.gz`.

The restore checks archive paths, restores state, validates Xray and nginx, then restarts services.
