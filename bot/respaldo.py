"""Exportar / importar la configuración de Voxia en un .zip (para otro PC o para recuperarla)."""
import json
import re
import shutil
import time
import tomllib
import zipfile
from pathlib import Path

from bot import config_io
from bot.actualizar import version_actual
from bot.rutas import CARPETA

MARCA = "voxia-respaldo.json"
ARCHIVOS = ["config.toml", "voces_usuarios.json", "overlay/avatar.png", "overlay/notificacion.wav"]
PATRONES = ["overlay/notificacion_original.*"]
# Claves secretas: la sesión de Twitch y las API keys / contraseñas de los motores de voz
_SECRETA = re.compile(r"^(token|.*api_key|.*secret.*|.*password|access_key|account_id|email)$", re.I)
_LINEA = re.compile(r'^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(".*?"|\'.*?\')(\s*(#.*)?)$')


def _archivos() -> list[Path]:
    lista = [CARPETA / a for a in ARCHIVOS]
    for patron in PATRONES:
        carpeta, nombre = patron.rsplit("/", 1)
        lista += sorted((CARPETA / carpeta).glob(nombre))
    return [p for p in lista if p.is_file()]


def _sin_secretos(texto: str) -> str:
    salida = []
    for linea in texto.splitlines():
        m = _LINEA.match(linea)
        if m and _SECRETA.match(m.group(2)):
            linea = f'{m.group(1)}{m.group(2)}{m.group(3)}""{m.group(5) or ""}'
        salida.append(linea)
    return "\n".join(salida) + "\n"


def exportar(destino: Path, con_claves: bool) -> Path:
    destino = Path(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for p in _archivos():
            rel = p.relative_to(CARPETA).as_posix()
            if rel == "config.toml" and not con_claves:
                z.writestr(rel, _sin_secretos(p.read_text(encoding="utf-8")))
            else:
                z.write(p, rel)
        z.writestr(MARCA, json.dumps({"app": "Voxia", "version": version_actual(), "con_claves": con_claves,
                                      "fecha": time.strftime("%Y-%m-%d %H:%M")}, indent=1))
    return destino


def leer_info(ruta: Path) -> dict:
    """Revisa que el .zip sea un respaldo de Voxia y devuelve su información."""
    if not zipfile.is_zipfile(ruta):
        raise ValueError("no es un .zip válido")
    with zipfile.ZipFile(ruta) as z:
        nombres = set(z.namelist())
        if "config.toml" not in nombres:
            raise ValueError("no es un respaldo de Voxia (no trae config.toml)")
        try:
            tomllib.loads(z.read("config.toml").decode("utf-8"))
        except Exception as e:
            raise ValueError(f"el config.toml del respaldo está dañado ({e})")
        info = json.loads(z.read(MARCA)) if MARCA in nombres else {}
    return info


def _secretos(datos: dict, camino=()) -> dict:
    """{(seccion, clave): valor} de las claves secretas con valor."""
    res = {}
    for k, v in datos.items():
        if isinstance(v, dict):
            res.update(_secretos(v, camino + (k,)))
        elif isinstance(v, str) and v and _SECRETA.match(k) and len(camino) == 1:
            res[(camino[0], k)] = v
    return res


def importar(ruta: Path) -> Path:
    """Reemplaza la configuración por la del respaldo. Antes copia la actual a backups/.
    Si el respaldo viene sin claves, se conservan tu sesión y tus API keys actuales."""
    leer_info(ruta)
    copia = CARPETA / "backups" / f"antes-de-importar_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
    copia.mkdir(parents=True, exist_ok=True)
    for p in _archivos():
        d = copia / p.relative_to(CARPETA)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, d)
    actuales = _secretos(config_io.leer()) if config_io.CONFIG.exists() else {}

    with zipfile.ZipFile(ruta) as z:
        permitidos = set(ARCHIVOS)
        for n in z.namelist():
            ok = n in permitidos or any(Path(n).match(pat) for pat in PATRONES)
            if not ok or n.startswith("/") or ".." in Path(n).parts:
                continue
            if n.startswith("overlay/notificacion_original."):
                for viejo in (CARPETA / "overlay").glob("notificacion_original.*"):
                    viejo.unlink(missing_ok=True)
            destino = CARPETA / n
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(z.read(n))

    nuevos = _secretos(config_io.leer())
    conservar = {}
    for (seccion, clave), valor in actuales.items():
        if (seccion, clave) not in nuevos:
            conservar.setdefault(seccion, {})[clave] = valor
    if conservar:
        config_io.guardar(conservar)
    return copia
