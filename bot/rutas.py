"""Dónde viven los archivos de Voxia.

- Con Python (app.py): la carpeta del proyecto.
- Como Voxia.exe: la carpeta donde está el .exe (ahí quedan config.toml, el log, la notificación…).

INTERNOS es lo que viene DENTRO del .exe (la página, los íconos, el overlay, VERSION): solo se lee.
"""
import sys
from pathlib import Path

ES_EXE = bool(getattr(sys, "frozen", False))
CARPETA = Path(sys.executable).resolve().parent if ES_EXE else Path(__file__).resolve().parent.parent
INTERNOS = Path(getattr(sys, "_MEIPASS", CARPETA))
