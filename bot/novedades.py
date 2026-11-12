"""Aviso de versiones nuevas publicadas en GitHub (Releases) y actualización automática del .exe.

Cómo publicar una versión nueva: sube un tag (git tag v2.1.0 && git push origin v2.1.0).
GitHub Actions (.github/workflows/compilar.yml) compila Voxia.exe y crea la Release con:
  - Voxia.exe                      -> lo que descargan las versiones 2.x para actualizarse
  - Voxia-X.Y.Z-portable.zip       -> para las versiones viejas (1.x), que buscan un .zip
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import aiohttp

from bot.actualizar import _numeros, version_actual
from bot.rutas import CARPETA, ES_EXE

REPO = "boldo3108/voxia"
API = os.environ.get("VOXIA_API_RELEASES") or f"https://api.github.com/repos/{REPO}/releases/latest"
PAGINA = f"https://github.com/{REPO}/releases/latest"

# Lo tuyo: la actualización nunca lo toca
NO_TOCAR = ["config.toml", "config.toml.bak", "voces_usuarios.json", "voxia.log",
            "avatar.png", "notificacion.wav", "notificacion_original.*"]


async def ultima_version() -> dict | None:
    """{"version", "notas", "pagina", "zip"} de la última versión publicada, o None si no hay / no se pudo."""
    cabeceras = {"Accept": "application/vnd.github+json", "User-Agent": "Voxia"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12), headers=cabeceras) as s:
        async with s.get(API) as r:
            if r.status == 404:
                return None
            if r.status != 200:
                raise RuntimeError(f"GitHub respondió {r.status}")
            d = await r.json(content_type=None)
    zips = [a for a in d.get("assets", []) if str(a.get("name", "")).lower().endswith(".zip")]
    return {"version": str(d.get("tag_name") or d.get("name") or "").lstrip("vV").strip(),
            "notas": (d.get("body") or "").strip(),
            "pagina": d.get("html_url") or PAGINA,
            "zip": zips[0]["browser_download_url"] if zips else "",
            "exe": next((a["browser_download_url"] for a in d.get("assets", [])
                         if str(a.get("name", "")).lower() == "voxia.exe"), "")}


def es_mas_nueva(version: str) -> bool:
    actual = version_actual()
    return bool(version) and actual != "?" and _numeros(version) > _numeros(actual)


async def descargar(url: str, destino: Path, progreso=lambda fraccion: None) -> Path:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900),
                                     headers={"User-Agent": "Voxia"}) as s:
        async with s.get(url) as r:
            if r.status != 200:
                raise RuntimeError(f"No pude descargar ({r.status})")
            total, hecho = int(r.headers.get("Content-Length") or 0), 0
            with open(destino, "wb") as f:
                async for trozo in r.content.iter_chunked(256 * 1024):
                    f.write(trozo)
                    hecho += len(trozo)
                    if total:
                        progreso(hecho / total)
    return destino


def preparar(zip_descargado: Path) -> Path:
    """Descomprime la versión nueva en una carpeta temporal y devuelve la carpeta que trae Voxia.exe."""
    tmp = Path(tempfile.mkdtemp(prefix="voxia_nueva_"))
    with zipfile.ZipFile(zip_descargado) as z:
        for n in z.namelist():
            if n.startswith("/") or ".." in Path(n).parts:
                raise RuntimeError("El .zip tiene rutas raras; no lo uso.")
        z.extractall(tmp)
    candidatos = sorted(tmp.rglob("Voxia.exe"), key=lambda p: len(p.parts))
    if not candidatos:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("El .zip no trae Voxia.exe.")
    return candidatos[0].parent


def preparar_exe(exe_descargado: Path) -> Path:
    """Pone el Voxia.exe descargado en su propia carpeta temporal y devuelve esa carpeta."""
    tmp = Path(tempfile.mkdtemp(prefix="voxia_nueva_"))
    shutil.move(str(exe_descargado), str(tmp / "Voxia.exe"))
    return tmp


def aplicar_y_reiniciar(nueva: Path):
    """Abre el Voxia.exe NUEVO (desde la carpeta temporal) para que se instale encima de este.
    Quien llama debe cerrar la app justo después: el nuevo espera a que se cierre."""
    if not ES_EXE:
        raise RuntimeError("La actualización automática es para Voxia.exe.")
    subprocess.Popen([str(nueva / "Voxia.exe"), "--instalar", str(CARPETA), "--pid", str(os.getpid())],
                     cwd=str(nueva))


def _esperar_pid(pid: int, segundos: float = 60):
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, int(segundos * 1000))
        k.CloseHandle(h)


def _no_tocar(rel: Path) -> bool:
    import fnmatch
    if rel.parts[:2] == ("overlay", "audio"):
        return True
    return any(fnmatch.fnmatch(rel.name, patron) for patron in NO_TOCAR)


def _copiar(origen: Path, destino: Path, intentos: int = 20):
    import time
    for n in range(intentos):
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            with open(origen, "rb") as fo, open(destino, "wb") as fd:     # copia simple (sin CopyFile2)
                shutil.copyfileobj(fo, fd, 1024 * 1024)
            try:
                st = origen.stat()
                os.utime(destino, (st.st_atime, st.st_mtime))
            except OSError:
                pass
            return
        except PermissionError:          # Windows todavía no suelta el archivo
            time.sleep(0.5)
    raise RuntimeError(f"No pude reemplazar {destino.name}")


def instalar_si_se_pidio() -> bool:
    """Si este Voxia.exe se abrió con --instalar, se copia encima de la instalación vieja y la abre.
    Devuelve True si hizo la instalación (entonces el programa debe terminar)."""
    if "--instalar" not in sys.argv:
        return False
    args = sys.argv
    destino = Path(args[args.index("--instalar") + 1])
    pid = int(args[args.index("--pid") + 1]) if "--pid" in args else 0
    nueva = CARPETA                      # la carpeta temporal donde está este .exe
    error = None
    try:
        if pid:
            _esperar_pid(pid)
        nuevos = set()
        for f in nueva.rglob("*"):
            if f.is_file():
                rel = f.relative_to(nueva)
                if _no_tocar(rel):
                    continue
                nuevos.add(rel)
                _copiar(f, destino / rel)
        if not (nueva / "_internal").exists():   # la versión nueva es un solo .exe
            limpiar_version_carpeta(destino)
        else:
            viejos = destino / "_internal"            # lo que ya no trae la versión nueva
            for f in list(viejos.rglob("*")) if viejos.exists() else []:
                if f.is_file() and f.relative_to(destino) not in nuevos:
                    try:
                        f.unlink()
                    except OSError:
                        pass
    except Exception as e:
        error = e
    if error:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"No se pudo terminar la actualización:\n{error}\n\n"
                                                   f"Descarga la versión nueva desde {PAGINA}", "Voxia", 0x10)
        except Exception:
            pass
    subprocess.Popen([str(destino / "Voxia.exe")], cwd=str(destino))
    return True


# Lo que traían las versiones de carpeta (hasta la 2.0 en .zip) y ahora viene dentro de Voxia.exe
SOBRAS_CARPETA = ["_internal", "web", "recursos", "VERSION", "overlay/index.html"]


def limpiar_version_carpeta(destino: Path | None = None):
    """Borra lo que dejó la versión vieja (de carpeta) y que el .exe único ya trae adentro."""
    if not ES_EXE or not hasattr(sys, "_MEIPASS"):
        return
    destino = destino or CARPETA
    if not (destino / "Voxia.exe").exists():
        return
    for rel in SOBRAS_CARPETA:
        p = destino / rel
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:
            pass


def limpiar_temporales():
    """Borra las carpetas de actualizaciones anteriores que quedaron en %TEMP%."""
    for d in Path(tempfile.gettempdir()).glob("voxia_nueva_*"):
        if d.is_dir() and CARPETA not in (d, *d.parents) and d not in CARPETA.parents:
            shutil.rmtree(d, ignore_errors=True)
    for z in [*Path(tempfile.gettempdir()).glob("Voxia-*.zip"), *Path(tempfile.gettempdir()).glob("Voxia-*.exe")]:
        try:
            z.unlink()
        except OSError:
            pass
