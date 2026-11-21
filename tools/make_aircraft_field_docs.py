"""Regenerate the field tables in docs/aircraft_data.md from the configuration model.

    python tools/make_aircraft_field_docs.py

Everything between the BEGIN/END markers in docs/aircraft_data.md is replaced; the
text around it is hand-written. tests/test_app.py checks that every field is listed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.builder import FIELDS, GROUP_TITLES  # noqa: E402

DOC = ROOT / "docs" / "aircraft_data.md"
BEGIN, END = "<!-- BEGIN FIELDS (generated) -->", "<!-- END FIELDS -->"


def _default(f: dict) -> str:
    if f["required"]:
        return "**required**"
    v = f["default"]
    if v in (None, "", {}, []):
        return "–"
    return f"`{v}`"


def tables() -> str:
    out = []
    groups: dict[str, list[dict]] = {}
    for f in FIELDS:
        groups.setdefault(f["group"], []).append(f)
    for g, fields in groups.items():
        title = GROUP_TITLES.get(g, g)
        out.append(f"#### {title}" + (f" (`{g}:`)" if g else ""))
        out.append("")
        out.append("| field | default | meaning |")
        out.append("|---|---|---|")
        for f in fields:
            out.append(f"| `{f['name']}` | {_default(f)} | {f['help'].replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    text = DOC.read_text()
    a, b = text.index(BEGIN) + len(BEGIN), text.index(END)
    DOC.write_text(text[:a] + "\n\n" + tables() + "\n" + text[b:])
    print(f"updated {DOC}")


if __name__ == "__main__":
    main()
