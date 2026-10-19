"""Pattern scan of src/sazon/web/ for things the panel must never contain.

This is NOT a security audit: it is a line-by-line regex check. It misses
obfuscated code, URLs built at runtime, remote loads outside src/href (fetch,
CSS url(), import), and every vulnerability that is not one of these patterns.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "sazon" / "web"

# URL prefixes the panel may load from. Empty: our own app serves every asset.
ALLOWED_REMOTE: tuple[str, ...] = ()

REMOTE = re.compile(r"""\b(?:src|href)\s*=\s*["']?((?:https?:)?//[^"'\s>]+)""", re.I)
BANNED = {
    "eval() runs strings as code": re.compile(r"\beval\s*\("),
    "new Function() runs strings as code": re.compile(r"\bnew\s+Function\s*\("),
    "web storage keeps candidate data in the browser": re.compile(
        r"\b(?:localStorage|sessionStorage)\b"
    ),
    "document.cookie is readable by any script": re.compile(r"\bdocument\.cookie\b"),
}


def test_web_has_no_banned_patterns() -> None:
    findings: list[str] = []
    for path in sorted(p for p in WEB.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            where = f"{path.relative_to(ROOT)}:{lineno}"
            findings += [
                f"{where}: remote resource {url}"
                for url in REMOTE.findall(line)
                if not url.startswith(ALLOWED_REMOTE)
            ]
            findings += [
                f"{where}: {reason}"
                for reason, pattern in BANNED.items()
                if pattern.search(line)
            ]
    assert not findings, "\n".join(findings)
