# Gündəlik DB Backup Endirici (Emios + AKT-Portali, saat 09:00)

Məntiq:
- Remote: `/backup/dbbackups/29Oct2026/akt-29Oct2026.sql.gz`
- Local: `D:/Production-Database-Backups/Emios/29Oct2026/...` və `.../AKT-Portali/29Oct2026/...`
- Hər işəsalma: ən son tarix folderi endirilir + 30 gündən köhnələr avtomatik silinir.

## 1. Quraşdırma

```powershell
cd D:\opencodeXAsistant\db_backup_downloader
py -m pip install -r requirements.txt
```

## 2. Tənzimləmə

```powershell
py backup_download.py   # ilk dəfə config.json yaradır
```

Sonra `config.json`-i aç, 2 server üçün doldur:
- `host`: Emios və AKT server IP/host
- `username`, `password` (və ya `auth_type: key` + `key_file`)
- `remote_base`: `/backup/dbbackups` (ikində də eyni)
- `local_base`: `D:/Production-Database-Backups/Emios` və `D:/Production-Database-Backups/AKT-Portali`
- `retention_days`: 30

## 3. Test

```powershell
py backup_download.py --dry-run   # silmədən göstərir, nə silinəcək
py backup_download.py             # real endirmə + 30+ günlük təmizlik
```

## 4. Hər gün 09:00 (Task Scheduler, Administrator PowerShell)

```powershell
schtasks /create /tn "DB_Backup_9AM" /tr "C:\Users\hidayet.hidayetov\AppData\Local\Programs\Python\Python313\python.exe D:\opencodeXAsistant\db_backup_downloader\backup_download.py --config D:\opencodeXAsistant\db_backup_downloader\config.json" /sc daily /st 09:00 /f
schtasks /run /tn "DB_Backup_9AM"
```

Qeyd: kompüter 09:00-da açıq olmalıdır. "Missed start" halı üçün Task-da "Run as soon as possible after a scheduled start is missed" aç.

## Təhlükəsizlik

- Tarix kimi tanınmayan qovluqlara toxunulmur, yalnız `29Oct2026` formatı silinir.
- Eyni ölçülü fayl varsa təkrar endirilmir (`.part` ilə yarımçıq endirmə qorunur).
- Log: `backup_download.log`
