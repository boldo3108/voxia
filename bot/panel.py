"""
Servidor del panel de Voxia: la ventana es una página web (web/panel.html) que habla con este
servidor local (solo 127.0.0.1). Aquí vive todo lo que antes hacía la ventana de customtkinter:
iniciar/detener el bot, Opciones de leer, Configuración, notificación, respaldo y actualizaciones.

  GET  /                -> la página
  GET  /ws              -> eventos en vivo (chat, estado, fila, hablando…)
  GET  /app/mostrar     -> otra Voxia pidió mostrar esta ventana
  /api/...              -> acciones (JSON)
"""
import asyncio
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from pathlib import Path

from aiohttp import WSMsgType, web

from bot import actualizar as A
from bot import atajos, config_io, escritorio, idioma, novedades, respaldo, tema, twitch_login
from bot import lector as L
from bot import notificacion as N
from bot import proveedores as P
from bot.idioma import t
from bot.reproductor import Reproductor
from bot.rutas import CARPETA, ES_EXE, INTERNOS
from bot.voz import Voz

APP = "Voxia"
WEB = INTERNOS / "web"
PUERTO = 8766

# Opciones de la ventana (sección [app] de config.toml) y teclas rápidas ([atajos])
APP_DEFECTO = {"bandeja_minimizar": True, "bandeja_cerrar": False, "iniciar_windows": False,
               "iniciar_en_bandeja": True, "conectar_al_abrir": False, "buscar_actualizaciones": True}
ATAJOS_DEFECTO = {"saltar": "F9", "callar": ""}
NOTIF_DEFECTO = {"activada": False, "volumen": 0.8}
VOZ_DEFECTO = {"motor": "edge", "volumen": 0.9, "gemini_voz": "Puck",
               "gemini_estilo": "Lee esto en español con acento chileno, como un joven bromista y buena onda, "
                                "con energía y ritmo rápido"}
COLUMNAS_ONDA = 820


def ajustes_app(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else config_io.leer()
    return {**APP_DEFECTO, **cfg.get("app", {})}


def teclas_config(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else config_io.leer()
    return {**ATAJOS_DEFECTO, **cfg.get("atajos", {})}


def nombre_bot(cfg: dict) -> str:
    nombre = cfg.get("bot", {}).get("nombre") or "Voxia"
    return "Voxia" if nombre == "BoldoBot" else nombre


def puerto_libre(desde: int = PUERTO, intentos: int = 20) -> int:
    for p in range(desde, desde + intentos):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("No encontré un puerto libre para la ventana de Voxia.")


# ------------------------------------------------------------- el motor del bot
class Runner:
    """Corre el bot en un hilo aparte (con su propio loop), igual que antes."""

    def __init__(self, al_evento):
        self.al_evento = al_evento          # (tipo, datos) desde el hilo del bot
        self.loop: asyncio.AbstractEventLoop | None = None
        self.bot = None
        self.hilo: threading.Thread | None = None
        self.tarea = None
        self.prueba = False
        self._corriendo = False
        self._parar = False

    @property
    def activo(self) -> bool:
        # una marca propia: el aviso «detenido» sale cuando el hilo todavía no termina del todo
        return self._corriendo

    def iniciar(self, prueba: bool):
        cfg = config_io.leer()
        self.prueba = prueba
        self._corriendo = True
        self._parar = False
        self.hilo = threading.Thread(target=self._correr, args=(cfg, prueba), daemon=True)
        self.hilo.start()

    def _correr(self, cfg, prueba):
        from main import BoldoBot
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        try:
            self.bot = BoldoBot(cfg, modo_prueba=prueba, consola=False,
                                eventos=lambda tipo, **d: self.al_evento(tipo, d))
            self.tarea = loop.create_task(self.bot.correr())
            if self._parar:                  # pulsaron Detener mientras arrancaba
                self.tarea.cancel()
            loop.run_until_complete(self.tarea)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"\n❌ {e}\n")
            self.al_evento("error", {"texto": str(e)})
        finally:
            pendientes = [x for x in asyncio.all_tasks(loop) if not x.done()]
            for x in pendientes:
                x.cancel()
            if pendientes:
                loop.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
            loop.close()
            self.bot, self.loop, self.tarea = None, None, None
            self._corriendo = False
            self.al_evento("detenido", {})

    def detener(self):
        self._parar = True
        if self.loop and self.tarea:
            self.loop.call_soon_threadsafe(self.tarea.cancel)

    def esperar(self, segundos: float = 4):
        if self.hilo:
            self.hilo.join(timeout=segundos)

    def llamar(self, nombre: str, *args) -> bool:
        bot, loop = self.bot, self.loop
        if not bot or not loop:
            return False

        def ejecutar():
            r = getattr(bot, nombre)(*args)
            if asyncio.iscoroutine(r):
                asyncio.ensure_future(r)
        loop.call_soon_threadsafe(ejecutar)
        return True


class Salida:
    """Los print() van a voxia.log (sirve si hay que revisar un error)."""

    def __init__(self):
        try:
            self.archivo = open(CARPETA / "voxia.log", "w", encoding="utf-8", buffering=1)
        except OSError:
            self.archivo = None

    def write(self, s):
        if s and self.archivo:
            try:
                self.archivo.write(s)
            except (OSError, ValueError):
                pass
        if sys.__stdout__ and s:
            try:
                sys.__stdout__.write(s)
            except Exception:
                pass

    def flush(self):
        pass


def _err(e) -> web.Response:
    return web.json_response({"ok": False, "error": str(e)}, status=200)


def _ok(**datos) -> web.Response:
    return web.json_response({"ok": True, **datos})


# ------------------------------------------------------------------ el panel
class Panel:
    def __init__(self):
        cfg = config_io.leer()
        idioma.poner(idioma.de_config(cfg))
        self.loop: asyncio.AbstractEventLoop | None = None
        self.puerto = 0
        self.clientes: set[web.WebSocketResponse] = set()
        self.runner = Runner(self._evento_bot)
        self.hilo: threading.Thread | None = None
        self._listo = threading.Event()
        # lo que pide/avisa la parte de escritorio (app.py)
        self.ganchos = {"ajustes": lambda inicio=False: [], "mostrar": lambda: None, "salir": lambda: None,
                        "guardar_como": None, "bandeja_textos": lambda: None}
        # estado que la página recibe al abrir (y que sobrevive a recargarla)
        self.chat: list[dict] = []
        self.chips = {"twitch": ["", "Twitch"], "voz": ["", "Voz"]}
        self.ahora = {"texto": "", "usuario": ""}
        self.fila_n = 0
        self.novedad: dict | None = None
        self.novedad_cerrada = False
        self.descarga = None             # {"p": 0..100} mientras se descarga una actualización
        self.esperando_recompensa = False
        self._editor: dict | None = None      # audio cargado en el editor de la notificación
        self._respaldos: dict[str, Path] = {}  # respaldos subidos esperando confirmación
        self._repro_notif = Reproductor()
        self.avisos: list[str] = []      # avisos para mostrar apenas se abra la página

    # ------------------------------------------------------------ arranque
    def iniciar(self) -> int:
        self.puerto = puerto_libre()
        self.hilo = threading.Thread(target=self._correr, daemon=True, name="panel")
        self.hilo.start()
        if not self._listo.wait(15):
            raise RuntimeError("La ventana de Voxia no pudo arrancar.")
        return self.puerto

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}/"

    def _correr(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        app = self._app()
        runner = web.AppRunner(app, access_log=None)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", self.puerto).start())
        self._listo.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(runner.cleanup())

    def en_loop(self, fn, *args):
        """Ejecuta algo en el hilo del servidor (desde la bandeja, las teclas…)."""
        if self.loop:
            self.loop.call_soon_threadsafe(fn, *args)

    def cerrar(self):
        if self.runner.activo:
            self.runner.detener()
            self.runner.esperar(4)
        self._repro_notif.parar()

    # ----------------------------------------------------------- rutas
    def _app(self) -> web.Application:
        app = web.Application(client_max_size=60 * 1024 ** 2)
        r = app.router
        r.add_get("/", self.pagina)
        r.add_get("/ws", self.ws)
        r.add_get("/app/mostrar", self.mostrar)
        r.add_static("/static", WEB)
        r.add_static("/recursos", INTERNOS / "recursos")
        g, p = r.add_get, r.add_post
        g("/api/estado", self.api_estado)
        g("/api/i18n", self.api_i18n)
        p("/api/iniciar", self.api_iniciar)
        p("/api/detener", self.api_detener)
        p("/api/reiniciar", self.api_reiniciar)
        p("/api/simular", self.api_simular)
        p("/api/voz", self.api_voz)
        p("/api/notificacion", self.api_notificacion)
        p("/api/apariencia", self.api_apariencia)
        p("/api/idioma", self.api_idioma)
        p("/api/abrir", self.api_abrir)
        g("/api/lector", self.api_lector)
        p("/api/lector", self.api_lector_guardar)
        p("/api/recompensa/detectar", self.api_detectar_recompensa)
        g("/api/config", self.api_config)
        p("/api/config", self.api_config_guardar)
        p("/api/voces", self.api_voces)
        p("/api/probar_voz", self.api_probar_voz)
        g("/api/twitch/cuenta", self.api_cuenta)
        p("/api/twitch/login", self.api_login)
        p("/api/twitch/logout", self.api_logout)
        p("/api/acceso_directo", self.api_acceso_directo)
        p("/api/novedades/buscar", self.api_buscar_novedades)
        p("/api/novedades/cerrar", self.api_cerrar_novedad)
        p("/api/novedades/actualizar", self.api_actualizar)
        g("/api/notif/info", self.api_notif_info)
        p("/api/notif/escuchar", self.api_notif_escuchar)
        p("/api/notif/subir", self.api_notif_subir)
        p("/api/notif/original", self.api_notif_original)
        g("/api/notif/recorte.wav", self.api_notif_recorte)
        p("/api/notif/guardar", self.api_notif_guardar)
        p("/api/notif/defecto", self.api_notif_defecto)
        g("/api/respaldo/exportar", self.api_exportar_descarga)
        p("/api/respaldo/exportar", self.api_exportar)
        p("/api/respaldo/info", self.api_respaldo_info)
        p("/api/respaldo/importar", self.api_importar)
        app.middlewares.append(self._errores)
        return app

    @web.middleware
    async def _errores(self, request, handler):
        try:
            resp = await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            print("".join(traceback.format_exception(type(e), e, e.__traceback__)))
            return _err(e)
        if request.path.startswith(("/static", "/api", "/")) and isinstance(resp, web.StreamResponse):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    async def pagina(self, _req):
        return web.FileResponse(WEB / "panel.html")

    async def mostrar(self, _req):
        threading.Thread(target=self.ganchos["mostrar"], daemon=True).start()
        return web.Response(text="ok")

    # ------------------------------------------------------- eventos en vivo
    async def ws(self, req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        self.clientes.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clientes.discard(ws)
        return ws

    def emitir(self, ev: str, **datos):
        """Manda un evento a la(s) página(s) abierta(s). Llamar desde el hilo del servidor."""
        texto = json.dumps({"ev": ev, **datos}, ensure_ascii=False)
        for c in list(self.clientes):
            if not c.closed:
                asyncio.ensure_future(c.send_str(texto))

    def _evento_bot(self, tipo, datos):
        """Llega desde el hilo del bot: se pasa al hilo del servidor."""
        if self.loop:
            self.loop.call_soon_threadsafe(self._procesar_evento, tipo, datos)

    def _procesar_evento(self, tipo, d):
        if tipo == "chat":
            item = {"usuario": d.get("usuario", ""), "texto": d.get("texto", ""), "mod": bool(d.get("mod")),
                    "hora": time.strftime("%H:%M")}
            self._agregar_chat(item)
        elif tipo == "bot":
            self._agregar_chat({"bot": True, "usuario": nombre_bot(config_io.leer()), "texto": d.get("texto", ""),
                                "hora": time.strftime("%H:%M")})
        elif tipo == "fila":
            self.fila_n = len(d.get("items", []))
            self.emitir("fila", n=self.fila_n)
        elif tipo == "hablando":
            self.ahora = {"texto": d.get("texto") or "", "usuario": d.get("usuario") or ""}
            self.emitir("hablando", **self.ahora)
        elif tipo == "estado":
            self._estado(d.get("clave"), d.get("valor"))
        elif tipo == "recompensa":
            self._recompensa(d)
        elif tipo == "error":
            self.emitir("aviso", tipo="error", texto=d.get("texto", ""))
        elif tipo == "detenido":
            self.chips = {"twitch": ["", "Twitch"], "voz": ["", "Voz"]}
            self.ahora = {"texto": "", "usuario": ""}
            self.fila_n = 0
            self.esperando_recompensa = False
            self.emitir("estado", **{**self._estado_bot(), "activo": False})
            print("Voxia detenido.")

    def _agregar_chat(self, item):
        self.chat.append(item)
        if len(self.chat) > 400:
            del self.chat[:100]
        self.emitir("chat", **item)

    def _chip(self, clave, color, texto):
        self.chips[clave] = [color, texto]
        self.emitir("chip", clave=clave, color=color, texto=texto)

    def _estado(self, clave, valor):
        if clave == "twitch":
            if valor == "prueba":
                self._chip("twitch", "azul", "Modo prueba")
            else:
                self._chip("twitch", "ok" if valor else "warn", "Twitch" if valor else "Reconectando")
        elif clave in ("voz", "lector"):
            self._chip("voz", "ok" if valor else "", "Voz" if valor else "Voz apagada")
            self.emitir("switch", clave="voz", valor=bool(valor))
        elif clave == "notificacion":
            self.emitir("switch", clave="notificacion", valor=bool(valor))

    def _recompensa(self, d):
        try:
            config_io.guardar({"lector": {"recompensa_id": d["id"]}})
        except Exception as e:
            print(f"[Lector] No pude guardar la recompensa: {e}")
        self.esperando_recompensa = False
        self.emitir("recompensa", id=d["id"], usuario=d.get("usuario", ""))

    def _estado_bot(self) -> dict:
        return {"activo": self.runner.activo, "prueba": self.runner.prueba, "chips": self.chips,
                "ahora": self.ahora, "fila": self.fila_n}

    # --------------------------------------------------------------- estado
    async def api_estado(self, _req):
        cfg = config_io.leer()
        ap = cfg.get("app", {})
        color = ap.get("color", tema.POR_DEFECTO)
        modo = L.opciones(cfg.get("lector"))["modo_lectura"]
        return web.json_response({
            "app": APP, "version": A.version_actual(), "es_exe": ES_EXE, "windows": sys.platform == "win32",
            "idioma": idioma.actual(), "idiomas": idioma.IDIOMAS,
            "color": color, "colores": {n: list(c) for n, c in tema.COLORES.items()},
            "modo": ap.get("modo", "oscuro"),
            "voz": bool(cfg.get("lector", {}).get("activado", True)),
            "notificacion": bool(cfg.get("notificacion", {}).get("activada", False)),
            "puntos": modo == L.MODO_PUNTOS,
            "tecla_saltar": teclas_config(cfg)["saltar"] if atajos.DISPONIBLE else "",
            "tiene_token": bool(cfg.get("twitch", {}).get("token")),
            "chat": self.chat[-300:], **self._estado_bot(),
            "novedad": self.novedad if (self.novedad and not self.novedad_cerrada) else None,
            "descarga": self.descarga, "esperando_recompensa": self.esperando_recompensa,
            "avisos": self._sacar_avisos(),
        })

    def _sacar_avisos(self) -> list[str]:
        avisos, self.avisos = self.avisos[:], []
        return avisos

    async def api_i18n(self, _req):
        from bot.traducciones import EN, PT
        cod = idioma.actual()
        return web.json_response({"idioma": cod, "tabla": {"en": EN, "pt": PT}.get(cod, {})})

    # ------------------------------------------------------------ el bot
    async def api_iniciar(self, req):
        d = await req.json()
        prueba = bool(d.get("prueba"))
        if self.runner.activo:
            return _ok()
        cfg = config_io.leer()
        if not prueba and not cfg.get("twitch", {}).get("token"):
            return _ok(ir_a="twitch")
        self.runner.iniciar(prueba)
        voz = bool(cfg.get("lector", {}).get("activado", True))
        self.chips["twitch"] = ["azul", "Modo prueba"] if prueba else ["warn", "Twitch conectando"]
        self.chips["voz"] = ["ok", "Voz"] if voz else ["", "Voz apagada"]
        self.emitir("estado", **self._estado_bot())
        return _ok()

    async def api_detener(self, _req):
        self.runner.detener()
        print("Deteniendo Voxia...")
        return _ok()

    async def api_reiniciar(self, _req):
        prueba = self.runner.prueba
        if self.runner.activo:
            self.runner.detener()
            await asyncio.get_running_loop().run_in_executor(None, self.runner.esperar, 6)
        self.runner.iniciar(prueba)
        self.chips["twitch"] = ["azul", "Modo prueba"] if prueba else ["warn", "Twitch conectando"]
        self.emitir("estado", **self._estado_bot())
        return _ok()

    async def api_simular(self, req):
        d = await req.json()
        texto = str(d.get("texto", "")).strip()
        if not texto:
            return _ok()
        if not self.runner.llamar("simular", str(d.get("usuario", "")), texto, False, bool(d.get("canje"))):
            return _err(t("Primero inicia el bot (▶ Iniciar o 🧪 Modo prueba)."))
        return _ok()

    async def api_voz(self, req):
        activa = bool((await req.json()).get("activa"))
        config_io.guardar({"lector": {"activado": activa}})
        self.runner.llamar("poner_lector", activa, False)
        if self.runner.activo:
            self._chip("voz", "ok" if activa else "", "Voz" if activa else "Voz apagada")
        return _ok()

    async def api_notificacion(self, req):
        activa = bool((await req.json()).get("activa"))
        config_io.guardar({"notificacion": {"activada": activa}})
        self.runner.llamar("poner_notificacion", activa)
        return _ok()

    async def api_apariencia(self, req):
        d = await req.json()
        cambios = {}
        if d.get("color") in tema.COLORES:
            cambios["color"] = d["color"]
            self.runner.llamar("poner_color", d["color"])
        if d.get("modo") in ("oscuro", "claro"):
            cambios["modo"] = d["modo"]
        if cambios:
            config_io.guardar({"app": cambios})
        return _ok()

    async def api_idioma(self, req):
        codigo = (await req.json()).get("codigo")
        if codigo not in idioma.IDIOMAS or codigo == idioma.actual():
            return _ok()
        anterior = idioma.actual()
        cambios = {"app": {"idioma": codigo}}
        # si los textos que se dicen en voz alta son los de fábrica, pasan al idioma nuevo
        guardado = config_io.leer().get("lector", {})
        viejos, nuevos = idioma.textos_lectura(anterior), idioma.textos_lectura(codigo)
        for clave in nuevos:
            if guardado.get(clave, viejos[clave]) == viejos[clave]:
                cambios.setdefault("lector", {})[clave] = nuevos[clave]
        config_io.guardar(cambios)
        idioma.poner(codigo)
        self.runner.llamar("actualizar_lector", L.opciones(config_io.leer().get("lector")))
        threading.Thread(target=self.ganchos["bandeja_textos"], daemon=True).start()
        return _ok()

    async def api_abrir(self, req):
        url = str((await req.json()).get("url", ""))
        if url.startswith(("https://", "http://")):
            webbrowser.open(url)
        return _ok()

    # ---------------------------------------------------- opciones de leer
    async def api_lector(self, _req):
        op = L.opciones(config_io.leer().get("lector"))
        par = lambda lista: [[v, t(v)] for v in lista]
        return web.json_response({"op": op, "modos": par(L.MODOS), "unidades": par(L.UNIDADES),
                                  "filtros": par(L.FILTROS_URL), "puntos": L.MODO_PUNTOS,
                                  "activo": self.runner.activo, "esperando": self.esperando_recompensa})

    async def api_lector_guardar(self, req):
        op = (await req.json()).get("op") or {}
        limpio = {}
        base = L.LECTOR_DEFECTO
        for clave, v in op.items():
            if clave not in base or clave in L.FIJAS:
                continue
            defecto = base[clave]
            if isinstance(defecto, bool):
                v = bool(v)
            elif isinstance(defecto, int):
                try:
                    v = int(float(str(v).replace(",", ".").strip()))
                except ValueError:
                    return _err(t("«{campo}» tiene que ser un número entero.", campo=clave))
            elif isinstance(defecto, list):
                v = [str(x).strip() for x in (v or []) if str(x).strip()]
            else:
                v = str(v).strip()
            limpio[clave] = v
        config_io.guardar({"lector": limpio})
        nuevo = L.opciones(config_io.leer().get("lector"))
        self.runner.llamar("actualizar_lector", nuevo)
        self.emitir("puntos", valor=nuevo["modo_lectura"] == L.MODO_PUNTOS)
        return _ok()

    async def api_detectar_recompensa(self, _req):
        if not self.runner.activo:
            return _err(t("Primero inicia Voxia (▶ Iniciar). Después pulsa «Detectar recompensa» "
                          "y canjea la recompensa en tu chat."))
        self.runner.llamar("detectar_recompensa")
        self.esperando_recompensa = True
        return _ok()

    # --------------------------------------------------------- configuración
    def _catalogo(self) -> dict:
        salida = {}
        for pid, info in P.VOCES.items():
            salida[pid] = {
                "nombre": t(info["nombre"]), "precio": t(info.get("precio", "")) if info.get("precio") else "",
                "link": info.get("link", ""), "seccion": P.seccion_de(P.VOCES, pid, "voz"),
                "campos": [{"clave": c, "etiqueta": t(e), "tipo": tp, "defecto": dft, "ayuda": t(ay) if ay else ""}
                           for c, e, tp, dft, ay in info["campos"]]}
        return salida

    async def api_config(self, _req):
        cfg = config_io.leer()
        voz = {**VOZ_DEFECTO, **cfg.get("voz", {})}
        motor = voz.get("motor") if voz.get("motor") in P.VOCES else ""
        valores = {pid: P.config_de(cfg, P.VOCES, pid, "voz") for pid in P.VOCES}
        teclas = teclas_config(cfg)
        return web.json_response({
            "canal": cfg.get("twitch", {}).get("canal", ""),
            "tiene_token": bool(cfg.get("twitch", {}).get("token")),
            "motor": motor, "catalogo": self._catalogo(), "valores_voz": valores,
            "volumen_voz": float(voz.get("volumen", 0.9) or 0),
            "volumen_notif": float({**NOTIF_DEFECTO, **cfg.get("notificacion", {})}.get("volumen", 0.8) or 0),
            "app": ajustes_app(cfg),
            "atajos": {k: list(atajos.separar(v)) for k, v in teclas.items()},
            "teclas": [[k, t(k)] for k in ["Desactivada"] + atajos.TECLAS],
            "modificadores": [[k, t(k)] for k in atajos.MODIFICADORES],
            "atajos_disponibles": atajos.DISPONIBLE,
            "version": A.version_actual(), "es_exe": ES_EXE, "windows": sys.platform == "win32",
            "novedad": self.novedad,
        })

    async def api_config_guardar(self, req):
        d = await req.json()
        cambios = d.get("cambios") or {}
        permitidas = {"twitch": {"canal"}, "voz": None, "notificacion": {"volumen"}, "app": set(APP_DEFECTO),
                      "atajos": set(ATAJOS_DEFECTO)}
        permitidas.update({info["seccion"]: None for info in self._catalogo().values()})
        limpio: dict[str, dict] = {}
        for seccion, vals in cambios.items():
            if seccion not in permitidas or not isinstance(vals, dict):
                continue
            for clave, v in vals.items():
                if permitidas[seccion] is not None and clave not in permitidas[seccion]:
                    continue
                if seccion == "twitch" and clave == "canal":
                    v = str(v).strip().lower().lstrip("#")
                elif clave == "volumen":
                    v = round(max(0.0, min(1.0, float(v))), 2)
                elif clave == "modelo":
                    v = P.valor_id(str(v))
                elif isinstance(v, str):
                    v = v.strip()
                limpio.setdefault(seccion, {})[clave] = v
        config_io.guardar(limpio)
        print("[Config] Configuración guardada ✔")
        fallidas = await asyncio.get_running_loop().run_in_executor(None, self.ganchos["ajustes"])
        self.emitir("tecla", valor=teclas_config()["saltar"] if atajos.DISPONIBLE else "")
        return _ok(fallidas=fallidas or [], activo=self.runner.activo)

    async def api_voces(self, req):
        d = await req.json()
        pid = d.get("pid")
        if pid not in P.VOCES:
            return _err(t("Primero elige un motor de voz."))
        datos = {**P.config_de(config_io.leer(), P.VOCES, pid, "voz"), **(d.get("datos") or {})}
        try:
            lista = await P.listar_voces(pid, datos)
        except Exception as e:
            return _err(t("No pude cargar la lista:\n{error}\n\n¿Pusiste bien la API key?", error=e))
        if not lista:
            return _err(t("Este proveedor no tiene lista para cargar: escríbelo a mano."))
        return _ok(lista=lista)

    async def api_probar_voz(self, req):
        d = await req.json()
        cfg = config_io.leer()
        for seccion, vals in (d.get("cambios") or {}).items():
            cfg.setdefault(seccion, {}).update(vals)
        if cfg.get("voz", {}).get("motor") not in P.VOCES:
            return _err(t("Primero elige un motor de voz."))
        texto = str(d.get("texto") or "").strip() or t("¡Wena cabros! Soy {nombre} y así sueno, ¿cachai?",
                                                        nombre=nombre_bot(cfg))
        print("[Voz] Probando la voz por los parlantes del PC...")
        v = Voz(cfg, CARPETA / "overlay" / "audio_prueba")
        try:
            ruta = await v.generar(texto)
        except Exception as e:
            return _err(t("No pude generar la voz.\n{error}", error=e))
        if not ruta:
            return _err(t("No pude generar la voz.\n{error}", error=t("Revisa el archivo voxia.log.")))
        asyncio.ensure_future(v.reproducir_en_pc(ruta))
        return _ok()

    # ------------------------------------------------------------ Twitch
    async def api_cuenta(self, _req):
        token = config_io.leer().get("twitch", {}).get("token", "")
        if not token:
            return _ok(estado="sin")
        info = await twitch_login.cuenta_actual(token)
        if not info:
            return _ok(estado="vencida")
        return _ok(estado="ok", login=info.get("login"), dias=int(info.get("expires_in", 0)) // 86400)

    async def api_login(self, req):
        d = await req.json()
        canal = str(d.get("canal", "")).strip().lower().lstrip("#")
        config_io.guardar({"twitch": {"canal": canal}})
        client_id = config_io.leer().get("twitch", {}).get("client_id", "").strip() or twitch_login.CLIENT_ID
        try:
            info = await twitch_login.iniciar_sesion(client_id)
        except Exception as e:
            return _err(t("No se pudo iniciar sesión:\n{error}", error=e))
        return _ok(login=info.get("login"), canal=config_io.leer().get("twitch", {}).get("canal", ""))

    async def api_logout(self, _req):
        config_io.guardar({"twitch": {"token": ""}})
        return _ok()

    async def api_acceso_directo(self, _req):
        try:
            await asyncio.get_running_loop().run_in_executor(None, escritorio.crear_acceso_directo)
        except Exception as e:
            return _err(t("No pude crear el acceso directo:\n{error}", error=e))
        return _ok()

    # ------------------------------------------------------ actualizaciones
    async def buscar_novedades(self) -> dict | None:
        info = await novedades.ultima_version()
        if info and novedades.es_mas_nueva(info["version"]):
            nueva = self.novedad is None or self.novedad.get("version") != info["version"]
            self.novedad = info
            if nueva:
                self.novedad_cerrada = False
            if not self.novedad_cerrada:
                self.emitir("novedad", **info)
        return info

    async def api_buscar_novedades(self, _req):
        try:
            info = await self.buscar_novedades()
        except Exception as e:
            print(f"[Novedades] No pude revisar: {e}")
            return _ok(estado="error")
        if not info:
            return _ok(estado="nada")
        if novedades.es_mas_nueva(info["version"]):
            return _ok(estado="nueva", version=info["version"])
        return _ok(estado="al_dia")

    async def api_cerrar_novedad(self, _req):
        self.novedad_cerrada = True
        return _ok()

    async def api_actualizar(self, _req):
        info = self.novedad
        if not info:
            return _err(t("Todavía no hay versiones publicadas"))
        if not ES_EXE or not (info.get("exe") or info.get("zip")):
            webbrowser.open(info["pagina"])
            return _ok(abierta=True)
        if self.descarga:
            return _ok()
        if self.runner.activo:
            self.runner.detener()
        es_exe = bool(info.get("exe"))
        destino = Path(tempfile.gettempdir()) / f"Voxia-{info['version']}.{'exe' if es_exe else 'zip'}"
        self.descarga = {"p": 0}
        ultimo = [-1]

        def progreso(fraccion):
            pct = int(fraccion * 100)
            if pct != ultimo[0]:
                ultimo[0] = pct
                self.descarga = {"p": pct}
                self.emitir("descarga", p=pct)

        async def tarea():
            try:
                await novedades.descargar(info["exe"] or info["zip"], destino, progreso)
                preparar = novedades.preparar_exe if es_exe else novedades.preparar
                nueva = await asyncio.get_running_loop().run_in_executor(None, preparar, destino)
                novedades.aplicar_y_reiniciar(nueva)
            except Exception as e:
                self.descarga = None
                self.emitir("descarga", error=t("No pude actualizar:\n{error}\n\nPuedes descargarla a mano desde la "
                                                "página de descarga.", error=e))
                return
            self.emitir("descarga", p=100, listo=True)
            await asyncio.sleep(0.4)
            threading.Thread(target=self.ganchos["salir"], daemon=True).start()
        asyncio.ensure_future(tarea())
        return _ok()

    # ---------------------------------------------------------- notificación
    def _info_sonido(self) -> dict:
        ruta = N.asegurar_sonido()
        orig = N.original()
        if orig:
            nombre = t("Recorte de «{archivo}»", archivo=orig.name.replace("notificacion_original", t("tu archivo")))
        else:
            nombre = t("Ding (el que trae {app})", app=APP)
        return {"nombre": nombre, "dur": round(N.duracion(ruta), 1), "original": bool(orig)}

    async def api_notif_info(self, _req):
        return _ok(**self._info_sonido())

    async def api_notif_escuchar(self, req):
        d = await req.json()
        try:
            vol = float(d.get("volumen", NOTIF_DEFECTO["volumen"]))
        except (TypeError, ValueError):
            vol = NOTIF_DEFECTO["volumen"]
        self._repro_notif.parar()
        asyncio.ensure_future(self._repro_notif.reproducir(N.asegurar_sonido(), vol))
        return _ok()

    async def _abrir_editor(self, ruta: Path, es_nuevo: bool, nombre: str) -> web.Response:
        loop = asyncio.get_running_loop()
        try:
            datos, sr = await loop.run_in_executor(None, N.cargar, ruta)
        except Exception as e:
            return _err(e)
        import numpy as np
        dur = len(datos) / sr
        mn, mx = N.picos(datos, COLUMNAS_ONDA)
        tope = max(float(np.abs(mn).max()), float(np.abs(mx).max()), 1e-6)
        guardado = config_io.leer().get("notificacion", {})
        if not es_nuevo and guardado.get("recorte_fin"):
            ini = min(float(guardado.get("recorte_inicio", 0)), dur)
            fin = min(float(guardado["recorte_fin"]), dur)
        else:
            ini, fin = 0.0, min(dur, N.MAX_SEGUNDOS)
        self._editor = {"datos": datos, "sr": sr, "ruta": ruta, "es_nuevo": es_nuevo}
        return _ok(nombre=nombre, dur=round(dur, 3), ini=round(ini, 3), fin=round(fin, 3), max=N.MAX_SEGUNDOS,
                   min=N.MIN_SEGUNDOS, mn=[round(float(x) / tope, 3) for x in mn],
                   mx=[round(float(x) / tope, 3) for x in mx])

    async def api_notif_subir(self, req):
        lector = await req.multipart()
        campo = await lector.next()
        if not campo or not campo.filename:
            return _err(t("Elige el sonido de la notificación"))
        nombre = Path(campo.filename).name
        destino = Path(tempfile.gettempdir()) / f"voxia_subido_{uuid.uuid4().hex}{Path(nombre).suffix.lower()}"
        with open(destino, "wb") as f:
            while trozo := await campo.read_chunk(256 * 1024):
                f.write(trozo)
        return await self._abrir_editor(destino, True, nombre)

    async def api_notif_original(self, _req):
        orig = N.original()
        if not orig:
            return _err(t("Todavía no subes un sonido propio."))
        return await self._abrir_editor(orig, False, orig.name.replace("notificacion_original", t("tu archivo")))

    def _recorte(self, q) -> tuple[float, float, bool, bool]:
        ini = max(0.0, float(q.get("ini", 0)))
        fin = float(q.get("fin", 0))
        return ini, fin, str(q.get("fundido", "1")) in ("1", "true", "True"), \
            str(q.get("normalizar", "0")) in ("1", "true", "True")

    async def api_notif_recorte(self, req):
        if not self._editor:
            raise web.HTTPNotFound()
        ini, fin, fundido, normalizar = self._recorte(req.query)
        e = self._editor
        tmp = Path(tempfile.gettempdir()) / f"voxia_recorte_{uuid.uuid4().hex}.wav"
        try:
            N.guardar_recorte(e["datos"], e["sr"], ini, fin, tmp, fundido=fundido, normalizar=normalizar)
            cuerpo = tmp.read_bytes()
        except Exception as ex:
            return web.Response(status=400, text=str(ex))
        finally:
            tmp.unlink(missing_ok=True)
        return web.Response(body=cuerpo, content_type="audio/wav")

    async def api_notif_guardar(self, req):
        if not self._editor:
            return _err(t("Elige el sonido de la notificación"))
        ini, fin, fundido, normalizar = self._recorte(await req.json())
        e = self._editor
        N.guardar_recorte(e["datos"], e["sr"], ini, fin, N.ARCHIVO, fundido=fundido, normalizar=normalizar)
        if e["es_nuevo"]:
            N.guardar_original(e["ruta"])
            try:
                e["ruta"].unlink(missing_ok=True)
            except OSError:
                pass
        config_io.guardar({"notificacion": {"recorte_inicio": round(ini, 3), "recorte_fin": round(fin, 3)}})
        print(f"[Notificación] Guardada: {fin - ini:.2f} s ✔")
        self._editor = None
        return _ok(**self._info_sonido())

    async def api_notif_defecto(self, _req):
        for viejo in N.CARPETA.glob("notificacion_original.*"):
            viejo.unlink(missing_ok=True)
        N.crear_ding()
        return _ok(**self._info_sonido())

    # --------------------------------------------------------------- respaldo
    async def api_exportar_descarga(self, req):
        con = req.query.get("claves") == "1"
        tmp = Path(tempfile.gettempdir()) / f"voxia_respaldo_{uuid.uuid4().hex}.zip"
        respaldo.exportar(tmp, con_claves=con)
        cuerpo = tmp.read_bytes()
        tmp.unlink(missing_ok=True)
        nombre = f"voxia-respaldo-{time.strftime('%Y-%m-%d')}.zip"
        return web.Response(body=cuerpo, content_type="application/zip",
                            headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    async def api_exportar(self, req):
        """En la ventana de escritorio: pregunta dónde guardar con el diálogo de Windows."""
        d = await req.json()
        elegir = self.ganchos.get("guardar_como")
        if not elegir:
            return _ok(descargar=True)
        nombre = f"voxia-respaldo-{time.strftime('%Y-%m-%d')}.zip"
        ruta = await asyncio.get_running_loop().run_in_executor(None, elegir, nombre)
        if not ruta:
            return _ok(cancelado=True)
        respaldo.exportar(Path(ruta), con_claves=bool(d.get("claves")))
        return _ok(ruta=str(ruta))

    async def api_respaldo_info(self, req):
        lector = await req.multipart()
        campo = await lector.next()
        if not campo:
            return _err(t("Elige un respaldo de {app}", app=APP))
        tmp = Path(tempfile.gettempdir()) / f"voxia_importar_{uuid.uuid4().hex}.zip"
        with open(tmp, "wb") as f:
            while trozo := await campo.read_chunk(256 * 1024):
                f.write(trozo)
        try:
            info = respaldo.leer_info(tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return _err(t("No pude usar ese archivo:\n{error}", error=e))
        clave = uuid.uuid4().hex
        self._respaldos[clave] = tmp
        return _ok(clave=clave, fecha=info.get("fecha", "?"), version=info.get("version", "?"))

    async def api_importar(self, req):
        if self.runner.activo:
            return _err(t("Primero detén el bot (■ Detener) y vuelve a intentarlo."))
        clave = (await req.json()).get("clave", "")
        ruta = self._respaldos.pop(clave, None)
        if not ruta or not ruta.exists():
            return _err(t("Elige un respaldo de {app}", app=APP))
        try:
            respaldo.importar(ruta)
        except Exception as e:
            return _err(t("No pude importar:\n{error}", error=e))
        finally:
            ruta.unlink(missing_ok=True)
        idioma.poner(idioma.de_config(config_io.leer()))
        await asyncio.get_running_loop().run_in_executor(None, self.ganchos["ajustes"])
        threading.Thread(target=self.ganchos["bandeja_textos"], daemon=True).start()
        return _ok()

    # -------------------------------------------- desde la bandeja / teclas
    def atajo(self, accion: str):
        if accion in ("saltar", "callar"):
            self.runner.llamar(accion)
        print(f"[Teclas] {accion}")

    def iniciar_bot(self, prueba: bool = False) -> bool:
        cfg = config_io.leer()
        if self.runner.activo or (not prueba and not cfg.get("twitch", {}).get("token")):
            return False
        self.runner.iniciar(prueba)
        voz = bool(cfg.get("lector", {}).get("activado", True))
        self.chips["twitch"] = ["azul", "Modo prueba"] if prueba else ["warn", "Twitch conectando"]
        self.chips["voz"] = ["ok", "Voz"] if voz else ["", "Voz apagada"]
        self.en_loop(lambda: self.emitir("estado", **self._estado_bot()))
        return True
