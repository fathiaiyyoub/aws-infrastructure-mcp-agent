"""Offline manifest/secret-pattern check; reports locations, never matched values.

A focused safety net, not an exhaustive credential or history scanner.
Use a dedicated secret scanner as well when available.
"""
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLICATION_MANIFEST.txt"
PATTERNS = {
    "AWS access key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "OpenAI key": r"\bsk-[A-Za-z0-9_-]{16,}\b",
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    "private key": r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----",
    "certificate": r"-----BEGIN " + r"CERTIFICATE-----",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "credential URL": r"(?i)(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@",
    "authentication header": r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9_./+=-]{16,}",
    "AWS account identifier": r"\b\d{12}\b",
    "personal machine path": r"(?i)(?:[a-z]:[\\/]Users[\\/](?!<|\[)|/ho" r"me/(?!<)|/Us" r"ers/(?!<))",
}
ASSIGNMENT = re.compile(
    r'''(?i)["']?[\w-]*(?:password|secret|token|api_key|access_key|authorization)[\w-]*["']?\s*[:=]\s*["']([^"'\r\n]+)["']'''
)
ENV_ASSIGNMENT = re.compile(r"(?i)^(?:[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|SECRET_KEY|TOKEN|API_KEY|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN))\s*=\s*(.+)$")


def placeholder(value):
    lower = value.lower()
    return (not value or any(word in lower for word in
            ("fixture", "synthetic", "replace-with", "[redacted]", "example.invalid"))
            or value.startswith(("$" + "{", "$env:", "<", "os.environ", "os.getenv")))


def scan_text(text):
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in PATTERNS.items():
            for match in re.finditer(pattern, line):
                if label in ("credential URL", "authentication header") and placeholder(match.group()):
                    continue
                findings.append((number, label))
        for match in ASSIGNMENT.finditer(line):
            if not placeholder(match.group(1)):
                findings.append((number, "credential-like literal; review required"))
        match = ENV_ASSIGNMENT.match(line)
        if match and not placeholder(match.group(1)):
            findings.append((number, "non-placeholder credential environment assignment"))
    return findings


def prohibited(name):
    parts = Path(name).parts
    base = Path(name).name.lower()
    return (any(p in {".git", ".aws", ".venv", "venv", ".terraform", ".security-review",
                      "__pycache__", "logs", "reports", "build", "dist"} for p in parts)
            or (base.startswith(".env") and base != ".env.example")
            or ".tfstate" in base or base == "tfplan" or base.startswith("tfplan.")
            or base.endswith((".tfplan", ".plan", ".tfvars", ".tfvars.json", ".log", ".pyc", ".pem", ".key", ".pfx", ".p12")))


def main():
    names = [line.strip() for line in MANIFEST.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    failures = 0
    if len(names) != len(set(names)):
        print("Manifest contains duplicate paths")
        failures += 1
    for name in names:
        file = ROOT / name
        try:
            valid = (not Path(name).is_absolute() and ".." not in Path(name).parts
                     and not prohibited(name) and file.is_file()
                     and file.resolve().is_relative_to(ROOT)
                     and not any(p.is_symlink() or bool(getattr(p.lstat(), "st_file_attributes", 0)
                                 & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
                                 for p in [file, *list(file.parents)[:len(Path(name).parts) - 1]]))
            if not valid:
                print(f"{name}: prohibited, missing, or linked publication file")
                failures += 1
                continue
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            print(f"{name}: unreadable or non-text publication file; manual review required")
            failures += 1
            continue
        for line, kind in scan_text(text):
            print(f"{name}:{line}: {kind}")
            failures += 1
    print(f"Checked {len(names)} manifest files; {failures} findings requiring review.")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
