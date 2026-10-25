"""The built app must ship every local module its entry points import: a missing one crashes on first start."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
# What the launcher runs from Contents/Resources/app: the coach, the session summary, the site onboarding.
ENTRY_POINTS = [ROOT / "apex.py", ROOT / "report.py", PKG / "sites_onboard.py"]


def imported_names(path: Path) -> set[str]:
    """Top-level names of every import in the file, including ones inside functions (apex.py imports lazily)."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def local_closure(entries: list[Path]) -> set[str]:
    """File names of the entry points plus every repo-root module they reach, transitively."""
    seen, todo = set(), list(entries)
    while todo:
        path = todo.pop()
        if path.name in seen:
            continue
        seen.add(path.name)
        todo += [ROOT / f"{n}.py" for n in imported_names(path) if (ROOT / f"{n}.py").is_file()]
    return seen


def shipped_modules(script: str) -> set[str]:
    """The .py files build_app.sh copies into Contents/Resources/app."""
    loops = re.findall(r"^for f in ([^;]*\.py[^;]*); do", script, re.M)
    assert len(loops) == 1, f"expected one `for f in *.py` copy loop in build_app.sh, found {len(loops)}"
    single = re.findall(r'^cp "\$PKG/(\w+\.py)" "\$APP/Contents/Resources/app/"', script, re.M)
    return set(loops[0].split()) | set(single)


def test_build_ships_every_local_module_the_app_imports():
    shipped = shipped_modules((PKG / "build_app.sh").read_text())
    missing = local_closure(ENTRY_POINTS) - shipped
    assert not missing, f"build_app.sh does not copy {sorted(missing)}; the packaged app would crash importing them"


def test_closure_follows_lazy_and_transitive_imports():
    # Guards the walker itself: apex.py imports control/gemma inside functions; sites_onboard.py reaches rules.
    reached = local_closure(ENTRY_POINTS)
    assert {"apex.py", "control.py", "gemma.py", "personas.py", "rules.py", "report.py"} <= reached

