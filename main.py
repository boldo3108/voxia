"""
Voxia — lee el chat de Twitch en voz alta
La forma fácil de usarlo es la app:  VOXIA.bat  (o  python app.py)
Desde consola:  python main.py           (modo stream, conectado a Twitch)
                python main.py --prueba  (modo prueba, escribes tú en la consola)
"""
import asyncio
import sys
import time
from pathlib import Path

from bot import config_io, idioma, notificacion, tema
from bot import lector as L
from bot.fila import Fila, Item
from bot.idioma import t
from bot.overlay import Overlay
from bot.reproductor import Reproductor
from bot.twitch import ChatDePrueba, Mensaje, Twitch
from bot.voz import Voz

from bot.rutas import CARPETA

RECOMPENSA_PRUEBA = "prueba-voxia"     # id de recompensa de los canjes simulados en Modo prueba

LECTOR_DEFECTO = L.LECTOR_DEFECTO     # todas las Opciones de leer (ver bot/lector.py)


NOTIF_DEFECTO = {
    "activada": False,   # suena cada vez que alguien escribe; si también se lee, la voz espera a que termine
    "volumen": 0.8,
}


def nombre_bot(cfg: dict) -> str:
    nombre = cfg.get("bot", {}).get("nombre") or cfg.get("ia", {}).get("nombre") or "Voxia"
    return "Voxia" if nombre == "BoldoBot" else nombre      # el nombre antiguo de la app


class BoldoBot:
    def __init__(self, cfg: dict, modo_prueba: bool = False, consola: bool = True, eventos=None,
                 plataformas=("twitch",)):
        self.cfg = cfg
        self.lector = L.opciones(cfg.get("lector"))
        self.emotes_ext: dict[str, set] = {}          # emotes de BTTV / FFZ / 7TV
        self.voces_usuarios = L.VocesUsuarios()
        self._ultimo_hablante: tuple[str, float] = ("", 0.0)
        self._recientes: list[tuple[str, float]] = []   # (texto normalizado, cuándo) para el anti-spam
        self._esperando_recompensa: set[str] = set()   # «Detectar recompensa» de la app (por plataforma)
        self.notif = {**NOTIF_DEFECTO, **cfg.get("notificacion", {})}
        self.notif_repro = Reproductor()
        self._notif_desde = (0.0, 0.0)       # (cuándo empezó a sonar, cuánto dura) la última notificación
        notificacion.asegurar_sonido()
        self.nombre = nombre_bot(cfg)
        self.prueba = modo_prueba
        self.eventos = eventos or (lambda tipo, **datos: None)   # la app recibe aquí lo que pasa
        self.consola = consola
        # chats conectados: "twitch" (o "prueba" en Modo prueba)
        self.chats: dict = {}
        self._tareas_chat: dict[str, asyncio.Task] = {}
        self._ya_arranco = False
        self._iniciales = ["prueba"] if modo_prueba else [p for p in plataformas if p == "twitch"]
        self.voz = Voz(cfg, CARPETA / "overlay" / "audio")
        ov = cfg.get("overlay", {})
        self.overlay = Overlay(CARPETA / "overlay", int(ov.get("puerto", 8765)), int(ov.get("tiempo_visible", 6)),
                               self.nombre)
        if self.overlay:
            self.overlay.al_cambiar = lambda n: self.emitir("estado", clave="overlay", valor=n)
            self.overlay.colores = tema.colores(cfg.get("app", {}).get("color", tema.POR_DEFECTO))

        self.fila = Fila(int(self.lector["fila_maxima"]), al_cambiar=self._fila_cambio)
        self.actual: Item | None = None
        self._cancelado = False
        self.cooldowns: dict[str, float] = {}
        self.ultimo_global = 0.0
        self.lector_activo = bool(self.lector["activado"])
        self.pausado = False
        self._reanudar = asyncio.Event()
        self._reanudar.set()

    # --------------------------------------------------------------- eventos
    def emitir(self, tipo: str, **datos):
        try:
            self.eventos(tipo, **datos)
        except Exception as e:
            print(f"[App] Error mostrando evento: {e}")

    def _fila_cambio(self):
        self.emitir("fila", items=[(it.id, it.tipo, it.usuario, it.texto) for it in self.fila.items])

    async def enviar(self, texto: str, plataforma: str | None = None):
        """Escribe en el chat de esa plataforma (o en todos si no se dice cuál)."""
        destinos = [self.chats[plataforma]] if plataforma in self.chats else (
            list(self.chats.values()) if plataforma is None else [])
        for chat in destinos:
            await chat.enviar(texto)
        if destinos:
            self.emitir("bot", texto=texto)

    # ------------------------------------------------------------- plataformas
    def _crear_chat(self, p: str):
        if p == "prueba":
            chat = ChatDePrueba(self.al_recibir, consola=self.consola)
        elif p == "twitch":
            chat = Twitch(self.cfg["twitch"]["canal"], self.cfg["twitch"]["token"], self.al_recibir)
        else:
            raise ValueError(p)
        clave = "twitch" if p == "prueba" else p
        chat.al_estado = lambda ok, c=clave: self.emitir("estado", clave=c, valor=ok)
        chat.al_moderacion = lambda tipo, login, msg_id, pl=getattr(chat, "plataforma", "twitch"): \
            self._moderacion(pl, tipo, login, msg_id)
        return chat

    async def agregar_plataforma(self, p: str):
        """Conecta una plataforma con el bot ya funcionando."""
        if p in self.chats:
            return
        chat = self._crear_chat(p)
        await chat.preparar()
        self.chats[p] = chat
        self._tareas_chat[p] = asyncio.create_task(chat.conectar_para_siempre())
        self.emitir("plataforma", nombre=p, activa=True)
        if p == "prueba":
            self.emitir("estado", clave="twitch", valor="prueba")
        elif self._ya_arranco:                     # se agregó con el bot funcionando: sus emotes
            asyncio.create_task(self._cargar_emotes())

    async def agregar_desde_app(self, p: str):
        try:
            await self.agregar_plataforma(p)
        except Exception as e:
            print(f"[{p}] No pude conectar: {e}")
            self.emitir("plataforma", nombre=p, activa=False)
            self.emitir("error", texto=str(e))

    async def quitar_plataforma(self, p: str):
        tarea, chat = self._tareas_chat.pop(p, None), self.chats.pop(p, None)
        if tarea:
            tarea.cancel()
        if chat:
            await chat.cerrar()
        self.emitir("plataforma", nombre=p, activa=False)

    @property
    def pendientes(self) -> set[str]:
        """Usuarios que ya tienen un mensaje esperando o sonando."""
        quienes = {it.msg.login for it in self.fila.items if it.msg}
        if self.actual and self.actual.msg:
            quienes.add(self.actual.msg.login)
        return quienes

    # ------------------------------------------------------------------ inicio
    async def correr(self):
        print("=" * 56)
        print(f"  {self.nombre} arrancando {'(MODO PRUEBA)' if self.prueba else ''}")
        print("=" * 56)
        try:
            errores = []
            for p in self._iniciales:
                try:
                    await self.agregar_plataforma(p)
                except Exception as e:
                    errores.append(e)
                    self.emitir("plataforma", nombre=p, activa=False)
            if errores and not self.chats:
                raise errores[0]                     # no se pudo conectar a nada
            for e in errores:
                self.emitir("error", texto=str(e))
            if self.overlay:
                await self.overlay.iniciar()
                self.emitir("estado", clave="overlay", valor=0)
            comandos = " ".join(self.lector["comandos_hablar"])
            print(f"[Lector] {'Leyendo todo el chat' if self.lector['decir_todo'] else 'Solo leo comandos'} "
                  f"· comandos para hablar: {comandos or '(ninguno)'} ✔")
            self._ya_arranco = True
            await asyncio.gather(self.trabajador(), self._cargar_emotes())
        finally:
            for p in list(self.chats):
                tarea = self._tareas_chat.pop(p, None)
                if tarea:
                    tarea.cancel()
                try:
                    await self.chats.pop(p).cerrar()
                except Exception:
                    pass
            if self.overlay:
                await self.overlay.detener()

    async def _cargar_emotes(self):
        op = self.lector
        if not any(op[f"ignorar_emotes_{k}"] for k in ("bttv", "ffz", "7tv")):
            return
        canal_id = getattr(self.chats.get("twitch"), "broadcaster_id", "")
        self.emotes_ext = await L.cargar_emotes_terceros(canal_id)
        print("[Lector] Emotes cargados: " + " · ".join(f"{k.upper()} {len(v)}" for k, v in self.emotes_ext.items()))

    # ------------------------------------------------------------ cada mensaje
    async def al_recibir(self, msg: Mensaje):
        print(f"[{msg.plataforma}] {msg.usuario}: {msg.texto}")
        self.emitir("chat", usuario=msg.usuario, texto=msg.texto, mod=msg.es_mod, plataforma=msg.plataforma)

        op = self.lector
        if msg.plataforma == "twitch" and op["ignorar_chat_compartido"] and L.es_chat_compartido(msg):
            return

        if self.notif["activada"] and not self._es_ignorado(msg):
            asyncio.create_task(self.sonar_notificacion(esperar=False))   # cada vez que alguien escribe

        texto = msg.texto.strip()
        if msg.recompensa_id and msg.plataforma in self._esperando_recompensa:   # la app espera un canje
            self._esperando_recompensa.discard(msg.plataforma)
            op["recompensa_id"] = msg.recompensa_id
            self.emitir("recompensa", id=msg.recompensa_id, usuario=msg.usuario, plataforma=msg.plataforma)
            print(f"[Lector] Recompensa de {msg.plataforma} detectada ✔ ({msg.recompensa_id})")
        primera, _, resto = texto.partition(" ")
        primera = primera.lower()
        if op["prefijo_comandos"] and primera == op["prefijo_comandos"].strip().lower():
            await self.control(msg, resto.strip().lower())
            return
        if L.es_canje(msg, op):                                    # canje de puntos del canal
            await self.leer(msg, texto, canje=True)
            return
        if L.modo(msg, op) == L.MODO_PUNTOS:                      # solo se leen los canjes
            return
        if primera in {c.strip().lower() for c in op["comandos_hablar"] if c.strip()}:
            if op["permitir_forzados"] and resto.strip():
                await self.leer(msg, resto.strip(), forzado=True)
            return
        if not op["decir_todo"]:
            return
        if op["ignorar_prefijos"] and any(p and texto.startswith(p) for p in op["prefijos_ignorados"]):
            return
        await self.leer(msg, texto)

    async def simular(self, usuario: str, texto: str, mod: bool = False, canje: bool = False,
                      plataforma: str = "twitch"):
        """Mensaje de prueba escrito desde la app (no pasa por Twitch). canje = como si canjeara puntos."""
        usuario = usuario.strip() or "viewer_prueba"
        rid = RECOMPENSA_PRUEBA if canje else ""
        await self.al_recibir(Mensaje(usuario=usuario, login=usuario.lower(), texto=texto.strip(),
                                      id=f"prueba-{time.monotonic_ns()}",
                                      badges={"moderator"} if mod else set(),
                                      recompensa_id=rid, plataforma=plataforma))

    def detectar_recompensa(self, plataforma: str = "twitch"):
        """El próximo canje de puntos con texto que llegue (de esa plataforma) queda como «la recompensa»."""
        self._esperando_recompensa.add(plataforma)
        print(f"[Lector] Esperando un canje de {plataforma} para detectar la recompensa...")

    # ---------------------------------------------------------------- comandos
    async def responder(self, texto: str, plataforma: str = "twitch"):
        """Escribe en el chat de esa plataforma, salvo que «Silenciar respuestas de comandos» esté activo."""
        if not self.lector["silenciar_respuestas"]:
            await self.enviar(texto, "prueba" if "prueba" in self.chats else plataforma)

    async def control(self, msg: Mensaje, orden: str):
        """Comandos de mods: <prefijo> skip · callar · off · on   (ej: !voz skip)."""
        if not msg.es_mod:
            return
        if orden in ("skip", "saltar"):
            await self.saltar()
        elif orden in ("callar", "callate", "clear", "limpiar"):
            await self.callar()
        elif orden in ("off", "apagar"):
            await self.poner_lector(False, plataforma=msg.plataforma)
        elif orden in ("on", "prender"):
            await self.poner_lector(True, plataforma=msg.plataforma)

    # ------------------------------------------------------------- el lector
    async def leer(self, msg: Mensaje, texto: str, forzado: bool = False, canje: bool = False):
        """Limpia el mensaje y lo pone en la fila para leerlo en voz alta.
        canje = canje de puntos: no pasa por permisos, «una por persona» ni cooldown."""
        op = self.lector
        if not self.lector_activo or self._es_ignorado(msg):
            return
        if not canje and not L.puede_hablar(msg, op):
            if forzado and op["texto_no_permitido"].strip():
                await self.responder(f"@{msg.usuario} {op['texto_no_permitido'].strip()}", msg.plataforma)
            return
        if op["usar_palabras_prohibidas"]:
            mala = L.palabra_prohibida(texto, op["palabras_prohibidas"])
            if mala:
                print(f"  [Lector] No leo a {msg.usuario}: tiene una palabra prohibida («{mala}»)")
                return
        limpio = L.limpiar(msg, texto, op, self.emotes_ext)
        if not limpio:
            return
        if op["no_repetidos"]:
            ahora, clave = time.monotonic(), L.normalizar(limpio)
            ventana = float(op["segundos_repetidos"] or 0)
            self._recientes = [(k, c) for k, c in self._recientes if ahora - c < ventana]
            if clave and any(k == clave for k, _ in self._recientes):
                print(f"  [Lector] Mensaje repetido, no lo leo: {msg.usuario}: {limpio[:40]}")
                return
            self._recientes.append((clave, ahora))
        if not msg.es_mod and not canje:
            if op["una_por_persona"] and msg.login in self.pendientes:
                print(f"  [Lector] {msg.usuario} ya tiene un mensaje en la fila")
                return
            espera = float(op["cooldown_por_usuario"]) - (time.monotonic() - self.cooldowns.get(msg.login, -1e9))
            if espera > 0:
                print(f"  [Lector] {msg.usuario} en cooldown ({int(espera)}s)")
                return
        if not self.fila.agregar(Item("chat", usuario=msg.usuario, texto=limpio, msg=msg, al_chat=False)):
            print("  [Lector] Fila llena, me salto el mensaje")

    def _moderacion(self, plataforma: str, tipo: str, login: str, msg_id: str | None):
        """Si un mod borra un mensaje o da timeout/ban, ese mensaje no se lee (y se corta si está sonando)."""
        op = self.lector
        if not op.get({"borrado": "saltar_borrado", "timeout": "saltar_timeout", "ban": "saltar_ban"}[tipo]):
            return

        def coincide(it):
            if not it or not it.msg or it.msg.plataforma != plataforma:
                return False
            return it.msg.id == msg_id if tipo == "borrado" else it.msg.login == login
        for it in [i for i in self.fila.items if coincide(i)]:
            self.fila.quitar(it.id)
            print(f"  [Lector] Saltado ({tipo}): {it.usuario}: {it.texto[:40]}")
        if coincide(self.actual):
            print(f"  [Lector] Cortado ({tipo}): {self.actual.usuario}")
            asyncio.create_task(self.saltar())

    # ---------------------------------------------------------- notificación
    def _es_ignorado(self, msg: Mensaje) -> bool:
        propio = getattr(self.chats.get(msg.plataforma) or self.chats.get("prueba"), "login", "")
        return msg.login in {u.lower() for u in self.lector["ignorar"]} or (bool(propio) and msg.login == propio)

    async def sonar_notificacion(self, esperar: bool = True):
        ruta = notificacion.asegurar_sonido()
        vol = float(self.notif.get("volumen", 0.8))
        dur = notificacion.duracion(ruta)
        self._notif_desde = (time.monotonic(), dur)
        try:
            if esperar:                       # suena siempre por el PC
                await self.notif_repro.reproducir(ruta, vol)
            else:
                asyncio.create_task(self.notif_repro.reproducir(ruta, vol))
        except Exception as e:
            print(f"[Notificación] No pude sonar: {e}")

    async def parar_notificacion(self):
        self.notif_repro.parar()
        if self.overlay and self.overlay.conectado:
            await self.overlay.parar_sonido()

    def poner_notificacion(self, activa: bool):
        self.notif["activada"] = activa
        self.emitir("estado", clave="notificacion", valor=activa)
        print(f"[Notificación] {'Activada' if activa else 'Desactivada'}")

    # ------------------------------------------------------ controles (app/mods)
    async def poner_lector(self, activo: bool, avisar_chat: bool = True, plataforma: str = "twitch"):
        self.lector_activo = activo
        self.emitir("estado", clave="lector", valor=activo)
        if not activo:
            await self.callar()
            if avisar_chat:
                await self.responder(t("Ya, me quedo calladito 🤐 (un mod usa {cmd} on para que vuelva a leer)",
                                       cmd=self.lector["prefijo_comandos"]), plataforma)
        elif avisar_chat:
            await self.responder(t("¡Volví a leer el chat, po! 😎"), plataforma)

    async def saltar(self):
        """Corta lo que está diciendo ahora, pero deja la fila."""
        self._cancelado = True
        self.voz.callar()
        self.notif_repro.parar()
        if self.overlay:
            await self.overlay.ocultar()

    async def callar(self):
        """Corta lo que está diciendo y vacía la fila."""
        self.fila.vaciar()
        await self.saltar()

    def pausar(self, pausado: bool):
        self.pausado = pausado
        self._reanudar.clear() if pausado else self._reanudar.set()
        self.emitir("estado", clave="pausa", valor=pausado)
        print(f"[Fila] {'En pausa: no hablará hasta que la reanudes' if pausado else 'Reanudada'}")

    async def decir(self, texto: str, al_chat: bool = True):
        """Hace que Voxia diga una frase exacta. Pasa adelante en la fila."""
        texto = texto.strip()
        if texto:
            self.fila.agregar(Item("decir", usuario="(tú)", texto=texto, al_chat=al_chat), prioridad=True)

    def quitar_de_fila(self, item_id: int):
        it = self.fila.quitar(item_id)
        if it:
            print(f"[Fila] Quitada: {it.usuario or it.tipo}: {it.texto[:50]}")

    def poner_color(self, nombre: str):
        if self.overlay:
            self.overlay.colores = tema.colores(nombre)

    def poner_voz(self, activa: bool):
        self.cfg["voz"]["activada"] = activa
        self.emitir("estado", clave="voz", valor=activa)

    # --------------------------------------------------------------- la fila
    async def trabajador(self):
        """Lee la fila de a uno (así las voces no se pisan)."""
        while True:
            await self._reanudar.wait()
            item = await self.fila.sacar()
            if self.pausado:                       # se pausó mientras esperaba: lo devuelvo
                self.fila.agregar(item, prioridad=True)
                continue
            espera = float(self.lector["pausa_entre_mensajes"]) - (time.monotonic() - self.ultimo_global)
            if espera > 0 and item.tipo != "decir":
                await asyncio.sleep(espera)
            self.actual = item
            self._cancelado = False
            try:
                await self.atender(item)
            except Exception as e:
                print(f"  [Voz] Error: {e}")
            finally:
                if item.msg:
                    self.cooldowns[item.msg.login] = time.monotonic()
                self.actual = None
                self.emitir("hablando", texto="")
            self.ultimo_global = time.monotonic()

    def _texto_hablado(self, item: Item) -> str:
        """Arma lo que se dice: «nombre dice: mensaje», respetando las opciones de habla."""
        if item.tipo != "chat" or not item.msg:
            return item.texto
        op, ahora = self.lector, time.monotonic()
        login = item.msg.login
        decir_nombre = op["decir_usuario"]
        anterior, cuando = self._ultimo_hablante
        if decir_nombre and op["usuario_solo_si_cambia"] and anterior == login:
            gracia = float(op["gracia_segundos"] or 0)
            if gracia <= 0 or ahora - cuando < gracia:
                decir_nombre = False
        self._ultimo_hablante = (login, ahora)
        if not decir_nombre:
            return item.texto
        nombre = L.apodo(item.msg, op)
        sufijo = op["sufijo_usuario"].strip()
        return f"{nombre} {sufijo}: {item.texto}" if sufijo else f"{nombre}: {item.texto}"

    async def atender(self, item: Item):
        hablado = self._texto_hablado(item)
        self.emitir("hablando", texto=item.texto, usuario=item.usuario)
        if item.tipo == "decir" and item.al_chat:
            await self.enviar(item.texto)

        cvoz = self.cfg["voz"]
        voz_usuario = None
        if item.tipo == "chat" and item.msg and self.lector["voz_aleatoria"] and self.voz.motor == "edge":
            voz_usuario = self.voces_usuarios.de(item.msg.login)
        quitar_emojis = item.tipo != "chat"       # en el chat ya lo decide «Ignorar emojis»
        audio = await self.voz.generar(hablado, voz=voz_usuario, quitar_emojis=quitar_emojis) \
            if cvoz.get("activada", True) else None
        if self._cancelado:
            return
        inicio, dur = self._notif_desde              # si está sonando la notificación, la voz espera a que termine
        espera = dur - (time.monotonic() - inicio)
        if espera > 0:
            await asyncio.sleep(espera)
        if self._cancelado:
            return
        overlay_suena = False                 # la voz suena siempre por el PC (el overlay solo muestra el globo)

        if self.overlay and self.overlay.conectado:
            url = f"/archivos/audio/{audio.name}" if audio else None
            titulo = item.usuario if item.tipo == "chat" else self.nombre
            tarea_overlay = self.overlay.hablar(titulo, item.texto, url,
                                                esperar_audio=overlay_suena and audio is not None)
        else:
            tarea_overlay = asyncio.sleep(0)

        if audio and not overlay_suena:
            await asyncio.gather(tarea_overlay, self.voz.reproducir_en_pc(audio))
        else:
            await tarea_overlay

    def actualizar_lector(self, opciones: dict):
        """Aplica al tiro las Opciones de leer guardadas en la app."""
        self.lector = L.opciones(opciones)
        self.fila.maximo = int(self.lector["fila_maxima"])
        self.lector_activo = bool(self.lector["activado"])
        self.emitir("estado", clave="lector", valor=self.lector_activo)
        print("[Lector] Opciones de leer actualizadas ✔")


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    prueba = "--prueba" in sys.argv
    try:
        cfg = config_io.leer()
        idioma.poner(idioma.de_config(cfg))
        if not prueba and not cfg["twitch"].get("token"):
            raise RuntimeError(t("Falta el token de Twitch. Ejecuta primero OBTENER_TOKEN.bat"))
        asyncio.run(BoldoBot(cfg, modo_prueba=prueba).correr())
    except KeyboardInterrupt:
        print("\n¡Chao! Voxia apagado.")
    except RuntimeError as e:
        print(f"\n❌ {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
