"""Escribe version_win.txt (los datos que muestra Windows en Propiedades de Voxia.exe) con la versión de VERSION."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
v = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
n = tuple(int("".join(c for c in p if c.isdigit()) or 0) for p in (v.split(".") + ["0", "0", "0"])[:4])
(RAIZ / "version_win.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={n}, prodvers={n}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'boldo3108'),
      StringStruct('FileDescription', 'Voxia - lee el chat de Twitch en voz alta'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'Voxia'),
      StringStruct('OriginalFilename', 'Voxia.exe'),
      StringStruct('ProductName', 'Voxia'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print("version_win.txt ->", v)
