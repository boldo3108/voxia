"""Reproduce audio (mp3/wav) por los parlantes del PC con el reproductor que trae Windows (MCI)."""
import asyncio
import itertools
import sys
from pathlib import Path

_contador = itertools.count(1)


class Reproductor:
    """Cada reproductor suena por su cuenta (la voz y la notificación no se cortan entre sí)."""

    def __init__(self):
        self._alias: str | None = None

    async def reproducir(self, ruta: Path, volumen: float = 0.9):
        """Reproduce y espera a que termine (o a que alguien llame a parar())."""
        if sys.platform != "win32":
            print("[Audio] La reproducción por parlantes solo está disponible en Windows.")
            return
        alias = f"boldo{next(_contador)}"
        self._alias = alias
        if _mci(f'open "{Path(ruta).resolve()}" type mpegvideo alias {alias}') is None:
            return
        vol = int(max(0.0, min(1.0, float(volumen))) * 1000)
        _mci(f"setaudio {alias} volume to {vol}")
        _mci(f"play {alias}")
        try:
            while self._alias == alias and _mci(f"status {alias} mode") == "playing":
                await asyncio.sleep(0.05)
        finally:
            _mci(f"close {alias}")

    def parar(self):
        alias, self._alias = self._alias, None
        if alias and sys.platform == "win32":
            _mci(f"stop {alias}")


def _mci(comando: str) -> str | None:
    """Envía un comando al reproductor de Windows. Devuelve la respuesta o None si falla."""
    import ctypes
    buffer = ctypes.create_unicode_buffer(256)
    error = ctypes.windll.winmm.mciSendStringW(comando, buffer, 255, None)
    if error:
        if comando.startswith("open"):
            msg = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(error, msg, 255)
            print(f"[Audio] No pude reproducir el audio: {msg.value}")
        return None
    return buffer.value
