# SFTP Backup Sync — AZ təlimat (v1)

N sayda serverdən tarix-folderli backup endirir, seçdiyin gün sayını saxlayır.

Məntiq:
- Remote: `/backup/dbbackups/29Oct2026/akt-29Oct2026.sql.gz`
- Local: `D:/Production-Database-Backups/Emios/29Oct2026/...`
- Sənin ssenarin: 2 server (Emios + AKT-Portali), amma istədiyin qədər əlavə edə bilərsən.

## 1. Quraşdırma

```powershell
cd D:\opencodeXAsistant\db_backup_downloader
py -m pip install -r requirements.txt
py backup_download.py   # ilk dəfə config.json yaradır
```

## 2. Tənzimləmə (`config.json`)

Hər server üçün dinamikdir:

| Sahə | Məna |
|------|------|
| `host`, `port`, `username` | server bağlantısı |
| `password` | `"${BACKUP_PASS_EMIOS}"` kimi ENV yaz (açıq şifrə commit etmə!) |
| `remote_base` | serverdəki qovluq, məs `/backup/dbbackups` |
| `local_base` | PC-dəki qovluq, məs `D:/Production-Database-Backups/Emios` |
| `file_pattern` | məs `*` və ya `*.sql.gz` |
| `retention_days` | neçə günlük saxlansın (səndə 30) |
| `sync_mode` | `latest` (ən son 1) və ya `last-n-days` (son N folder) |
| `sync_last_n` | `last-n-days` üçün N |

Qlobal: `schedule.time` (məs `09:00`), `default_retention_days`, `max_workers`.

Şifrələri ENV-də saxla:

```powershell
setx BACKUP_PASS_EMIOS "senin_sifren"
setx BACKUP_PASS_AKT "senin_sifren"
```

## 3. Test

```powershell
py backup_download.py --dry-run --only Emios
py backup_download.py --dry-run
py backup_download.py
```

## 4. Hər gün avtomat (saat dinamikdir)

```powershell
py backup_download.py --install-schedule --time 09:00
```

Saat dəyişmək istəsən `--time 14:30` ilə təkrar işə sal. Kompüter o saatda açıq olmalıdır.

## Təhlükəsizlik

- Adı tarix kimi tanınmayan qovluq silinmir.
- Eyni ölçülü fayl təkrar endirilmir, yarımçıq endirmə `.part` ilə qorunur.
- `config.json` git-ə düşmür (`.gitignore`), real IP/şifrə paylaşma.
