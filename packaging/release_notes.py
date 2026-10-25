"""Extracts one version's section from CHANGELOG.md, used as the GitHub Release text."""
import re
import sys
from pathlib import Path

v = sys.argv[1]
text = Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(rf"^## \[{re.escape(v)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
body = (m.group(1).strip() if m else f"Version {v}") + "\n"
Path(sys.argv[2]).write_text(body, encoding="utf-8")
print(body)
