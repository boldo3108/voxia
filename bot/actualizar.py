"""Actualizar Voxia con un .zip nuevo sin perder la configuración, la sesión ni tus sonidos.

Uso desde la app (Configuración → Actualizaciones) o con ACTUALIZAR.bat:
    python -m bot.actualizar  ruta\\al\\Voxia-nuevo.zip
"""
import hashlib
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import PurePosixPath, Path

from bot.idioma import t

from bot.rutas import CARPETA, INTERNOS
ARCHIVO_VERSION = INTERNOS / "VERSION"
CARPETA_RESPALDOS = CARPETA / "backups"
MAX_RESPALDOS = 5

# Lo tuyo: nunca se reemplaza ni se borra
PROTEGIDOS_EXACTOS = {
    "config.toml", "config.toml.bak", "voces_usuarios.json", "boldobot.log", "voxia.log",
    "overlay/avatar.png", "overlay/notificacion.wav",
}
PROTEGIDOS_PREFIJOS = ("overlay/audio/", "overlay/audio_prueba/", "overlay/notificacion_original.",
                       ".venv/", "venv/", "backups/", "__pycache__/")


def version_actual() -> str:
    try:
        return ARCHIVO_VERSION.read_text(encoding="utf-8").strip() or "?"
    except OSError:
        return "?"


def _numeros(v: str) -> tuple:
    partes = []
    for p in v.strip().lstrip("vV").split("."):
        num = "".join(c for c in p if c.isdigit())
        partes.append(int(num) if num else 0)
    return tuple(partes)


def protegido(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return (rel in PROTEGIDOS_EXACTOS or rel.startswith(PROTEGIDOS_PREFIJOS)
            or "/__pycache__/" in rel or rel.endswith(".pyc"))


def administrado(rel: str) -> bool:
    """Archivos del programa (los que una versión nueva puede borrar si ya no vienen)."""
    p = PurePosixPath(rel)
    if len(p.parts) == 1:
        return p.suffix in (".py", ".bat", ".md") or p.name in ("VERSION", "requirements.txt")
    if p.parts[0] == "bot" and len(p.parts) == 2:
        return p.suffix == ".py"
    if p.parts[0] == "recursos" and len(p.parts) == 2:
        return True
    return rel == "overlay/index.html"


def _hash(ruta: Path) -> str:
    try:
        return hashlib.sha256(ruta.read_bytes()).hexdigest()
    except OSError:
        return ""


class Paquete:
    """Un .zip de Voxia ya revisado: sabe su versión y qué archivos trae."""

    def __init__(self, ruta_zip):
        self.ruta = Path(ruta_zip)
        if not zipfile.is_zipfile(self.ruta):
            raise ValueError(t("Ese archivo no es un .zip válido."))
        self.zip = zipfile.ZipFile(self.ruta)
        nombres = [n for n in self.zip.namelist() if not n.endswith("/")]
        raices = sorted((n[: -len("app.py")] for n in nombres
                         if n == "app.py" or n.endswith("/app.py")), key=len)
        if not raices:
            raise ValueError(t("Ese .zip no es de Voxia (no trae app.py)."))
        self.raiz = raices[0]          # "" o "Voxia/"
        self.archivos = {}             # ruta relativa → nombre dentro del zip
        for n in nombres:
            if not n.startswith(self.raiz):
                continue
            rel = n[len(self.raiz):]
            if not rel or ".." in PurePosixPath(rel).parts or rel.startswith("/"):
                continue
            if protegido(rel):
                continue
            self.archivos[rel] = n
        if "main.py" not in self.archivos or "bot/voz.py" not in self.archivos:
            raise ValueError(t("Ese .zip no es de Voxia (le faltan archivos del programa)."))
        try:
            self.version = self.zip.read(self.archivos["VERSION"]).decode("utf-8").strip()
        except KeyError:
            self.version = "?"

    def es_mas_nueva(self) -> bool | None:
        """True si es más nueva, False si es igual o más vieja, None si no se puede saber."""
        actual, nueva = version_actual(), self.version
        if "?" in (actual, nueva):
            return None
        return _numeros(nueva) > _numeros(actual)

    def cerrar(self):
        self.zip.close()


def _respaldar(rels: list[str]) -> Path:
    destino = CARPETA_RESPALDOS / f"v{version_actual()}_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
    destino.mkdir(parents=True, exist_ok=True)
    for rel in rels:
        origen = CARPETA / rel
        if origen.is_file():
            d = destino / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, d)
    # Solo se guardan los últimos respaldos
    viejos = sorted((p for p in CARPETA_RESPALDOS.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for p in viejos[:-MAX_RESPALDOS]:
        shutil.rmtree(p, ignore_errors=True)
    return destino


def _actuales() -> list[str]:
    res = []
    for p in CARPETA.rglob("*"):
        if p.is_file():
            rel = p.relative_to(CARPETA).as_posix()
            if administrado(rel) and not protegido(rel):
                res.append(rel)
    return res


def _instalar_librerias(avisar=print) -> bool:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":          # pythonw no muestra la salida de pip
        exe = exe.with_name("python.exe")
    flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
    avisar(t("Instalando librerías nuevas… (puede tardar un poco)"))
    try:
        r = subprocess.run([str(exe), "-m", "pip", "install", "-r", str(CARPETA / "requirements.txt")],
                           capture_output=True, text=True, creationflags=flags, timeout=900)
        if r.returncode != 0:
            avisar("⚠ No pude instalar las librerías. Ejecuta INSTALAR.bat.\n" + (r.stderr or r.stdout)[-600:])
            return False
        return True
    except Exception as e:
        avisar(f"⚠ No pude instalar las librerías ({e}). Ejecuta INSTALAR.bat.")
        return False


def aplicar(paquete: Paquete, avisar=print) -> dict:
    """Copia la versión nueva. Antes respalda lo que se va a tocar en backups/."""
    actuales = _actuales()
    nuevos = paquete.archivos
    cambian = [rel for rel, n in nuevos.items()
               if hashlib.sha256(paquete.zip.read(n)).hexdigest() != _hash(CARPETA / rel)]
    sobran = [rel for rel in actuales if rel not in nuevos]
    req_cambia = "requirements.txt" in cambian
    respaldo = _respaldar(sorted(set(cambian) | set(sobran)))

    for rel in cambian:
        destino = CARPETA / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".nuevo")
        tmp.write_bytes(paquete.zip.read(nuevos[rel]))
        tmp.replace(destino)
    for rel in sobran:
        try:
            (CARPETA / rel).unlink()
        except OSError:
            pass
    shutil.rmtree(CARPETA / "bot" / "__pycache__", ignore_errors=True)

    librerias_ok = _instalar_librerias(avisar) if req_cambia else True
    return {"version": paquete.version, "cambiados": cambian, "borrados": sobran,
            "respaldo": respaldo, "librerias_ok": librerias_ok}


def _consola(argv):
    try:
        from bot import config_io, idioma
        idioma.poner(idioma.de_config(config_io.leer()))
    except Exception:
        pass
    print(t("Voxia — versión instalada: {v}", v=version_actual()) + "\n")
    if len(argv) < 2:
        print(t("Uso: arrastra el .zip nuevo encima de ACTUALIZAR.bat"))
        return 1
    try:
        pq = Paquete(argv[1].strip('"'))
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1
    print(t("Versión del .zip: {v}", v=pq.version))
    if pq.es_mas_nueva() is False:
        if input(t("Esa versión no es más nueva que la tuya. ¿Instalarla igual? (s/n): ")).strip().lower() not in ("s", "y"):
            return 0
    r = aplicar(pq)
    pq.cerrar()
    print("\n[OK] " + t("Voxia actualizado a la versión {v} ({c} archivo/s nuevos o cambiados, {b} borrado/s).",
                         v=r["version"], c=len(r["cambiados"]), b=len(r["borrados"])))
    print("     " + t("Respaldo de lo anterior en: {ruta}", ruta=r["respaldo"]))
    print("     " + t("Tu config.toml, la sesión de Twitch, el avatar y la notificación no se tocaron."))
    return 0


if __name__ == "__main__":
    sys.exit(_consola(sys.argv))
