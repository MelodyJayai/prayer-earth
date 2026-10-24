#!/usr/bin/env python3
"""Publish a complete read-only snapshot to reader.bytelanework.com.

The Cloudflare credential stays on this publishing host, never on the OCI
origin. Only public snapshots are pulled over SSH. Static assets are uploaded
before a single Worker deployment makes the complete release visible.
Protocol: https://developers.cloudflare.com/workers/static-assets/direct-upload/
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = Path(r"D:\Fight\OracleFree\ops\.cf-token-proxy")
WORK = ROOT / ".reader-publish"
API = "https://api.cloudflare.com/client/v4"
ACCOUNT_ID = "a5d4155be82d3440deb88afe079ed86b"
ZONE_ID = "17179c9d17e1f47bfba4d35048f85563"
HOSTNAME = "reader.bytelanework.com"
WORKER = "prayer-reader-failover"
SOURCE = ROOT / "scripts" / "cf-reader-failover.js"
SSH_KEY = Path(r"C:\Users\Administrator\.ssh\oci_a1_ed25519")
KNOWN_HOSTS = Path(r"C:\Users\Administrator\.ssh\known_hosts")
SSH = Path(r"C:\Windows\System32\OpenSSH\ssh.exe")
SECURITY_HEADERS = """/*
  Strict-Transport-Security: max-age=31536000
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Cross-Origin-Resource-Policy: same-origin
  X-Robots-Tag: noindex, nofollow
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'
  Cache-Control: public, max-age=0, must-revalidate
"""
ASSET_CONFIG = {
    "html_handling": "none",
    "not_found_handling": "none",
    "run_worker_first": False,
    "_headers": SECURITY_HEADERS,
    "_redirects": "/ /reader/index.html 302\n/index.html /reader/index.html 302\n",
}
MAX_FILE = 25 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
HEALTH_IP = None


def log(message):
    print(dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), message, flush=True)


@contextmanager
def publisher_lock():
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "publish.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("invalid snapshot path")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part.startswith(".") for part in path.parts):
        raise ValueError("invalid snapshot path")
    if name in ("index.html", "health.json", "manifest.json"):
        return path
    if re.fullmatch(r"reader/[A-Za-z0-9][A-Za-z0-9_-]*\.html", name):
        return path
    if (name.startswith(("assets/content/", "assets/assets/content/", "media/"))
            and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")):
        return path
    raise ValueError("non-public file in snapshot")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "iframe", "object", "embed", "form"):
            raise ValueError("active content in snapshot")
        for key, value in attrs:
            if key.lower().startswith("on"):
                raise ValueError("event handler in snapshot")
            if key in ("href", "src") and value:
                self.references.append((tag, value))


def validate_snapshot(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    health = json.loads((folder / "health.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    if not 1 <= len(files) <= 19998 or manifest.get("schema") != 1:
        raise ValueError("invalid snapshot manifest")
    if health.get("contentVersion") != manifest["contentVersion"] or health.get("counts") != manifest["counts"]:
        raise ValueError("inconsistent health record")
    required = {"index.html", "reader/index.html", "reader/morning.html", "reader/mission.html"}
    if not required.issubset(files):
        raise ValueError("missing reader entry pages")
    expected = set(files) | {"manifest.json", "health.json"}
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != expected or len({name.lower() for name in expected}) != len(expected):
        raise ValueError("unexpected or case-colliding snapshot files")
    total = 0
    for name in expected:
        safe_path(name)
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError("snapshot link outside folder")
        content = path.read_bytes()
        if len(content) > MAX_FILE:
            raise ValueError("snapshot file exceeds host limit")
        total += len(content)
        if name in files and digest(content) != files[name]:
            raise ValueError("snapshot checksum mismatch: " + name)
        if name.endswith(".html"):
            links = Links()
            links.feed(content.decode("utf-8"))
            for tag, reference in links.references:
                if tag == "base" and reference == "/reader/":
                    continue
                if reference.startswith("//"):
                    raise ValueError("external snapshot reference")
                resolved = urllib.parse.urljoin("https://snapshot.invalid/reader/index.html" if name == "index.html"
                                                else "https://snapshot.invalid/" + name, reference)
                url = urllib.parse.urlsplit(resolved)
                target = urllib.parse.unquote(url.path).lstrip("/") or "index.html"
                if url.scheme != "https" or url.netloc != "snapshot.invalid" or target not in expected:
                    raise ValueError("broken or external snapshot reference: " + reference)
    if total > MAX_TOTAL:
        raise ValueError("snapshot exceeds publishing size limit")
    return manifest


def read_token(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("CF_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("CF_API_TOKEN missing from credential file")


def api(cf_token, path, method="GET", payload=None, raw=None, content_type=None):
    body = raw
    headers = {"Authorization": "Bearer " + cf_token, "User-Agent": "PrayerReaderPublisher/1"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    for attempt in range(3):
        try:
            request = urllib.request.Request(API + path, data=body, method=method, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                value = json.load(response)
            if not value.get("success"):
                raise RuntimeError("Cloudflare API unsuccessful: " + str([e.get("code") for e in value.get("errors", [])]))
            return value.get("result")
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            # Do not echo server bodies, JWTs, headers, or API tokens to logs.
            raise RuntimeError(f"Cloudflare API HTTP {error.code} for {method} {path.split('?')[0]}") from None


def multipart(fields, files):
    boundary = "----PrayerReader-" + os.urandom(12).hex()
    chunks = []
    for name, value in fields.items():
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\nContent-Type: application/json\r\n\r\n'.encode(),
                       json.dumps(value).encode(), b"\r\n"])
    for name, (content, content_type) in files.items():
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode(),
                       content, b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def extract_delta(archive_file, folder):
    # Never use extractall() on an archive from a remote host.
    seen = set()
    total = 0
    controls = {}
    with tarfile.open(archive_file, mode="r:") as archive:
        for member in archive:
            safe_path(member.name)
            if not member.isfile() or member.name.lower() in seen or member.size > MAX_FILE:
                raise ValueError("invalid snapshot archive member")
            seen.add(member.name.lower())
            total += member.size
            if total > MAX_TOTAL or len(seen) > 20000:
                raise ValueError("snapshot archive too large")
            content = archive.extractfile(member).read()
            if member.name in ("manifest.json", "health.json"):
                controls[member.name] = content
                continue
            destination = folder / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".incoming")
            temporary.write_bytes(content)
            temporary.replace(destination)
    if set(controls) != {"manifest.json", "health.json"}:
        raise ValueError("snapshot archive missing manifest")
    expected = set(json.loads(controls["manifest.json"])["files"]) | set(controls)
    for name in expected:
        safe_path(name)
    for path in folder.rglob("*"):
        if path.is_file() and path.relative_to(folder).as_posix() not in expected:
            path.unlink()
    for name, content in controls.items():
        (folder / name).write_bytes(content)


def pull_snapshot(folder):
    folder.mkdir(parents=True, exist_ok=True)
    known = {}
    for path in folder.rglob("*"):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            try:
                safe_path(relative)
            except ValueError:
                # An interrupted previous write may leave a .incoming file;
                # it is never trusted and is pruned after a complete pull.
                continue
            known[relative] = digest(path.read_bytes())
    args = [str(SSH), "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(KNOWN_HOSTS), "-o", "ConnectTimeout=20",
            "-o", "ConnectionAttempts=1", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
            "ubuntu@129.225.197.207", "sudo -n systemctl start prayer-earth-trial-snapshot.service && sudo -n python3 /opt/prayer-earth-trial/bin/export-reader-snapshot.py"]
    with tempfile.NamedTemporaryFile(dir=WORK, suffix=".tar", delete=False) as temporary:
        archive_path = Path(temporary.name)
        try:
            subprocess.run(args, input=json.dumps(known).encode(), stdout=temporary, check=True, timeout=600)
            temporary.close()
            extract_delta(archive_path, folder)
        finally:
            temporary.close()
            archive_path.unlink(missing_ok=True)
    return validate_snapshot(folder)


def asset_manifest(folder):
    files = {}
    by_hash = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            safe_path(relative)
            content = path.read_bytes()
            # This follows Cloudflare's documented direct-upload hash algorithm.
            hashed = digest(base64.b64encode(content) + path.suffix.lstrip(".").encode())[:32]
            files["/" + relative] = {"hash": hashed, "size": len(content)}
            by_hash[hashed] = path
    return files, by_hash


def publish_assets(cf_token, folder):
    manifest, by_hash = asset_manifest(folder)
    session = api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER}/assets-upload-session", "POST", {"manifest": manifest})
    upload_jwt = session["jwt"]
    buckets = session.get("buckets", [])
    completion = upload_jwt if not buckets else None
    for number, bucket in enumerate(buckets, start=1):
        files = {}
        for hashed in bucket:
            path = by_hash[hashed]
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith(("text/", "application/json")):
                content_type += "; charset=utf-8"
            files[hashed] = (base64.b64encode(path.read_bytes()), content_type)
        raw, content_type = multipart({}, files)
        result = api(upload_jwt, f"/accounts/{ACCOUNT_ID}/workers/assets/upload?base64=true", "POST", raw=raw, content_type=content_type)
        if result and result.get("jwt"):
            completion = result["jwt"]
        log(f"uploaded bucket {number}/{len(buckets)} ({len(bucket)} assets)")
    if not completion:
        raise RuntimeError("asset upload did not return a completion token; deployment unchanged")
    metadata = {"main_module": "worker.js", "compatibility_date": "2026-10-01",
                "assets": {"jwt": completion, "config": ASSET_CONFIG}}
    body, content_type = multipart({"metadata": metadata}, {"worker.js": (SOURCE.read_bytes(), "application/javascript+module")})
    return api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER}", "PUT", raw=body, content_type=content_type)


def resolve_health_address():
    """Use the source host's normal resolver if this desktop has stale DNS.
    curl still verifies the original hostname's HTTPS certificate."""
    command = [str(SSH), "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "UserKnownHostsFile=" + str(KNOWN_HOSTS), "-o", "ConnectTimeout=20",
               "ubuntu@129.225.197.207", "getent ahostsv4 " + HOSTNAME]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
    return str(ipaddress.IPv4Address(result.stdout.split()[0]))


def public_request(path, *, method="GET", expected=(200,)):
    global HEALTH_IP
    with tempfile.TemporaryDirectory(dir=WORK) as directory:
        body = Path(directory) / "body"
        headers = Path(directory) / "headers"
        command = ["C:\\Windows\\System32\\curl.exe", "--noproxy", "*", "--silent", "--show-error", "--max-time", "45",
                   "-X", method, "-A", "PrayerEarth-Reader-Health/1.0", "-D", str(headers), "-o", str(body),
                   "-w", "%{http_code}", f"https://{HOSTNAME}/{path}"]
        if HEALTH_IP:
            command.extend(["--resolve", f"{HOSTNAME}:443:{HEALTH_IP}"])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode and not HEALTH_IP:
            HEALTH_IP = resolve_health_address()
            command.extend(["--resolve", f"{HOSTNAME}:443:{HEALTH_IP}"])
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        try:
            status = int(result.stdout.strip()[-3:])
        except ValueError:
            raise RuntimeError("public health check did not return an HTTP status") from None
        if status not in expected:
            raise RuntimeError(f"public health check returned HTTP {status} for {path}")
        response_headers = {}
        for line in headers.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                response_headers[key.lower()] = value.strip()
        return body.read_bytes(), response_headers


def verify_public(manifest, folder, *, full=False):
    paths = ["health.json", "manifest.json", "reader/index.html", "reader/morning.html", "reader/mission.html"]
    images = [name for name in manifest["files"] if name.startswith(("assets/", "media/"))]
    details = [name for name in manifest["files"] if name.startswith("reader/") and name not in paths]
    paths.extend((images[:1] + images[-1:] + details[:1]) if not full else (images + details))
    def check_file(name):
        content, response_headers = public_request(name)
        if name in manifest["files"] and digest(content) != manifest["files"][name]:
            raise RuntimeError("public snapshot mismatch: " + name)
        if name == "health.json" and json.loads(content)["contentVersion"] != manifest["contentVersion"]:
            raise RuntimeError("public health version mismatch")
        if name == "manifest.json" and json.loads(content)["files"] != manifest["files"]:
            raise RuntimeError("public manifest mismatch")
        if "content-security-policy" not in response_headers:
            raise RuntimeError("security headers missing: " + name)
    # Resolve any desktop DNS cache issue before running parallel requests.
    check_file("health.json")
    with ThreadPoolExecutor(max_workers=6 if full else 1) as executor:
        list(executor.map(check_file, dict.fromkeys(paths)))
    for name in ("admin", "api/content", ".git/config", "reader/removed-content-test.html"):
        public_request(name, expected=(404,))
    public_request("reader/index.html", method="POST", expected=(405,))


def signature(manifest):
    # health.json and manifest generatedAt sit outside the content hashes.
    # A snapshot rebuild with the same files must not look like a new release.
    value = {"files": manifest["files"], "version": manifest["contentVersion"], "worker": digest(SOURCE.read_bytes()),
             "config": ASSET_CONFIG, "account": ACCOUNT_ID, "target": WORKER, "hostname": HOSTNAME}
    return digest(json.dumps(value, sort_keys=True).encode())


_KEEP_DEPLOYMENT_ID = object()


def publish_state(previous, manifest, current_signature, *, deployment_id=_KEEP_DEPLOYMENT_ID):
    """State recorded after a successful public verification.

    A no-deploy run refreshes verifiedAt and keeps deploymentId (and any
    extra fields). A real deploy passes deployment_id to replace it.
    """
    state = dict(previous)
    state["signature"] = current_signature
    state["contentVersion"] = manifest["contentVersion"]
    state["counts"] = manifest["counts"]
    state["verifiedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["hostname"] = HOSTNAME
    if deployment_id is not _KEEP_DEPLOYMENT_ID:
        state["deploymentId"] = deployment_id
    return state


def write_publish_state(state_file, state):
    temporary = state_file.with_suffix(".new")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_file)


def bind_domain(cf_token):
    domains = api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/domains")
    existing = next((item for item in domains if item["hostname"] == HOSTNAME), None)
    if existing:
        if existing["service"] != WORKER:
            raise RuntimeError("reader hostname already belongs to another Worker")
        return
    records = api(cf_token, f"/zones/{ZONE_ID}/dns_records?name={HOSTNAME}")
    if records:
        raise RuntimeError("reader hostname already has DNS records; refusing to replace them")
    api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/domains", "PUT",
        {"zone_id": ZONE_ID, "hostname": HOSTNAME, "service": WORKER, "environment": "production"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-directory", type=Path, help="publish an existing validated snapshot instead of SSH pull")
    parser.add_argument("--token-file", type=Path, default=TOKEN_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--full-verify", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    folder = (args.snapshot_directory or WORK / "snapshot").resolve()
    manifest = validate_snapshot(folder) if args.snapshot_directory else pull_snapshot(folder)
    state_file = WORK / "state.json"
    previous = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    current_signature = signature(manifest)
    log(f'snapshot validated: version {manifest["contentVersion"]}, {manifest["counts"]["all"]} items, {len(manifest["files"])} files')
    if args.dry_run:
        log("dry run: no Cloudflare changes")
        return 0
    # generatedAt advances on every OCI snapshot rebuild, but it is not part of
    # signature(). Redeploying whenever the local stamp is newer would publish
    # every 15 minutes. Public generatedAt stays the last content publish;
    # liveness is verifiedAt below, including this no-deploy path.
    if args.verify_only or (not args.force and previous.get("signature") == current_signature):
        verify_public(manifest, folder, full=args.full_verify)
        if previous.get("signature") == current_signature:
            write_publish_state(state_file, publish_state(previous, manifest, current_signature))
            log("publisher state verifiedAt refreshed")
        log("public snapshot verified; no deployment needed")
        return 0
    cf_token = read_token(args.token_file)
    # Save the prior deployment record so a release can be explicitly rolled
    # back if post-deploy checks fail. Never treat a lost PUT reply as rollback.
    try:
        prior = api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER}/deployments")
    except RuntimeError as error:
        if "HTTP 404" not in str(error):
            raise
        prior = None
    (WORK / "previous-deployment.json").write_text(json.dumps(prior, indent=2), encoding="utf-8")
    result = publish_assets(cf_token, folder)
    bind_domain(cf_token)
    # Disable public version previews and workers.dev; the fixed custom domain
    # is the only published entry, including after content is archived.
    api(cf_token, f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER}/subdomain", "POST",
        {"enabled": False, "previews_enabled": False})
    for attempt in range(10):
        try:
            verify_public(manifest, folder, full=args.full_verify)
            break
        except (OSError, RuntimeError):
            if attempt == 9:
                raise
            time.sleep(5)
    write_publish_state(state_file, publish_state(
        previous, manifest, current_signature, deployment_id=result.get("deployment_id")))
    log(f"deployed and verified https://{HOSTNAME}")
    return 0


if __name__ == "__main__":
    try:
        with publisher_lock():
            raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        log("FAILED: " + str(error))
        raise SystemExit(1)
