"""Levanta solo el panel de Voxia (sin ventana, sin bandeja ni teclas) para probarlo en el navegador.

    python herramientas/servir_panel.py        ->  http://127.0.0.1:8766
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.panel import Panel  # noqa: E402

panel = Panel()
panel.ganchos["ajustes"] = lambda inicio=False: []
panel.iniciar()
print("Panel en", panel.url, "(Ctrl+C para salir)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    panel.cerrar()
