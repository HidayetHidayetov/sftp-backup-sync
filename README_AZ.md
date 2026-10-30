# SFTP Backup Sync — AZ təlimat

N sayda serverdən tarix-folderli backup endirir, seçdiyin gün sayını saxlayır.

Məntiq:
- Remote: `/backup/dbbackups/29Oct2026/db-29Oct2026.sql.gz`
- Local: `./backups/server1/29Oct2026/...`, `./backups/server2/29Oct2026/...`
- `servers` siyahısına istədiyin qədər server əlavə edə bilərsən.

## 1. Quraşdırma

```bash
pip install -r requirements.txt
cp config.example.json config.json   # doldur
```

## 2. Tənzimləmə (`config.json`)

Hər server üçün dinamikdir:

| Sahə | Məna |
|------|------|
| `host`, `port`, `username` | server bağlantısı |
| `password` | `"${BACKUP_PASS_SERVER1}"` kimi ENV yaz (açıq şifrə commit etmə!) |
| `remote_base` | serverdəki qovluq, məs `/backup/dbbackups` |
| `local_base` | lokaldakı qovluq, məs `./backups/server1` |
| `file_pattern` | məs `*` və ya `*.sql.gz` |
| `retention_days` | neçə günlük saxlansın |
| `sync_mode` | `latest` (ən son 1) və ya `last-n-days` (son N folder) |
| `sync_last_n` | `last-n-days` üçün N |

Qlobal: `schedule.time` (məs `09:00`), `default_retention_days`, `max_workers`.

Şifrələri mühit dəyişənində saxla (Windows):

```powershell
setx BACKUP_PASS_SERVER1 "senin_sifren"
```

## 3. Test

```bash
python backup_download.py --dry-run --only server1
python backup_download.py --dry-run
python backup_download.py
```

## 4. Hər gün avtomat (saat dinamikdir)

```bash
python backup_download.py --install-schedule --time 09:00
```

Windows-da Task Scheduler, Linux/macOS-da cron sətrini çap edir.

## Təhlükəsizlik

- Adı tarix kimi tanınmayan qovluq silinmir.
- Eyni ölçülü fayl təkrar endirilmir, yarımçıq endirmə `.part` ilə qorunur.
- `config.json` git-ə düşmür (`.gitignore`), real IP/şifrə paylaşma.
