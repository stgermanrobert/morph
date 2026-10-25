"""Writes packaging/version_info.txt, the .exe version resource (Properties → Details)."""
import sys
from pathlib import Path

v = sys.argv[1]
name, desc = sys.argv[2], sys.argv[3]
t = tuple(int(x) for x in (v.split(".") + ["0", "0", "0"])[:4])
Path(__file__).with_name("version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Germán Robert'),
      StringStruct('FileDescription', '{name} — {desc}'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('LegalCopyright', '© 2026 Germán Robert · MIT License'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '{name}'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
""", encoding="utf-8")
print("version_info.txt", v)
