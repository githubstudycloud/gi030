#!/usr/bin/env python3
"""offline-bundle — pack pip wheels and arbitrary URLs into a verifiable bundle.

Workflow:
    On the *online* machine (procurement proxy)::

        python bundle.py pack \
            --pip-requirements requirements.txt \
            --url https://get.scoop.sh \
            --urls-file extra-urls.txt \
            --out ./bundle

    Transfer ``./bundle`` to the offline machine (USB / share / whatever).

    On the *offline* machine::

        python bundle.py verify --bundle ./bundle
        python bundle.py install --bundle ./bundle --pip-requirements requirements.txt

Stdlib only. Uses the ambient ``pip``/``uv`` (whichever is present) for the
``pack``-pip and ``install`` steps. Tested on Python 3.10+.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = "1"
WHEEL_DIR = "wheels"
FILES_DIR = "files"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def utcnow_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def pick_pip_runner() -> list[str]:
    """Return the argv prefix for invoking pip-equivalent.

    Prefers ``uv pip`` (much faster, identical CLI surface for our needs);
    falls back to ``python -m pip``.
    """
    if which("uv"):
        return ["uv", "pip"]
    return [sys.executable, "-m", "pip"]


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("$", " ".join(argv), flush=True)
    return subprocess.run(argv, check=True, **kwargs)


def safe_url_basename(url: str) -> str:
    """Pick a filename for a URL download. Falls back to a hash if URL has no path."""
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if not name:
        name = hashlib.sha256(url.encode()).hexdigest()[:16] + ".bin"
    return name


def download_url(url: str, dest: Path) -> None:
    print(f"GET {url} -> {dest.name}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "offline-bundle/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------
@dataclass
class Manifest:
    version: str = MANIFEST_VERSION
    created: str = field(default_factory=utcnow_iso)
    source: dict = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)

    def add(self, rel_path: str, sha256: str, size: int, kind: str, origin: str | None = None) -> None:
        entry = {"path": rel_path, "sha256": sha256, "size": size, "kind": kind}
        if origin:
            entry["origin"] = origin
        self.items.append(entry)

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "created": self.created,
                "source": self.source,
                "items": sorted(self.items, key=lambda x: x["path"]),
            },
            indent=2,
            sort_keys=False,
        )


def pack(args: argparse.Namespace) -> int:
    out: Path = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        if not args.force:
            print(f"refusing to write into non-empty directory: {out}", file=sys.stderr)
            print("pass --force to overwrite", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    wheels = out / WHEEL_DIR
    files = out / FILES_DIR
    wheels.mkdir(exist_ok=True)
    files.mkdir(exist_ok=True)

    manifest = Manifest(
        source={
            "host_python": sys.version.split()[0],
            "host_platform": sys.platform,
            "target_platform": args.platform,
            "target_python_version": args.python_version,
            "pip_requirements": [str(p) for p in (args.pip_requirements or [])],
            "urls": list(args.urls or []),
            "urls_file": str(args.urls_file) if args.urls_file else None,
        },
    )

    # 1) pip download
    if args.pip_requirements:
        pip = pick_pip_runner()
        cmd = pip + ["download", "-d", str(wheels), "--only-binary=:all:"]
        if args.platform:
            cmd += ["--platform", args.platform]
        if args.python_version:
            cmd += ["--python-version", args.python_version]
        for r in args.pip_requirements:
            cmd += ["-r", str(r)]
        try:
            run(cmd)
        except subprocess.CalledProcessError as e:
            print(f"pip download failed (exit {e.returncode})", file=sys.stderr)
            return e.returncode

    # 2) URLs (CLI + file)
    url_list: list[str] = list(args.urls or [])
    if args.urls_file:
        # utf-8-sig tolerates a leading BOM (PowerShell's `Out-File -Encoding utf8` writes one)
        for line in Path(args.urls_file).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip().lstrip("﻿")
            if line and not line.startswith("#"):
                url_list.append(line)
    for url in url_list:
        name = safe_url_basename(url)
        dest = files / name
        # avoid clobbering: prefix counter if duplicate
        i = 1
        while dest.exists():
            dest = files / f"{i:02d}-{name}"
            i += 1
        try:
            download_url(url, dest)
        except Exception as e:
            print(f"download failed for {url}: {e}", file=sys.stderr)
            return 3
        manifest.add(
            rel_path=f"{FILES_DIR}/{dest.name}",
            sha256=sha256_of(dest),
            size=dest.stat().st_size,
            kind="url",
            origin=url,
        )

    # 3) hash everything pip dropped
    for w in sorted(wheels.iterdir()):
        if w.is_file():
            manifest.add(
                rel_path=f"{WHEEL_DIR}/{w.name}",
                sha256=sha256_of(w),
                size=w.stat().st_size,
                kind="wheel",
            )

    # 4) write manifest
    (out / MANIFEST_NAME).write_text(manifest.to_json(), encoding="utf-8")
    print(f"\nbundle ready: {out}")
    print(f"  items: {len(manifest.items)}")
    print(f"  manifest: {out / MANIFEST_NAME}")
    return 0


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
def verify(args: argparse.Namespace) -> int:
    bundle: Path = args.bundle.resolve()
    mpath = bundle / MANIFEST_NAME
    if not mpath.is_file():
        print(f"no manifest at {mpath}", file=sys.stderr)
        return 2

    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("version") != MANIFEST_VERSION:
        print(f"warning: manifest version {manifest.get('version')} != {MANIFEST_VERSION}", file=sys.stderr)

    bad: list[str] = []
    missing: list[str] = []
    extra: list[str] = []

    declared = {item["path"]: item for item in manifest["items"]}
    for rel, item in declared.items():
        p = bundle / rel
        if not p.is_file():
            missing.append(rel)
            continue
        got = sha256_of(p)
        if got != item["sha256"]:
            bad.append(f"{rel}: expected {item['sha256']} got {got}")

    # detect extras
    for sub in (WHEEL_DIR, FILES_DIR):
        d = bundle / sub
        if d.is_dir():
            for f in d.iterdir():
                rel = f"{sub}/{f.name}"
                if f.is_file() and rel not in declared:
                    extra.append(rel)

    ok = not (bad or missing)
    print(f"verified: {len(declared)} items declared")
    print(f"  matched : {len(declared) - len(bad) - len(missing)}")
    print(f"  bad     : {len(bad)}")
    print(f"  missing : {len(missing)}")
    print(f"  extras  : {len(extra)}")
    for b in bad:
        print(f"  ! {b}")
    for m in missing:
        print(f"  ? missing: {m}")
    for e in extra:
        print(f"  + extra  : {e}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Install (convenience wrapper around offline pip install)
# ---------------------------------------------------------------------------
def install(args: argparse.Namespace) -> int:
    bundle: Path = args.bundle.resolve()
    wheels = bundle / WHEEL_DIR
    if not wheels.is_dir():
        print(f"no wheels dir at {wheels}", file=sys.stderr)
        return 2

    if args.verify_first:
        rc = verify(argparse.Namespace(bundle=bundle))
        if rc != 0:
            print("aborting install: verification failed", file=sys.stderr)
            return rc

    pip = pick_pip_runner()
    cmd = pip + ["install", "--no-index", "--find-links", str(wheels)]
    if args.target:
        cmd += ["--target", str(args.target)]
    if args.require_hashes:
        cmd += ["--require-hashes"]
    if args.pip_requirements:
        for r in args.pip_requirements:
            cmd += ["-r", str(r)]
    elif args.packages:
        cmd += list(args.packages)
    else:
        print("nothing to install: pass --pip-requirements or packages", file=sys.stderr)
        return 2

    try:
        run(cmd)
    except subprocess.CalledProcessError as e:
        return e.returncode
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bundle", description="Pack/verify offline bundles.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pack", help="Build a bundle on an online machine.")
    pp.add_argument("--out", type=Path, required=True, help="Output directory")
    pp.add_argument("--pip-requirements", "-r", type=Path, action="append",
                    help="pip requirements file (repeatable)")
    pp.add_argument("--url", "-u", dest="urls", action="append", help="Extra URL to fetch (repeatable)")
    pp.add_argument("--urls-file", type=Path, help="File with one URL per line")
    pp.add_argument("--platform", default=None,
                    help="Target platform tag for wheels, e.g. win_amd64 / manylinux2014_x86_64")
    pp.add_argument("--python-version", default=None, help="Target Python version, e.g. 3.12")
    pp.add_argument("--force", action="store_true", help="Overwrite existing bundle dir")
    pp.set_defaults(func=pack)

    pv = sub.add_parser("verify", help="Verify SHA-256 of every item in a bundle.")
    pv.add_argument("--bundle", type=Path, required=True)
    pv.set_defaults(func=verify)

    pi = sub.add_parser("install", help="Install pip packages from a bundle.")
    pi.add_argument("--bundle", type=Path, required=True)
    pi.add_argument("--pip-requirements", "-r", type=Path, action="append")
    pi.add_argument("packages", nargs="*", help="Or just package names")
    pi.add_argument("--target", type=Path, help="Install into this directory (e.g. .venv site-packages)")
    pi.add_argument("--require-hashes", action="store_true",
                    help="Force --require-hashes (requirements file must contain hashes)")
    pi.add_argument("--verify-first", action="store_true", help="Run verify before installing")
    pi.set_defaults(func=install)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
