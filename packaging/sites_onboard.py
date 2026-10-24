"""Add first-run answers to sites.txt under [distracting] / [ok]. Never clobbers: creates from the
rules.TEMPLATE only when missing, keeps comments, skips entries already present.

usage: python sites_onboard.py SITES_PATH BLOCK_CSV ALLOW_CSV   (run with cwd = the app dir)
"""

import re
import sys
from pathlib import Path

import rules


def clean(csv: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[,\n]", csv):
        # '#' would start a comment and '[' could fake a section header in the rules file.
        term = re.sub(r"[#\[\]]", "", part).strip().lower()[:100]
        if term and term not in out:
            out.append(term)
    return out


def insert(lines: list[str], section: str, terms: list[str]) -> list[str]:
    header = f"[{section}]"
    if header not in (ln.strip().lower() for ln in lines):
        lines = lines + ["", header]
    start = next(i for i, ln in enumerate(lines) if ln.strip().lower() == header)
    end = next(
        (i for i in range(start + 1, len(lines)) if re.fullmatch(r"\[\w+\]", lines[i].strip().lower())), len(lines)
    )
    existing = set(rules.parse("\n".join([header] + lines[start + 1 : end]))[section])
    new = [t for t in terms if t not in existing]
    at = end
    while at > start + 1 and not lines[at - 1].strip():
        at -= 1  # keep the blank line that separates sections
    return lines[:at] + new + lines[at:]


def main() -> None:
    path, block, allow = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rules.TEMPLATE)
    lines = path.read_text(errors="replace").splitlines()
    lines = insert(lines, "distracting", clean(block))
    lines = insert(lines, "ok", clean(allow))
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)  # atomic: the coach may be reading it live
    r = rules.parse(path.read_text())
    print(f"sites: distracting={r['distracting']} ok={r['ok']}")


if __name__ == "__main__":
    main()
