"""Teclas rápidas globales (funcionan aunque estés dentro de un juego). Solo Windows.

Se guardan como texto: "F9", "Ctrl+F10", "Alt+Shift+Pausa"…  ("" = desactivada)
"""
import sys
import threading

TECLAS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
          "Pausa", "Bloq Despl", "Insert", "Inicio", "Fin", "RePág", "AvPág",
          "Num 0", "Num 1", "Num 2", "Num 3", "Num 4", "Num 5", "Num 6", "Num 7", "Num 8", "Num 9"]
MODIFICADORES = ["Ninguno", "Ctrl", "Alt", "Shift", "Ctrl+Shift", "Ctrl+Alt"]

_VK = {**{f"F{i}": 0x6F + i for i in range(1, 13)},
       "Pausa": 0x13, "Bloq Despl": 0x91, "Insert": 0x2D, "Inicio": 0x24, "Fin": 0x23,
       "RePág": 0x21, "AvPág": 0x22, **{f"Num {i}": 0x60 + i for i in range(10)}}
_MOD = {"Alt": 0x1, "Ctrl": 0x2, "Shift": 0x4}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY, _WM_QUIT = 0x0312, 0x0012

DISPONIBLE = sys.platform == "win32"


def separar(combo: str) -> tuple[str, str]:
    """"Ctrl+F9" -> ("Ctrl", "F9") · "F9" -> ("Ninguno", "F9") · "" -> ("Ninguno", "")"""
    combo = (combo or "").strip()
    for mod in sorted(MODIFICADORES[1:], key=len, reverse=True):
        if combo.startswith(mod + "+") and combo[len(mod) + 1:] in _VK:
            return mod, combo[len(mod) + 1:]
    return "Ninguno", combo if combo in _VK else ""


def juntar(mod: str, tecla: str) -> str:
    if not tecla:
        return ""
    return tecla if mod in ("", "Ninguno") else f"{mod}+{tecla}"


class Atajos:
    """Registra las teclas en un hilo propio (Windows exige que el hilo que las registra lea sus mensajes)."""

    def __init__(self, al_pulsar):
        self.al_pulsar = al_pulsar          # al_pulsar(accion) — se llama desde OTRO hilo
        self._hilo = None
        self._tid = 0

    def poner(self, teclas: dict[str, str]) -> list[str]:
        """teclas = {"saltar": "F9", "callar": ""}. Devuelve las combinaciones que no se pudieron registrar
        (porque otro programa ya las usa)."""
        self.detener()
        teclas = {accion: c for accion, c in teclas.items() if c}
        if not DISPONIBLE or not teclas:
            return []
        listo, fallidas = threading.Event(), []
        self._hilo = threading.Thread(target=self._bucle, args=(teclas, listo, fallidas), daemon=True)
        self._hilo.start()
        listo.wait(3)
        return fallidas

    def _bucle(self, teclas, listo, fallidas):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()
        ids = {}
        for n, (accion, combo) in enumerate(teclas.items(), start=1):
            mod, tecla = separar(combo)
            mods = _MOD_NOREPEAT
            for parte in ("" if mod == "Ninguno" else mod).split("+"):
                mods |= _MOD.get(parte, 0)
            if tecla and user32.RegisterHotKey(None, n, mods, _VK[tecla]):
                ids[n] = accion
            else:
                fallidas.append(combo)
        listo.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY and msg.wParam in ids:
                    try:
                        self.al_pulsar(ids[msg.wParam])
                    except Exception as e:
                        print(f"[Teclas] Error: {e}")
        finally:
            for n in ids:
                user32.UnregisterHotKey(None, n)

    def detener(self):
        if self._hilo and self._hilo.is_alive() and self._tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)
            self._hilo.join(2)
        self._hilo, self._tid = None, 0
