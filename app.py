"""
Voxia — App de escritorio que lee el chat de Twitch en voz alta.
Abre con Voxia.exe  (o:  python app.py)

La ventana es una página (carpeta web/) que muestra un servidor local (bot/panel.py), igual que Stremia.
  python app.py --navegador   -> abre el panel en el navegador en vez de la ventana
"""
import os
import sys
import threading
import time
import webbrowser

from bot import atajos, escritorio, novedades
from bot.idioma import t
from bot.panel import Panel, Salida, ajustes_app, teclas_config
from bot.rutas import ES_EXE, INTERNOS

APP = "Voxia"
ICONO_PNG = INTERNOS / "recursos" / "voxia.png"


def webview_moderno() -> bool:
    """¿La ventana puede usar Edge WebView2? (si no, pywebview usaría Internet Explorer y el panel no funciona)."""
    try:
        import webview  # noqa: F401
    except Exception as e:
        print(f"[Ventana] No está pywebview: {e}")
        return False
    if sys.platform != "win32":
        return True
    try:
        from webview.platforms import winforms
        return getattr(winforms, "renderer", "") == "edgechromium"
    except Exception as e:
        print(f"[Ventana] No pude preparar la ventana: {e}")
        return False


class Escritorio:
    def __init__(self, instancia: escritorio.Instancia, navegador: bool):
        self.instancia = instancia
        self.navegador = navegador
        self.ventana = None
        self.oculta = False
        self._salir = threading.Event()
        self.panel = Panel()
        self.atajos = atajos.Atajos(self.panel.atajo)
        self.bandeja = escritorio.Bandeja(
            ICONO_PNG, {"mostrar": self.mostrar,
                        "saltar": lambda: self.panel.atajo("saltar"),
                        "callar": lambda: self.panel.atajo("callar"),
                        "salir": self.salir},
            lambda: {"mostrar": t("Mostrar Voxia"), "saltar": t("Saltar mensaje"),
                     "callar": t("Callar todo"), "salir": t("Salir")})
        self.panel.ganchos.update(ajustes=self.aplicar_ajustes, mostrar=self.mostrar, salir=self.salir,
                                  bandeja_textos=self.bandeja.actualizar_textos)
        instancia.al_pedir_mostrar = self.mostrar

    # ------------------------------------------------------------- ajustes
    def aplicar_ajustes(self, inicio: bool = False) -> list[str]:
        """Teclas rápidas, bandeja e inicio con Windows (al abrir y cada vez que se guarda la configuración)."""
        ap, teclas = ajustes_app(), teclas_config()
        fallidas = self.atajos.poner({"saltar": teclas["saltar"], "callar": teclas["callar"]})
        intento = 0
        while fallidas and inicio and intento < 6:
            # recién actualizada / reabierta: la Voxia anterior puede tardar un poco en soltar las teclas
            time.sleep(1)
            intento += 1
            fallidas = self.atajos.poner({"saltar": teclas["saltar"], "callar": teclas["callar"]})
        if ap["bandeja_minimizar"] or ap["bandeja_cerrar"] or (escritorio.abierta_por_windows()
                                                               and ap["iniciar_en_bandeja"]) or self.navegador:
            self.bandeja.mostrar_icono()
        elif not self.oculta:
            self.bandeja.quitar()
        if sys.platform == "win32" and (not inicio or ap["iniciar_windows"]):
            escritorio.poner_inicio_windows(ap["iniciar_windows"])
        if fallidas and inicio:
            self.panel.avisos.append(t("No pude usar estas teclas porque otro programa ya las ocupa:\n{teclas}\n\n"
                                       "Elige otras en Configuración → Teclas rápidas.", teclas=", ".join(fallidas)))
        return fallidas

    # ------------------------------------------------------------- ventana
    def mostrar(self):
        if self.navegador or not self.ventana:
            webbrowser.open(self.panel.url)
            return
        self.oculta = False
        try:
            self.ventana.show()
            self.ventana.restore()
            self.ventana.on_top = True        # traerla al frente
            self.ventana.on_top = False
        except Exception as e:
            print(f"[Ventana] {e}")
        ap = ajustes_app()
        if not (ap["bandeja_minimizar"] or ap["bandeja_cerrar"]):
            self.bandeja.quitar()

    def a_la_bandeja(self):
        if not self.ventana or not self.bandeja.mostrar_icono():
            return False             # sin bandeja: queda minimizada normal
        self.oculta = True
        self.ventana.hide()
        self.bandeja.avisar(t("Voxia sigue funcionando aquí. Haz clic en el ícono para volver."))
        return True

    def _al_minimizar(self):
        if ajustes_app()["bandeja_minimizar"]:
            threading.Thread(target=self.a_la_bandeja, daemon=True).start()

    def _al_cerrar(self):
        """Devuelve False para que la ventana NO se cierre (se va a la bandeja)."""
        if self._salir.is_set():
            return True
        if ajustes_app()["bandeja_cerrar"] and self.bandeja.disponible:
            threading.Thread(target=self.a_la_bandeja, daemon=True).start()
            return False
        self._salir.set()
        return True

    def _guardar_como(self, nombre: str) -> str | None:
        import webview
        r = self.ventana.create_file_dialog(webview.FileDialog.SAVE, save_filename=nombre,
                                            file_types=("Voxia (*.zip)",))
        if isinstance(r, (list, tuple)):
            r = r[0] if r else None
        return str(r) if r else None

    def salir(self):
        self._salir.set()
        if self.ventana:
            try:
                self.ventana.destroy()
            except Exception:
                pass

    # -------------------------------------------------------------- correr
    def correr(self):
        self.panel.iniciar()
        print(f"[Voxia] Panel en {self.panel.url}")
        cfg_app = ajustes_app()
        oculta = escritorio.abierta_por_windows() and cfg_app["iniciar_en_bandeja"]
        threading.Thread(target=self._al_arrancar, daemon=True).start()
        if not self.navegador:
            try:
                self._ventana(oculta)
            except Exception as e:
                print(f"[Ventana] No pude abrir la ventana ({e}); uso el navegador.")
                self.navegador = True
                self.panel.avisos.append(t("No pude abrir la ventana de Voxia, así que se abrió en el navegador. "
                                           "Instala «Microsoft Edge WebView2» para verla como app."))
        if self.navegador:
            if not oculta:
                webbrowser.open(self.panel.url)
            self.bandeja.mostrar_icono()
            try:
                while not self._salir.wait(0.5):
                    pass
            except KeyboardInterrupt:
                pass
        self.cerrar()

    def _ventana(self, oculta: bool):
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        self.ventana = webview.create_window(
            APP, self.panel.url, width=1180, height=760, min_size=(920, 600),
            background_color="#0f1114", hidden=oculta, text_select=True)
        self.oculta = oculta
        self.ventana.events.closing += self._al_cerrar
        self.ventana.events.minimized += self._al_minimizar
        self.panel.ganchos["guardar_como"] = self._guardar_como
        if oculta:
            self.bandeja.mostrar_icono()
        webview.start(private_mode=True, debug="--depurar" in sys.argv)

    def _al_arrancar(self):
        self.aplicar_ajustes(inicio=True)
        cfg = ajustes_app()
        from bot import config_io
        if cfg["conectar_al_abrir"] and config_io.leer().get("twitch", {}).get("token"):
            time.sleep(1.2)
            self.panel.iniciar_bot(False)
        if ES_EXE:
            novedades.limpiar_temporales()
            novedades.limpiar_version_carpeta()
        if cfg["buscar_actualizaciones"]:
            time.sleep(4)
            if self.panel.loop:
                import asyncio
                fut = asyncio.run_coroutine_threadsafe(self.panel.buscar_novedades(), self.panel.loop)
                try:
                    fut.result(30)
                except Exception as e:
                    print(f"[Novedades] No pude revisar: {e}")

    def cerrar(self):
        self.panel.cerrar()
        self.atajos.detener()
        self.bandeja.quitar()
        self.instancia.soltar()


def main():
    if novedades.instalar_si_se_pidio():   # este .exe vino a instalar una versión nueva encima de la vieja
        sys.exit(0)
    if sys.platform == "win32":
        try:  # que Windows agrupe la app con su propio ícono en la barra de tareas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("voxia.app")
        except Exception:
            pass
    instancia = escritorio.Instancia(lambda: None)
    if not instancia.tomar():           # ya hay una Voxia abierta: esa se muestra y esta se cierra
        sys.exit(0)
    sys.stdout = sys.stderr = Salida()     # recién ahora: la segunda Voxia no debe borrar el voxia.log de la primera
    navegador = "--navegador" in sys.argv or not webview_moderno()
    app = Escritorio(instancia, navegador)
    app.correr()
    print("¡Chao!")
    os._exit(0)                         # que ningún hilo deje la app abierta


if __name__ == "__main__":
    main()
