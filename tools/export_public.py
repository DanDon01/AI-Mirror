"""Export this checkout as a clean public tree, and refuse if anything leaks.

Copies the tracked files (as they are in the working tree) to DEST, leaving
out anything that belongs to one home, then scans every exported file for:

  - secret VALUES from Variables.env (and, with --secrets-from-commit, from an
    env file in an old commit) - compared exactly, never printed
  - credential shapes: OpenAI/GitHub/Google/Slack keys, JWTs, private keys
  - private IPv4 addresses and personal email addresses
  - image metadata (EXIF/XMP: author names, camera details, GPS)
  - every term in the house pack's export_deny.txt (one per line; names,
    places, account numbers - whatever must never be published)

and runs gitleaks too if it is installed. Exit code 1 on any finding; the
report names files and variables only.

    python tools/export_public.py ../AI-Mirror-public
    python tools/export_public.py ../AI-Mirror-public --secrets-from-commit <sha>
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from house_pack import house_path  # noqa: E402

# Never exported, even if tracked by mistake.
EXCLUDE = ["house/*", "house.local/*", "CLAUDE.local.md", "Variables.env", "*.env",
           "data/*", "*.log", "api_tracker_state.json"]
# Third-party code and licences: checked for secret values, not for patterns.
VENDOR = ["prototype/visual-gate/assets/vendor/*", "*.min.js", "assets/fonts/*"]

PATTERNS = {
    "OpenAI-style key": r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}",
    "Google API key": r"AIza[0-9A-Za-z_-]{35}",
    "Slack token": r"xox[abpr]-[A-Za-z0-9-]{10,}",
    "JWT / bearer token": r"eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "private IPv4": r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "email address": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
}
ALLOWED_EMAIL = re.compile(r"(@users\.noreply\.github\.com|@example\.(com|org)|noreply@anthropic\.com)$", re.I)
TRIVIAL = {"true", "false", "none", "null", "auto", "minimal"}
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic", ".gif")
IMAGE_METADATA = (b"xmpmeta", b"Exif\x00\x00", b"EXIF", b"XMP ", b"pdf:Author", b"dc:creator")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if len(value) >= 8 and value.lower() not in TRIVIAL:
            values[key.strip()] = value
    return values


def secret_values(commit: str | None) -> dict[str, str]:
    secrets = {}
    env = ROOT.parent / "Variables.env"
    if env.is_file():
        secrets.update({f"Variables.env:{k}": v for k, v in parse_env(env.read_text("utf-8", "replace")).items()})
    if commit:
        for name in subprocess.run(["git", "show", "--name-only", "--format=", commit], cwd=ROOT,
                                   capture_output=True, text=True).stdout.split():
            if name.endswith(".env") or name.endswith("Variables.env"):
                text = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=ROOT,
                                      capture_output=True, text=True).stdout
                secrets.update({f"{commit}:{name}:{k}": v for k, v in parse_env(text).items()})
    return secrets


def deny_terms() -> list[str]:
    path = house_path("export_deny.txt")
    if not path.is_file():
        return []
    return [t.strip() for t in path.read_text("utf-8").splitlines() if t.strip() and not t.startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest", help="empty or missing directory to export into")
    ap.add_argument("--secrets-from-commit", help="also check values from an env file in this old commit")
    args = ap.parse_args()

    dest = Path(args.dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        print(f"refusing: {dest} is not empty")
        return 2
    if str(dest).startswith(str(ROOT) + os.sep):
        print("refusing: the export must be outside this checkout")
        return 2

    files = [p for p in tracked() if not matches(p, EXCLUDE) and (ROOT / p).is_file()]
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print(f"exported {len(files)} files to {dest}")
    # Windows checkouts do not carry the executable bit into a new repo, and
    # the Pi's service fails if run.sh is not executable. Say which to restore.
    stage = subprocess.run(["git", "ls-files", "-s"], cwd=ROOT, capture_output=True, text=True).stdout
    executable = [line.split("\t", 1)[1] for line in stage.splitlines()
                  if line.startswith("100755") and line.split("\t", 1)[1] in files]
    if executable:
        print("after git init + add, keep these executable:\n  git update-index --chmod=+x " + " ".join(executable))

    secrets = secret_values(args.secrets_from_commit)
    terms = deny_terms()
    compiled = {name: re.compile(rx) for name, rx in PATTERNS.items()}
    findings = []
    for rel in files:
        data = (dest / rel).read_bytes()
        for label, value in secrets.items():
            if value.encode("utf-8") in data:
                findings.append(f"{rel}: contains the value of {label}")
        # Images carry metadata a text scan never sees: author names, camera
        # serials, GPS. Strip it (losslessly) before publishing.
        if rel.lower().endswith(IMAGES) and any(marker in data for marker in IMAGE_METADATA):
            findings.append(f"{rel}: image metadata (EXIF/XMP) - strip it before publishing")
        text = data.decode("utf-8", "replace")
        lower = text.lower()
        for term in terms:
            if term.lower() in lower:
                findings.append(f"{rel}: contains a denied term (line {terms.index(term) + 1} of export_deny.txt)")
        if matches(rel, VENDOR) or b"\0" in data[:4096]:
            continue
        for name, rx in compiled.items():
            for m in rx.finditer(text):
                if name == "email address" and ALLOWED_EMAIL.search(m.group(0)):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{rel}:{line}: {name}")

    print(f"checked {len(secrets)} secret values, {len(terms)} denied terms, {len(PATTERNS)} patterns")
    if shutil.which("gitleaks"):
        r = subprocess.run(["gitleaks", "detect", "--no-git", "--source", str(dest), "--redact"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            findings.append("gitleaks reported findings (run: gitleaks detect --no-git --redact --source DEST)")
        else:
            print("gitleaks: clean")
    else:
        print("gitleaks: not installed (skipped)")

    if findings:
        print(f"\n{len(findings)} finding(s) - do NOT publish:")
        for f in findings:
            print("  " + f)
        return 1
    print("\nclean: nothing found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
