#!/usr/bin/env python3
"""Deploy the Prayer Earth trial site using one SSH session."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CF_TOKEN_FILE = Path(r"D:\Fight\OracleFree\ops\.cf-worker")
API = "https://api.cloudflare.com/client/v4"
ACCOUNT_ID = "a1bcc820c8574ff1923c8984cc6c005f"
ZONE = "diagport.com"
HOSTNAME = "prayer.diagport.com"
TUNNEL_NAME = "prayer-earth-trial"
REMOTE = "ubuntu@129.225.197.207"
SSH_KEY = Path.home() / ".ssh" / "oci_a1_ed25519"
REMOTE_ROOT = "/opt/prayer-earth-trial"
ORIGIN = "http://127.0.0.1:18080"
TOKEN_PATH = "/etc/prayer-earth-trial/tunnel-token.txt"
PYTHON = f"{REMOTE_ROOT}/venv/bin/python"


def read_kv(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"missing {key} in {path}")


def api(token: str, path: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "Bearer " + token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Cloudflare HTTP {error.code}: {error.read().decode(errors='replace')[:300]}") from error
    if not value.get("success"):
        raise RuntimeError(json.dumps(value.get("errors"), ensure_ascii=False))
    return value.get("result")


STATIC_UNIT = f"""[Unit]
Description=Prayer Earth trial static site
After=network-online.target
Wants=network-online.target

[Service]
User=prayer-web
Group=prayer-web
WorkingDirectory={REMOTE_ROOT}
ExecStart={PYTHON} {REMOTE_ROOT}/bin/serve-static.py --directory {REMOTE_ROOT}/site --data-directory {REMOTE_ROOT}/data --host 127.0.0.1 --port 18080
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
PrivateDevices=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths={REMOTE_ROOT}/data
UMask=0077
MemoryMax=512M
TasksMax=64
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
"""
TUNNEL_UNIT = f"""[Unit]
Description=Prayer Earth trial Cloudflare tunnel
After=network-online.target prayer-earth-trial.service
Wants=network-online.target

[Service]
User=cloudflared
Group=cloudflared
ExecStart=/usr/local/bin/cloudflared tunnel run --protocol http2 --token-file {TOKEN_PATH}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
PrivateDevices=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0077
MemoryMax=256M
TasksMax=32
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
"""

BACKUP_UNIT = f"""[Unit]
Description=Prayer Earth trial private data backup
After=prayer-earth-trial.service

[Service]
Type=oneshot
User=prayer-web
Group=prayer-web
ExecStart={PYTHON} {REMOTE_ROOT}/bin/backup-prayer-data.py --data-directory {REMOTE_ROOT}/data --backup-directory {REMOTE_ROOT}/backups --keep 14
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={REMOTE_ROOT}/data {REMOTE_ROOT}/backups
UMask=0077
"""
BACKUP_TIMER = """[Unit]
Description=Run Prayer Earth trial data backup every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
"""
SNAPSHOT_UNIT = f"""[Unit]
Description=Prayer Earth trial read-only content snapshot
After=prayer-earth-trial.service

[Service]
Type=oneshot
User=prayer-web
Group=prayer-web
ExecStart=/usr/bin/flock --wait 60 {REMOTE_ROOT}/snapshots/export.lock {PYTHON} {REMOTE_ROOT}/bin/generate-static-snapshot.py --data-directory {REMOTE_ROOT}/data --site-directory {REMOTE_ROOT}/site --output {REMOTE_ROOT}/snapshots/current
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={REMOTE_ROOT}/data {REMOTE_ROOT}/snapshots
UMask=0077
"""
SNAPSHOT_TIMER = """[Unit]
Description=Refresh Prayer Earth trial read-only snapshot every 15 minutes

[Timer]
OnBootSec=7min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
"""


def remote_install_script() -> str:
    return f"""#!/bin/sh
set -eu
stage=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    if ! id -u prayer-web >/dev/null 2>&1; then useradd --system --home /nonexistent --shell /usr/sbin/nologin prayer-web; fi
    if ! id -u cloudflared >/dev/null 2>&1; then useradd --system --home /nonexistent --shell /usr/sbin/nologin cloudflared; fi
    install -d -o root -g root -m 755 {REMOTE_ROOT}/site {REMOTE_ROOT}/bin
    install -d -o prayer-web -g prayer-web -m 700 {REMOTE_ROOT}/data {REMOTE_ROOT}/data/media {REMOTE_ROOT}/backups {REMOTE_ROOT}/snapshots
install -d -o root -g cloudflared -m 750 /etc/prayer-earth-trial
if [ -d "$stage/site" ]; then
  release=$(mktemp -d {REMOTE_ROOT}/.site-release.XXXXXX)
  cp -a "$stage/site/." "$release/"
  chown -R root:root "$release"
  find "$release" -type d -exec chmod 755 {{}} +
  find "$release" -type f -exec chmod 644 {{}} +
  if [ -d {REMOTE_ROOT}/site ]; then rm -rf {REMOTE_ROOT}/site.previous; mv {REMOTE_ROOT}/site {REMOTE_ROOT}/site.previous; fi
  mv "$release" {REMOTE_ROOT}/site
  rm -rf {REMOTE_ROOT}/site.previous
fi
    chown -R root:root {REMOTE_ROOT}/site
    find {REMOTE_ROOT}/site -type d -exec chmod 755 {{}} +
    find {REMOTE_ROOT}/site -type f -exec chmod 644 {{}} +
    chown -R prayer-web:prayer-web {REMOTE_ROOT}/data {REMOTE_ROOT}/backups {REMOTE_ROOT}/snapshots
    chmod 700 {REMOTE_ROOT}/data {REMOTE_ROOT}/data/media {REMOTE_ROOT}/backups {REMOTE_ROOT}/snapshots
install -o root -g root -m 755 "$stage/serve-static.py" {REMOTE_ROOT}/bin/serve-static.py
install -o root -g root -m 644 "$stage/admin_backend.py" {REMOTE_ROOT}/bin/admin_backend.py
install -o root -g root -m 644 "$stage/admin.html" {REMOTE_ROOT}/bin/admin.html
install -o root -g root -m 644 "$stage/generate-reader.py" {REMOTE_ROOT}/bin/generate-reader.py
    install -o root -g root -m 755 "$stage/backup-prayer-data.py" {REMOTE_ROOT}/bin/backup-prayer-data.py
    install -o root -g root -m 755 "$stage/generate-static-snapshot.py" {REMOTE_ROOT}/bin/generate-static-snapshot.py
    install -o root -g root -m 755 "$stage/export-reader-snapshot.py" {REMOTE_ROOT}/bin/export-reader-snapshot.py
    install -o cloudflared -g cloudflared -m 600 "$stage/tunnel-token.txt" {TOKEN_PATH}
test -f {REMOTE_ROOT}/site/index.html
cat > /etc/systemd/system/prayer-earth-trial.service <<'UNIT'
{STATIC_UNIT}UNIT
cat > /etc/systemd/system/prayer-earth-trial-tunnel.service <<'UNIT'
{TUNNEL_UNIT}UNIT
cat > /etc/systemd/system/prayer-earth-trial-backup.service <<'UNIT'
{BACKUP_UNIT}UNIT
cat > /etc/systemd/system/prayer-earth-trial-backup.timer <<'UNIT'
{BACKUP_TIMER}UNIT
cat > /etc/systemd/system/prayer-earth-trial-snapshot.service <<'UNIT'
{SNAPSHOT_UNIT}UNIT
cat > /etc/systemd/system/prayer-earth-trial-snapshot.timer <<'UNIT'
{SNAPSHOT_TIMER}UNIT
rm -f /etc/prayer-earth-trial/tunnel.env
systemctl daemon-reload
systemctl enable prayer-earth-trial.service prayer-earth-trial-tunnel.service prayer-earth-trial-backup.timer prayer-earth-trial-snapshot.timer
systemctl restart prayer-earth-trial.service prayer-earth-trial-tunnel.service
systemctl start prayer-earth-trial-backup.timer prayer-earth-trial-snapshot.timer
systemctl is-active --quiet prayer-earth-trial.service
systemctl is-active --quiet prayer-earth-trial-tunnel.service
systemctl is-active --quiet prayer-earth-trial-backup.timer
systemctl is-active --quiet prayer-earth-trial-snapshot.timer
ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 5 {ORIGIN}/ >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" = 1
"""


class SingleSSH:
    """One SSH process carries the archive and runs the complete install."""

    def __init__(self) -> None:
        self.args = [
            "ssh", "-i", str(SSH_KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15",
            "-o", "ConnectionAttempts=1", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", REMOTE,
            "set -eu; stage=$(mktemp -d /tmp/prayer-trial.XXXXXX); "
            "trap 'sudo rm -rf \"$stage\"' EXIT; sudo tar -xf - -C \"$stage\"; "
            "sudo sh \"$stage/install.sh\"",
        ]

    def deploy(self, *, token: str, upload: bool) -> None:
        process = subprocess.Popen(self.args, stdin=subprocess.PIPE)
        assert process.stdin is not None
        # Bound the streaming upload itself, including blocked writes to SSH.
        timer = threading.Timer(900, process.kill)
        timer.daemon = True
        timer.start()
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                archive.add(PROJECT / "scripts" / "serve-static.py", arcname="serve-static.py")
                archive.add(PROJECT / "scripts" / "admin_backend.py", arcname="admin_backend.py")
                archive.add(PROJECT / "scripts" / "admin.html", arcname="admin.html")
                archive.add(PROJECT / "scripts" / "generate-reader.py", arcname="generate-reader.py")
                archive.add(PROJECT / "scripts" / "backup-prayer-data.py", arcname="backup-prayer-data.py")
                archive.add(PROJECT / "scripts" / "generate-static-snapshot.py", arcname="generate-static-snapshot.py")
                archive.add(PROJECT / "scripts" / "export-reader-snapshot.py", arcname="export-reader-snapshot.py")
                add_bytes(archive, "install.sh", remote_install_script().encode())
                add_bytes(archive, "tunnel-token.txt", (token + "\n").encode())
                if upload:
                    archive.add(PROJECT / "dist", arcname="site")
            process.stdin.close()
            result = process.wait(timeout=900)
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            timer.cancel()
        if result:
            raise RuntimeError(f"single SSH deployment failed (exit={result})")


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o700 if name == "install.sh" else 0o600
    archive.addfile(info, io.BytesIO(data))


def verify_public() -> None:
    request = urllib.request.Request(
        f"https://{HOSTNAME}/", method="GET",
        headers={"User-Agent": "Mozilla/5.0 (PrayerEarth health check)"},
    )
    last: Exception | None = None
    # A tunnel restart can briefly return Cloudflare 403/502 while its
    # connectors register. Keep probing long enough for the service to settle.
    for _ in range(18):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise RuntimeError(f"public check returned HTTP {response.status}")
                return
        except (OSError, urllib.error.URLError, RuntimeError) as error:
            last = error
            time.sleep(5)
    raise RuntimeError(f"public check failed: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the Prayer Earth trial web site")
    parser.add_argument("--repair", action="store_true", help="repair services without uploading dist/")
    parser.add_argument("--skip-upload", action="store_true", help="reuse the existing remote site")
    args = parser.parse_args()
    upload = not (args.repair or args.skip_upload)
    if upload and not (PROJECT / "dist" / "index.html").exists():
        raise RuntimeError("dist/index.html not found; run npm run build:web first")
    token = read_kv(CF_TOKEN_FILE, "CF_API_TOKEN")
    zone_id = api(token, "/zones?name=" + ZONE)[0]["id"]
    records = api(token, f"/zones/{zone_id}/dns_records?name={HOSTNAME}")
    if len(records) > 1:
        raise RuntimeError(f"multiple DNS records already exist for {HOSTNAME}; refusing to choose one")
    tunnels = api(token, f"/accounts/{ACCOUNT_ID}/cfd_tunnel?is_deleted=false")
    tunnel = next((item for item in tunnels if item.get("name") == TUNNEL_NAME), None)
    if tunnel is None:
        if args.repair:
            raise RuntimeError(f"tunnel {TUNNEL_NAME!r} not found; --repair will not create one")
        if records:
            raise RuntimeError(f"DNS already exists for {HOSTNAME}, but tunnel {TUNNEL_NAME!r} was not found; refusing to create or replace anything")
        tunnel = api(token, f"/accounts/{ACCOUNT_ID}/cfd_tunnel", "POST", {"name": TUNNEL_NAME, "config_src": "cloudflare"})
    tunnel_id = tunnel["id"]
    expected = (tunnel_id + ".cfargotunnel.com").rstrip(".").lower()
    if records:
        record = records[0]
        if record.get("type") != "CNAME" or record.get("content", "").rstrip(".").lower() != expected:
            raise RuntimeError(f"existing DNS record for {HOSTNAME} does not point to {TUNNEL_NAME}; refusing to overwrite")
    api(token, f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/configurations", "PUT", {"config": {"ingress": [{"hostname": HOSTNAME, "service": ORIGIN}, {"service": "http_status:404"}]}})
    tunnel_token = api(token, f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/token")
    SingleSSH().deploy(token=str(tunnel_token), upload=upload)
    for attempt in range(6):
        state = api(token, f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}")
        if state.get("status") == "healthy":
            break
        if attempt == 5:
            raise RuntimeError("tunnel is not healthy after installation; DNS was not published")
        time.sleep(5)
    if not records:
        api(token, f"/zones/{zone_id}/dns_records", "POST", {"type": "CNAME", "name": HOSTNAME, "content": tunnel_id + ".cfargotunnel.com", "proxied": True, "ttl": 1, "comment": "Prayer Earth 同工手机网页试用版"})
    verify_public()
    print(f"Trial URL: https://{HOSTNAME}")
    print(f"Tunnel ID: {tunnel_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print("FAIL:", error, file=sys.stderr)
        raise SystemExit(1)
