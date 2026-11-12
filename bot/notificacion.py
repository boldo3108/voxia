"""Sonido de notificación: el que trae Voxia o uno propio recortado (máximo 10 segundos)."""
import math
import shutil
import struct
import wave
from pathlib import Path

from bot.rutas import CARPETA as _BASE

CARPETA = _BASE / "overlay"
ARCHIVO = CARPETA / "notificacion.wav"
MAX_SEGUNDOS = 10.0
MIN_SEGUNDOS = 0.1
FORMATOS = [("Audio", "*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus"), ("Todos los archivos", "*.*")]

# cuándo suena (lo que se guarda en config.toml)
ANTES = "antes de leer"
CADA = "cada mensaje"
PRIMERO = "primer mensaje"
OPCIONES_CUANDO = [ANTES, CADA, PRIMERO]


def crear_ding(destino: Path = ARCHIVO):
    """Crea el sonido por defecto: un 'ding-dong' corto y suave (no necesita librerías)."""
    sr = 44100
    muestras = []
    for inicio, freq, dur in ((0.0, 1318.5, 0.45), (0.13, 1046.5, 0.6)):   # Mi6 y Do6
        for i in range(int(dur * sr)):
            t = i / sr
            env = math.exp(-t * 7) * min(1, t * 200)
            idx = int(inicio * sr) + i
            while len(muestras) <= idx:
                muestras.append(0.0)
            muestras[idx] += 0.35 * env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t))
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, m)) * 32000)) for m in muestras))
    return destino


def asegurar_sonido() -> Path:
    if not ARCHIVO.exists():
        crear_ding()
    return ARCHIVO


def duracion(ruta: Path) -> float:
    try:
        with wave.open(str(ruta)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        try:
            import soundfile as sf
            return float(sf.info(str(ruta)).duration)
        except Exception:
            return 0.0


def cargar(ruta: Path):
    """Lee cualquier audio (mp3, wav, ogg, flac...). Devuelve (muestras mono float32, frecuencia)."""
    from bot.idioma import t
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        raise RuntimeError(t("Falta instalar una librería de audio. Ejecuta INSTALAR.bat otra vez."))
    try:
        datos, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    except Exception as e:
        raise RuntimeError(t("No pude leer ese archivo de audio ({error}).\nPrueba con un .mp3 o .wav.", error=e))
    if len(datos) == 0:
        raise RuntimeError(t("El archivo de audio está vacío."))
    return np.ascontiguousarray(datos.mean(axis=1)), int(sr)


def picos(datos, columnas: int):
    """Mínimo y máximo por columna, para dibujar la forma de onda."""
    import numpy as np
    columnas = max(1, int(columnas))
    largo = len(datos) - len(datos) % columnas
    if largo < columnas:
        relleno = np.zeros(columnas, dtype="float32")
        relleno[:len(datos)] = datos
        bloques = relleno.reshape(columnas, 1)
    else:
        bloques = datos[:largo].reshape(columnas, -1)
    return bloques.min(axis=1), bloques.max(axis=1)


def guardar_recorte(datos, sr: int, inicio: float, fin: float, destino: Path, fundido: bool = True,
                    normalizar: bool = False) -> Path:
    """Guarda el tramo [inicio, fin] (en segundos) como WAV. Corta a 10 s como máximo."""
    import numpy as np
    import soundfile as sf
    fin = min(fin, inicio + MAX_SEGUNDOS)
    trozo = np.array(datos[int(inicio * sr): int(fin * sr)], dtype="float32")
    if len(trozo) < int(MIN_SEGUNDOS * sr):
        from bot.idioma import t
        raise RuntimeError(t("El recorte es demasiado corto."))
    if normalizar and np.abs(trozo).max() > 0:
        trozo *= 0.95 / np.abs(trozo).max()
    if fundido:                     # entrada y salida suaves, para que no haga "clic"
        n = min(int(0.015 * sr), len(trozo) // 4)
        if n > 0:
            rampa = np.linspace(0, 1, n, dtype="float32")
            trozo[:n] *= rampa
            trozo[-n:] *= rampa[::-1]
    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destino), np.clip(trozo, -1, 1), sr, subtype="PCM_16")
    return destino


def guardar_original(origen: Path) -> Path:
    """Copia el archivo subido para poder recortarlo de nuevo más tarde."""
    for viejo in CARPETA.glob("notificacion_original.*"):
        viejo.unlink(missing_ok=True)
    destino = CARPETA / f"notificacion_original{Path(origen).suffix.lower()}"
    shutil.copyfile(origen, destino)
    return destino


def original() -> Path | None:
    return next(iter(sorted(CARPETA.glob("notificacion_original.*"))), None)
