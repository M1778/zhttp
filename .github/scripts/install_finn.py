#!/usr/bin/env python3
# =============================================================================
# Fin Programming Language
#
# Made with ❤️ for someone special.
#
# This project is genuinely built on love and dedication, a way to express your love can be done through Fin.
# Fin is a semi-object-orientated programming language that specialized in control, giving so much control to the user while asking for the bare minimum.
# Fin is the name of the Angel from BlackNightmare-Stories not yet published.
# “Love is the reason this project exists”
# -----------------------------------------------------------------------------
# Author: M1778
# Repository: https://github.com/M1778/zhttp
# Profile: https://github.com/M1778M/
# -----------------------------------------------------------------------------
# Copyright (C) 2027 M1778
#
# This file is part of zhttp, a project for the Fin Programming Language.
#
# Licensed under the MIT License. See LICENSE in the repository root.
#
# SPDX-License-Identifier: MIT
# =============================================================================

"""Install the pinned `finn` package manager release, verifying its checksum.

`finn` is needed by one CI step: proving that `import ... from zhttp::fin`
resolves for a real consumer. That is the packaging contract, and a broken
package layout is invisible to `finc -I src`.

The release publishes a `.sha256` beside every archive and no index file, so
the checksum is read from that sibling rather than from a pinned copy here --
there is nothing to pin it against, and a stale local copy would be worse than
the publisher's own. If the release ever stops publishing the `.sha256`, this
refuses instead of installing unverified bytes.

    python3 .github/scripts/install_finn.py
    python3 .github/scripts/install_finn.py --version 1.0.1 --dest ~/.finn-bin
"""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "M1778/finn"


def asset_stem() -> str:
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(machine)
    if arch is None:
        print(f"error: unsupported machine {machine!r}", file=sys.stderr)
        sys.exit(1)
    if sys.platform.startswith("linux"):
        return f"finn-linux-{arch}"
    if sys.platform == "darwin":
        return f"finn-macos-{arch}"
    if sys.platform == "win32":
        return f"finn-windows-{arch}"
    print(f"error: unsupported platform {sys.platform!r}", file=sys.stderr)
    sys.exit(1)


def add_to_path(path: Path) -> None:
    """Put `path` on PATH for the following steps (see install_finc.py)."""
    print(f"installed into {path}")
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with open(github_path, "a", encoding="utf-8") as handle:
            handle.write(f"{path}\n")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fin-ci-installer"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.1")
    ap.add_argument("--dest", type=Path, default=Path(".finn-bin"))
    args = ap.parse_args()
    version = args.version.lstrip("v")

    stem = asset_stem()
    suffix = ".zip" if sys.platform == "win32" else ".tar.gz"
    base = f"https://github.com/{REPO}/releases/download/v{version}/{stem}{suffix}"

    print(f"downloading {base}")
    payload = fetch(base)
    try:
        published = fetch(base + ".sha256").decode().split()[0].strip().lower()
    except Exception as exc:  # noqa: BLE001 - any failure here must refuse
        print(f"error: no published sha256 for {base}: {exc}", file=sys.stderr)
        return 1
    got = hashlib.sha256(payload).hexdigest()
    if got != published:
        print(f"error: checksum mismatch\n  published: {published}\n  download:  {got}", file=sys.stderr)
        return 1
    print(f"sha256 ok ({len(payload)} bytes)")

    dest = args.dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f"finn{suffix}"
        archive.write_bytes(payload)
        if suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)
        else:
            with tarfile.open(archive) as tf:
                # `filter` exists from 3.12; on older interpreters the argument
                # is absent, so fall back to the plain call.
                try:
                    tf.extractall(dest, filter="data")
                except TypeError:
                    tf.extractall(dest)

    binary = dest / ("finn.exe" if sys.platform == "win32" else "finn")
    if not binary.exists():
        found = sorted(p.name for p in dest.rglob("finn*"))
        print(f"error: expected {binary}, found {found}", file=sys.stderr)
        return 1
    if sys.platform != "win32":
        binary.chmod(0o755)

    out = subprocess.run([str(binary), "--version"], capture_output=True, text=True)
    if out.returncode != 0 or "finn" not in out.stdout:
        print(f"error: installed finn does not answer --version: {out.stdout}{out.stderr}", file=sys.stderr)
        return 1
    print(f"installed: {out.stdout.strip()}")
    add_to_path(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
