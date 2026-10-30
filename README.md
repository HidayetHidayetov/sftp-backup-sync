# sftp-backup-sync

Sync date-named backup folders from **N SFTP servers** to your PC, keep only the last **X days** locally.

Remote layout it understands:

```
/backup/dbbackups/29Oct2026/akt-29Oct2026.sql.gz
```

Local result:

```
./backups/server1/29Oct2026/...
./backups/server2/29Oct2026/...
```

## Features

- Unlimited servers (`servers` list in config)
- Per-server dynamic: `remote_base`, `local_base`, `file_pattern`,
  `retention_days`, `sync_mode` (`latest` | `last-n-days`), `sync_last_n`
- Dynamic daily schedule: `"schedule": {"time": "09:00"}` + `--install-schedule`
- Secrets via env: `"password": "${BACKUP_PASS_SERVER1}"` (never commit real passwords)
- Parallel downloads, `--only NAME`, `--dry-run`, skip-if-same-size, `.part` safety
- Safe retention: only date-parseable folders are deleted, unknown names are kept

## Quickstart

```bash
pip install -r requirements.txt
cp config.example.json config.json   # fill hosts/users/paths
python backup_download.py --dry-run
python backup_download.py
```

Single server test:

```bash
python backup_download.py --only server1
```

## Config

| Key | Where | Default | Meaning |
|-----|-------|---------|---------|
| `servers[].remote_base` | per server | — | remote dir with date folders |
| `servers[].local_base` | per server | — | local mirror dir |
| `servers[].file_pattern` | per server | `*` | e.g. `*.sql.gz` |
| `servers[].retention_days` | per server | `default_retention_days` | keep last N days locally |
| `servers[].sync_mode` | per server | `latest` | `latest` = newest folder, `last-n-days` = newest N folders |
| `servers[].sync_last_n` | per server | `7` | N for `last-n-days` |
| `schedule.time` | global | `09:00` | used by `--install-schedule` |
| `max_workers` | global | `4` | parallel server downloads |

Date folder formats: `29Oct2026`, `29-Oct-2026`, `2026-10-29`, `29.10.2026`, `20261029`, …

## Daily schedule

```bash
python backup_download.py --install-schedule --time 09:00
```

- Windows → creates a daily Task Scheduler entry
- Linux/macOS → prints a cron line to install

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).
