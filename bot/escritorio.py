"""Cosas de Windows: ícono en la bandeja (junto al reloj), iniciar con Windows y una sola Voxia abierta."""
import socket
import sys
import threading
from pathlib import Path

from bot.rutas import CARPETA, ES_EXE, INTERNOS

PUERTO_INSTANCIA = 47831          # localhost: la segunda Voxia le pide a la primera que se muestre
CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_RUN = "Voxia"
ARG_INICIO = "--inicio-windows"


# ------------------------------------------------------------- una sola Voxia
class Instancia:
    """Si ya hay una Voxia abierta, le avisa para que se muestre y devuelve False."""

    def __init__(self, al_pedir_mostrar):
        self.al_pedir_mostrar = al_pedir_mostrar
        self._srv = None

    def tomar(self) -> bool:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.bind(("127.0.0.1", PUERTO_INSTANCIA))
        except OSError:
            srv.close()
            try:
                with socket.create_connection(("127.0.0.1", PUERTO_INSTANCIA), timeout=2) as c:
                    c.sendall(b"mostrar")
            except OSError:
                return True          # el puerto lo usa otro programa: seguimos igual
            return False
        srv.listen(2)
        self._srv = srv
        threading.Thread(target=self._escuchar, daemon=True).start()
        return True

    def _escuchar(self):
        while self._srv:
            try:
                c, _ = self._srv.accept()
                with c:
                    if c.recv(16).startswith(b"mostrar"):
                        self.al_pedir_mostrar()
            except OSError:
                break

    def soltar(self):
        if self._srv:
            srv, self._srv = self._srv, None
            srv.close()


# ------------------------------------------------------------ acceso directo
def crear_acceso_directo():
    """Crea «Voxia» en el escritorio de Windows, con su ícono. Lanza un error si no se pudo."""
    import subprocess
    icono = Path(sys.executable) if ES_EXE else INTERNOS / "recursos" / "voxia.ico"   # el .exe ya trae su ícono
    if ES_EXE:                       # Voxia.exe: el acceso directo apunta al .exe
        destino, argumentos = Path(sys.executable), ""
    else:
        destino = CARPETA / ".venv" / "Scripts" / "pythonw.exe"
        if not destino.exists():
            exe = Path(sys.executable)
            destino = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
        argumentos = chr(34) + str(CARPETA / "app.py") + chr(34)

    def q(ruta):          # texto para PowerShell entre comillas simples
        return "'" + str(ruta).replace("'", "''") + "'"
    script = (
        "$e=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine($e,'Voxia.lnk'));"
        f"$s.TargetPath={q(destino)};"
        f"$s.Arguments={q(argumentos)};"
        f"$s.WorkingDirectory={q(CARPETA)};"
        f"$s.IconLocation={q(icono)};"
        "$s.Description='Voxia';$s.Save()")
    if sys.platform != "win32":
        raise RuntimeError("Solo funciona en Windows.")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])


# ------------------------------------------------------------ iniciar con Windows
def comando_inicio() -> str:
    if ES_EXE:
        return f'"{sys.executable}" {ARG_INICIO}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
    return f'"{pythonw}" "{CARPETA / "app.py"}" {ARG_INICIO}'


def poner_inicio_windows(activar: bool) -> bool:
    """Agrega o quita Voxia del inicio de Windows (solo para tu usuario). Devuelve True si quedó bien."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
            if activar:
                winreg.SetValueEx(k, NOMBRE_RUN, 0, winreg.REG_SZ, comando_inicio())
            else:
                try:
                    winreg.DeleteValue(k, NOMBRE_RUN)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        print(f"[Inicio] No pude cambiar el inicio con Windows: {e}")
        return False


def abierta_por_windows() -> bool:
    return ARG_INICIO in sys.argv


# ----------------------------------------------------------------- bandeja
class Bandeja:
    """Ícono junto al reloj. Las acciones llegan desde el hilo del ícono: la app las pasa a su ventana."""

    def __init__(self, ruta_icono: Path, acciones: dict, textos):
        self.ruta_icono, self.acciones, self.textos = ruta_icono, acciones, textos
        self.icono = None
        self.aviso_dado = False

    @property
    def disponible(self) -> bool:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            return self.ruta_icono.exists()
        except Exception:
            return False

    def _menu(self):
        import pystray
        tx = self.textos()
        return pystray.Menu(
            pystray.MenuItem(tx["mostrar"], lambda *_: self.acciones["mostrar"](), default=True),
            pystray.MenuItem(tx["saltar"], lambda *_: self.acciones["saltar"]()),
            pystray.MenuItem(tx["callar"], lambda *_: self.acciones["callar"]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tx["salir"], lambda *_: self.acciones["salir"]()))

    def mostrar_icono(self) -> bool:
        if self.icono:
            return True
        if not self.disponible:
            return False
        try:
            import pystray
            from PIL import Image
            self.icono = pystray.Icon("Voxia", Image.open(self.ruta_icono), "Voxia", menu=self._menu())
            self.icono.run_detached()
            return True
        except Exception as e:
            print(f"[Bandeja] No pude mostrar el ícono: {e}")
            self.icono = None
            return False

    def actualizar_textos(self):
        if self.icono:
            try:
                self.icono.menu = self._menu()
                self.icono.update_menu()
            except Exception:
                pass

    def avisar(self, texto: str):
        """Globo de Windows (solo la primera vez que se esconde)."""
        if self.icono and not self.aviso_dado:
            self.aviso_dado = True
            try:
                self.icono.notify(texto, "Voxia")
            except Exception:
                pass

    def quitar(self):
        if self.icono:
            try:
                self.icono.stop()
            except Exception:
                pass
            self.icono = None
