#!/usr/bin/env python3
"""SFTP Backup Sync — N serverden tarix-folderli backup endir + retensiya.

Remote struktur:
  /backup/dbbackups/29Oct2026/db-29Oct2026.sql.gz

Local struktur:
  ./backups/server1/29Oct2026/...
  ./backups/server2/29Oct2026/...

Xususiyyetler:
  - limitsiz server (config `servers` siyahisi)
  - her serverde dinamik: remote_base, local_base, file_pattern,
    retention_days, sync_mode (latest | last-n-days), sync_last_n
  - parollar `${ENV_VAR}` kimi yazila biler (secret commit olunmur)
  - paralel endirme (ThreadPoolExecutor)
  - --dry-run, --only SERVER, --install-schedule (09:00 ve s.)

Misal:
    pip install -r requirements.txt
    cp config.example.json config.json  # doldur
    python backup_download.py --dry-run
    python backup_download.py
    python backup_download.py --install-schedule --time 09:00
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fnmatch
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import paramiko
except ImportError:  # requirements.txt: pip install -r requirements.txt
    paramiko = None  # type: ignore[assignment]

__version__ = "1.1.0"

DATE_FORMATS = [
    "%d%b%Y",    # 29Oct2026
    "%d-%b-%Y",  # 29-Oct-2026
    "%d_%b_%Y",  # 29_Oct_2026
    "%d%b%y",    # 29Oct26
    "%Y-%m-%d",  # 2026-10-29
    "%d.%m.%Y",  # 29.10.2026
    "%d_%m_%Y",  # 29_10_2026
    "%Y%m%d",    # 20261029
    "%d-%m-%Y",  # 29-10-2026
]

DEFAULTS = {
    "log_file": "backup_download.log",
    "log_level": "INFO",
    "connect_timeout_sec": 15,
    "default_retention_days": 30,
    "default_sync_mode": "latest",
    "default_sync_last_n": 7,
    "max_workers": 4,
}


def parse_date_folder(name: str) -> date | None:
    s = name.strip()
    variants = (s, s.title())  # "29oct2026" kimi kicik herf de tutulur
    for text in variants:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def expand_env(value):
    """`${VAR}` / `$VAR` / `${VAR:-default}` genislenmesi. Yalniz str ucun."""
    if not isinstance(value, str):
        return value
    return os.path.expandvars(os.path.expanduser(value))


def setup_logging(log_file: str | None, level: str = "INFO") -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        base = Path(__file__).resolve().parent
        log_path = Path(expand_env(log_file))
        if not log_path.is_absolute():
            log_path = base / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("sftp-backup-sync")


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULTS)
    merged.update(cfg)
    servers = merged.get("servers")
    if not isinstance(servers, list) or not servers:
        raise ValueError("config-da bos olmayan 'servers' siyahisi olmalidir")
    seen: set[str] = set()
    for srv in servers:
        for key in ("name", "host", "username", "remote_base", "local_base"):
            if not srv.get(key):
                raise ValueError(f"serverde '{key}' teleb olunur: {srv}")
        if srv["name"] in seen:
            raise ValueError(f"tekrarlanan server name: {srv['name']}")
        seen.add(srv["name"])
        mode = srv.get("sync_mode", merged["default_sync_mode"])
        if mode not in ("latest", "last-n-days"):
            raise ValueError(f"[{srv['name']}] sync_mode 'latest' ve ya 'last-n-days' olmalidir")
    return merged


def server_cfg(cfg: dict, srv: dict, key: str):
    """Server deyeri yoxdursa global defaulta dusur."""
    if srv.get(key) is not None:
        return srv[key]
    fallback = {
        "retention_days": "default_retention_days",
        "sync_mode": "default_sync_mode",
        "sync_last_n": "default_sync_last_n",
    }.get(key, key)
    return cfg.get(fallback)


def pick_target_dirs(sftp, remote_base: str, sync_mode: str, sync_last_n: int,
                     log: logging.Logger, server_name: str) -> list[str]:
    entries = sftp.listdir_attr(remote_base)
    dirs = [e for e in entries if stat.S_ISDIR(e.st_mode)]
    if not dirs:
        return []
    scored = [(parse_date_folder(d.filename), d.st_mtime or 0, d.filename) for d in dirs]
    with_date = [s for s in scored if s[0] is not None]
    ranked = sorted(with_date, key=lambda x: (x[0], x[1])) if with_date else sorted(scored, key=lambda x: x[1])
    if not with_date:
        log.warning(f"[{server_name}] Tarix parse olunmadi, mtime-ye gore secilir.")
    n = 1 if sync_mode == "latest" else max(1, int(sync_last_n))
    return [name for _, _, name in ranked[-n:]]


def download_file(sftp, remote_path: str, local_path: Path,
                  remote_size: int, log: logging.Logger, server_name: str) -> None:
    if local_path.exists() and local_path.stat().st_size == remote_size:
        log.info(f"[{server_name}] Artiq var, atlanir: {local_path.name}")
        return
    local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = local_path.with_name(local_path.name + ".part")
    sftp.get(remote_path, str(tmp_path))
    os.replace(tmp_path, local_path)
    log.info(f"[{server_name}] Endirildi: {local_path.name} ({remote_size / 1024 / 1024:.1f} MB)")


def download_dir_recursive(sftp, remote_dir: str, local_dir: Path,
                           pattern: str, log: logging.Logger, server_name: str) -> int:
    count = 0
    local_dir.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_dir):
        r = f"{remote_dir.rstrip('/')}/{entry.filename}"
        target = local_dir / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            count += download_dir_recursive(sftp, r, target, pattern, log, server_name)
        else:
            if pattern and pattern != "*" and not fnmatch.fnmatch(entry.filename, pattern):
                continue
            download_file(sftp, r, target, entry.st_size, log, server_name)
            count += 1
    return count


def cleanup_old(local_base: Path, retention_days: int, dry_run: bool,
                log: logging.Logger, server_name: str) -> list[str]:
    """retention_days-den kohne tarix qovluqlarini silir.

    Yalniz tarix kimi parse olunanlar silinir — taninmayan adlara toxunulmur.
    """
    deleted: list[str] = []
    if retention_days <= 0 or not local_base.is_dir():
        return deleted
    today = date.today()
    for child in sorted(local_base.iterdir()):
        if not child.is_dir() or child.name.endswith(".part"):
            continue
        parsed = parse_date_folder(child.name)
        if parsed is None:
            continue
        age = (today - parsed).days
        if age > retention_days:
            if dry_run:
                log.info(f"[{server_name}] [DRY-RUN] Silecekdi ({age} gun): {child}")
            else:
                shutil.rmtree(child, ignore_errors=True)
                log.info(f"[{server_name}] Silindi ({age} gun kohne): {child}")
            deleted.append(child.name)
    return deleted


def connect_sftp(server: dict, timeout: int):
    if paramiko is None:
        raise RuntimeError("paramiko qurulu deyil: pip install -r requirements.txt")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict = {
        "hostname": expand_env(server["host"]),
        "port": int(server.get("port", 22)),
        "username": expand_env(server["username"]),
        "timeout": timeout,
        "banner_timeout": timeout,
        "auth_timeout": timeout,
    }
    if server.get("auth_type", "password") == "key":
        if server.get("key_file"):
            kwargs["key_filename"] = expand_env(server["key_file"])
        if server.get("key_passphrase"):
            kwargs["passphrase"] = expand_env(server["key_passphrase"])
        if server.get("password"):
            kwargs["password"] = expand_env(server["password"])
    else:
        if server.get("password"):
            kwargs["password"] = expand_env(server["password"])
        if server.get("key_file"):
            kwargs["key_filename"] = expand_env(server["key_file"])
    client.connect(**kwargs)
    return client


def process_server(cfg: dict, server: dict, timeout: int, dry_run: bool,
                   log: logging.Logger) -> bool:
    name = server["name"]
    remote_base = expand_env(server["remote_base"])
    local_base = Path(expand_env(server["local_base"]))
    pattern = server.get("file_pattern", "*")
    retention = int(server_cfg(cfg, server, "retention_days"))
    sync_mode = str(server_cfg(cfg, server, "sync_mode"))
    sync_last_n = int(server_cfg(cfg, server, "sync_last_n"))
    local_base.mkdir(parents=True, exist_ok=True)

    log.info(f"[{name}] Qosulur: {expand_env(server['username'])}@{expand_env(server['host'])} ...")
    client = None
    try:
        client = connect_sftp(server, timeout)
        sftp = client.open_sftp()
        try:
            targets = pick_target_dirs(sftp, remote_base, sync_mode, sync_last_n, log, name)
            if not targets:
                log.warning(f"[{name}] Bosdur: {remote_base}")
                return False
            log.info(f"[{name}] Hedef ({sync_mode}): {', '.join(targets)}")
            total = 0
            for t in targets:
                total += download_dir_recursive(
                    sftp, f"{remote_base.rstrip('/')}/{t}",
                    local_base / t, pattern, log, name)
            log.info(f"[{name}] Sinxronlandi: {local_base} ({total} fayl)")
        finally:
            try:
                sftp.close()
            except Exception:
                pass
    except Exception as e:
        log.error(f"[{name}] XETA: {type(e).__name__}: {e}")
        return False
    finally:
        if client:
            client.close()

    try:
        deleted = cleanup_old(local_base, retention, dry_run, log, name)
        if deleted:
            log.info(f"[{name}] Retensiya: {len(deleted)} qovluq silindi: {', '.join(deleted)}")
        else:
            log.info(f"[{name}] Retensiya: silinecek kohne yoxdur (son {retention} gun).")
    except Exception as e:
        log.error(f"[{name}] Temizlik xetasi: {e}")
        return False
    return True


def install_schedule(time_str: str, config_path: Path, task_name: str = "SFTP_Backup_Sync") -> int:
    """Gunluk ise salmani qurasdirir. Zamani dinamik: --time HH:MM."""
    try:
        hour, minute = time_str.split(":")
        assert 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except Exception:
        print(f"Sehv saat formati: {time_str} (gozlenilen HH:MM, mes: 09:00)")
        return 2
    script = Path(__file__).resolve()
    python = sys.executable
    cmd = f'{python} "{script}" --config "{config_path.resolve()}"'
    system = platform.system()
    if system == "Windows":
        full = (f'schtasks /create /tn "{task_name}" /tr "{cmd}" '
                f"/sc daily /st {time_str} /f")
        print(f"Windows Task yaradilir:\n  {full}")
        r = subprocess.run(full, shell=True)
        if r.returncode == 0:
            print(f"Hazirdir: her gun {time_str} ({task_name}). Yoxla: schtasks /query /tn \"{task_name}\"")
        return r.returncode
    # Linux / macOS: cron
    cron_line = f"{int(minute)} {int(hour)} * * * {cmd} >> {script.parent}/cron.log 2>&1"
    print("Cron setri elave edilir:")
    print(f"  {cron_line}")
    print("Emr:\n  (crontab -l 2>/dev/null; echo '"
          + cron_line + "') | crontab -")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SFTP Backup Sync — N server, dinamik cedvel + retensiya")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--dry-run", action="store_true", help="silmeden goster")
    ap.add_argument("--only", action="append", default=[], help="yalniz bu server (tekrarlana biler)")
    ap.add_argument("--install-schedule", action="store_true", help="gunluk task qurasdir")
    ap.add_argument("--time", default=None, help="cedvel saati HH:MM (default config schedule.time)")
    ap.add_argument("--task-name", default="SFTP_Backup_Sync")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    cfg_path = Path(expand_env(args.config))
    if not cfg_path.is_absolute():
        cfg_path = base / cfg_path

    if not cfg_path.exists():
        example = base / "config.example.json"
        if example.exists():
            shutil.copy(example, cfg_path)
            print(f"config yaradildi: {cfg_path} — doldurub yeniden ise salin.")
            return 2
        print(f"config tapilmadi: {cfg_path}")
        return 2

    cfg = load_config(cfg_path)

    if args.install_schedule:
        schedule = cfg.get("schedule") or {}
        t = args.time or schedule.get("time", "09:00")
        return install_schedule(t, cfg_path, args.task_name)

    log = setup_logging(cfg.get("log_file"), cfg.get("log_level", "INFO"))
    timeout = int(cfg.get("connect_timeout_sec", 15))

    servers = cfg["servers"]
    if args.only:
        wanted = set(args.only)
        servers = [s for s in servers if s["name"] in wanted]
        if not servers:
            log.error(f"--only uygun gelmedi. Movcud: {', '.join(s['name'] for s in cfg['servers'])}")
            return 2

    log.info(f"Basladi (dry_run={args.dry_run}). Server sayi: {len(servers)}")
    workers = max(1, min(int(cfg.get("max_workers", 4)), len(servers)))
    results: dict[str, bool] = {}
    if workers == 1:
        for srv in servers:
            results[srv["name"]] = process_server(cfg, srv, timeout, args.dry_run, log)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(process_server, cfg, srv, timeout, args.dry_run, log): srv["name"]
                          for srv in servers}
            for fut in concurrent.futures.as_completed(future_map):
                results[future_map[fut]] = fut.result()

    failed = sorted(k for k, v in results.items() if not v)
    if failed:
        log.error(f"Bitdi. UGURSUZ: {', '.join(failed)}")
        return 1
    log.info("Bitdi. Hamisi ugurlu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
