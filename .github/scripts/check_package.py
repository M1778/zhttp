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

"""Build a throwaway `finn` consumer against this checkout of the library.

Why a script: the step has to write a manifest whose `zhttp` path is this
repository's absolute location, and doing that from YAML means a heredoc inside
a block scalar. A heredoc body starting at column 0 ends the YAML scalar, and
indenting it puts leading spaces into the generated `finn.toml`. A file with one
clear job avoids both, and it is testable locally.

It answers one question -- can a `finn` project import `zhttp::fin` the way the
README says -- which `finc -I src` cannot, because that bypasses the package
layout the package manager actually uses.

    python3 .github/scripts/check_package.py
    python3 .github/scripts/check_package.py --repo-root .
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CONSUMER = Path(".github/consumer")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    args = ap.parse_args()

    root = args.repo_root.resolve()
    source = root / CONSUMER / "main.fin"
    if not source.exists():
        print(f"error: {source} is missing", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="zhttp-consumer-") as tmp:
        project = Path(tmp)
        (project / "src").mkdir()
        shutil.copy2(source, project / "src" / "main.fin")

        # A path with spaces would still be legal TOML in double quotes, but the
        # repository path is not escaped for anything else, so check it early
        # rather than produce a confusing parse error.
        manifest = (
            "[project]\n"
            'name = "consumer"\n'
            'version = "0.1.0"\n'
            'envpath = ".finn"\n'
            'entrypoint = "main.fin"\n'
            "\n"
            "[packages]\n"
            f'zhttp = "{root.as_posix()}"\n'
            "\n"
            "[scripts]\n"
        )
        (project / "finn.toml").write_text(manifest, encoding="utf-8")

        env = dict(os.environ)
        finc = shutil.which("finc")
        if finc:
            env["FIN_COMPILER_PATH"] = finc

        for command in (["finn", "sync"], ["finn", "build"]):
            print(f"== {' '.join(command)}")
            result = subprocess.run(command, cwd=project, env=env)
            if result.returncode != 0:
                print(f"error: {' '.join(command)} failed", file=sys.stderr)
                return result.returncode

        binary = project / "out" / "consumer"
        if not binary.exists():
            binary = project / "out" / "consumer.exe"
        if not binary.exists():
            print(f"error: no consumer binary under {project / 'out'}", file=sys.stderr)
            return 1

        output = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
        print(f"consumer printed: {output.stdout.strip()!r}")
        expected = "Created 201 made"
        if expected not in output.stdout:
            print(f"error: expected {expected!r} in the consumer's output", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
