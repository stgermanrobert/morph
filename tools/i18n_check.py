"""
Translation check: every string passed to tr() must exist in every catalog, with the same {placeholders}.

    python tools/i18n_check.py            # exit code 1 if something is missing
    python tools/i18n_check.py --dump     # print the keys as JSON (to add new translations)
"""
from __future__ import annotations

import ast
import json
import re
import string
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = literal(node.left), literal(node.right)
        return a + b if a is not None and b is not None else None
    return None


def keys_from_source() -> set[str]:
    keys = set()
    for f in SRC.glob("*.py"):
        if f.name in ("locales.py", "i18n.py"):
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                s = literal(node.args[0])
                if s is not None:
                    keys.add(s)
    return keys


def dynamic_keys() -> set[str]:
    """Strings translated through variables (tables of bands, listening modes, help sections…)."""
    keys = set()
    extra = SRC / "i18n_dynamic.py"
    if extra.exists():
        ns: dict = {}
        exec(extra.read_text(encoding="utf-8"), ns)
        keys |= set(ns["dynamic_keys"]())
    return keys


def fields(s: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def main():
    keys = keys_from_source() | dynamic_keys()
    if "--dump" in sys.argv:
        print(json.dumps(sorted(keys), ensure_ascii=False, indent=1))
        return 0
    import locales
    bad = 0
    for lang, cat in locales.CATALOGS.items():
        missing = sorted(k for k in keys if k not in cat)
        unused = sorted(k for k in cat if k not in keys)
        wrong = sorted(k for k in keys if k in cat and fields(k) != fields(cat[k]))
        for k in missing:
            print(f"[{lang}] MISSING: {k[:90]!r}")
        for k in wrong:
            print(f"[{lang}] PLACEHOLDERS DIFFER: {k[:90]!r}")
        for k in unused:
            print(f"[{lang}] unused (ok): {k[:90]!r}")
        bad += len(missing) + len(wrong)
        print(f"[{lang}] {len(keys) - len(missing)}/{len(keys)} translated")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
