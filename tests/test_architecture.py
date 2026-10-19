"""Module boundaries, checked with ast. Rules for modules not created yet skip."""

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "sazon"

# module -> sibling modules it must not import
FORBIDDEN_IMPORTS = {
    "llm": {"engine", "storage", "api"},  # the LLM drafts and extracts, never decides
    "api": {"llm"},  # api reaches the LLM only through engine
}

# Literal aliases in schema.py that label messages, not business values; their
# values are everyday words ("question", "es") a prompt may use freely.
LABEL_ALIASES = {"Intent", "Language"}
# Catch-all enum value with no rule behind it.
COMMON_WORDS = {"other"}


def imports(path: Path) -> set[str]:
    """Dotted names a file imports; `from x import y` yields both x and x.y."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # shortcut: relative imports resolve against the flat sazon package,
            # revisit if subpackages appear
            parts = ["sazon" if node.level else "", node.module or ""]
            base = ".".join(filter(None, parts))
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def imports_module(names: set[str], module: str) -> bool:
    return any(n == module or n.startswith(f"{module}.") for n in names)


def strings(tree: ast.AST) -> list[str]:
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def literal_values(path: Path, skip: set[str]) -> set[str]:
    """String values inside every Literal[...] in a file, except top-level aliases
    named in skip."""
    kept = [
        stmt
        for stmt in ast.parse(path.read_text(encoding="utf-8")).body
        if not (isinstance(stmt, ast.Assign) and ast.unparse(stmt.targets[0]) in skip)
    ]
    values: set[str] = set()
    for node in (n for stmt in kept for n in ast.walk(stmt)):
        if isinstance(node, ast.Subscript) and ast.unparse(node.value).endswith(
            "Literal"
        ):
            values.update(strings(node.slice))
    return values


@pytest.mark.parametrize(("module", "forbidden"), FORBIDDEN_IMPORTS.items())
def test_import_boundaries(module: str, forbidden: set[str]) -> None:
    path = PKG / f"{module}.py"
    if not path.exists():
        pytest.skip(f"{module}.py does not exist yet")
    names = imports(path)
    leaks = sorted(f for f in forbidden if imports_module(names, f"sazon.{f}"))
    assert not leaks, f"{module}.py must not import {leaks}"


def test_web_is_not_imported_from_python() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in [*PKG.rglob("*.py"), *(ROOT / "tests").rglob("*.py")]
        if imports_module(imports(p), "sazon.web")
    ]
    assert not offenders, f"web/ is static assets, not Python: {offenders}"


def test_prompts_hold_no_business_values() -> None:
    prompts = PKG / "prompts.py"
    if not prompts.exists():
        pytest.skip("prompts.py does not exist yet")
    banned: set[str] = set()
    zones = ROOT / "config" / "zones.toml"
    if zones.exists():
        banned.update(tomllib.loads(zones.read_text(encoding="utf-8"))["zones"])
    if (PKG / "schema.py").exists():
        banned.update(literal_values(PKG / "schema.py", LABEL_ALIASES))
    banned -= COMMON_WORDS
    texts = strings(ast.parse(prompts.read_text(encoding="utf-8")))
    # shortcut: whole-word match, so a value that is also a common word
    # ("flexible") can false-positive; then match on schema identifiers instead
    # "_" matches a space, hyphen or nothing: "Uber Eats", "part-time", "fulltime"
    patterns = {v: re.escape(v).replace("_", r"[_\s-]*") for v in banned}
    leaks = sorted(
        v
        for v, p in patterns.items()
        if any(re.search(rf"\b{p}\b", t, re.IGNORECASE) for t in texts)
    )
    assert not leaks, f"prompts.py hardcodes values, inject from schema/config: {leaks}"
