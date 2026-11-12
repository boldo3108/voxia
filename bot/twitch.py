"""Conexión al chat de Twitch (IRC seguro) y a la API de moderación (Helix)."""
import asyncio
import ssl
import time
from dataclasses import dataclass, field

import aiohttp
from bot.idioma import t

IRC_HOST = "irc.chat.twitch.tv"
IRC_PORT = 6697  # puerto seguro (SSL)
HELIX = "https://api.twitch.tv/helix"


@dataclass
class Mensaje:
    usuario: str          # nombre visible (ej: "Boldo3108")
    login: str            # nombre en minúsculas
    texto: str
    id: str = ""
    user_id: str = ""
    room_id: str = ""
    badges: set = field(default_factory=set)
    emotes: str = ""          # posiciones de los emotes de Twitch (tag «emotes»)
    bits: int = 0             # bits del mensaje (cheer)
    source_room_id: str = ""  # canal de origen (chat compartido)
    recompensa_id: str = ""   # canje de puntos del canal con texto (tag «custom-reward-id»)
    plataforma: str = "twitch"

    @property
    def es_mod(self) -> bool:
        return bool(self.badges & {"broadcaster", "moderator"})

    @property
    def es_vip(self) -> bool:
        return self.es_mod or "vip" in self.badges


def _desescapar(valor: str) -> str:
    return (valor.replace(r"\s", " ").replace(r"\:", ";")
                 .replace(r"\r", "").replace(r"\n", "").replace("\\\\", "\\"))


def parsear_linea(linea: str):
    """Convierte una línea IRC de Twitch en (tags, comando, canal, texto, prefijo)."""
    tags = {}
    if linea.startswith("@"):
        crudo, linea = linea[1:].split(" ", 1)
        for par in crudo.split(";"):
            k, _, v = par.partition("=")
            tags[k] = _desescapar(v)
    prefijo = ""
    if linea.startswith(":"):
        prefijo, linea = linea[1:].split(" ", 1)
    texto = ""
    if " :" in linea:
        linea, texto = linea.split(" :", 1)
    partes = linea.split()
    comando = partes[0] if partes else ""
    canal = partes[1] if len(partes) > 1 else ""
    return tags, comando, canal, texto, prefijo


async def validar_token(token: str) -> dict:
    """Pregunta a Twitch a quién pertenece el token y cuánto le queda."""
    async with aiohttp.ClientSession() as s:
        async with s.get("https://id.twitch.tv/oauth2/validate",
                         headers={"Authorization": f"OAuth {token}"}) as r:
            if r.status != 200:
                raise RuntimeError(t("La sesión de Twitch no es válida o venció. Ve a Configuración → Twitch → «Iniciar sesión con Twitch»."))
            return await r.json()


class Twitch:
    def __init__(self, canal: str, token: str, al_recibir):
        self.canal = canal.lower().lstrip("#")
        self.token = token.removeprefix("oauth:")
        self.al_recibir = al_recibir           # async def f(Mensaje)
        self.login = ""
        self.user_id = ""
        self.client_id = ""
        self.broadcaster_id = ""
        self.scopes: list[str] = []
        self._writer = None
        self._ultimo_envio = 0.0
        self._lock_envio = asyncio.Lock()
        self._http: aiohttp.ClientSession | None = None
        self.al_estado = lambda conectado: None   # la app lo reemplaza para mostrar el estado
        # avisos de moderación: ("borrado", login, msg_id) · ("timeout", login, None) · ("ban", login, None)
        self.al_moderacion = lambda tipo, login, msg_id: None

    async def preparar(self):
        info = await validar_token(self.token)
        self.login = info["login"]
        self.user_id = info["user_id"]
        self.client_id = info["client_id"]
        self.scopes = info.get("scopes", [])
        dias = info.get("expires_in", 0) // 86400
        print(f"[Twitch] Token OK: cuenta '{self.login}', vence en ~{dias} días.")
        faltan = {"chat:read", "chat:edit"} - set(self.scopes)
        if faltan:
            raise RuntimeError(t("A la sesión de Twitch le faltan permisos ({faltan}). Vuelve a «Iniciar sesión con Twitch».", faltan=faltan))
        self._http = aiohttp.ClientSession(headers={
            "Authorization": f"Bearer {self.token}", "Client-Id": self.client_id})
        # ID del canal (para moderar)
        async with self._http.get(f"{HELIX}/users", params={"login": self.canal}) as r:
            datos = (await r.json()).get("data", [])
            if not datos:
                raise RuntimeError(t("No encontré el canal «{canal}» en Twitch.", canal=self.canal))
            self.broadcaster_id = datos[0]["id"]

    # ---------------- chat ----------------
    async def conectar_para_siempre(self):
        espera = 2
        while True:
            try:
                await self._sesion()
                espera = 2
            except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
                self.al_estado(False)
                print(f"[Twitch] Conexión perdida ({e}). Reintentando en {espera}s...")
            await asyncio.sleep(espera)
            espera = min(espera * 2, 60)

    async def _sesion(self):
        reader, writer = await asyncio.open_connection(
            IRC_HOST, IRC_PORT, ssl=ssl.create_default_context())
        self._writer = writer
        self._raw(f"PASS oauth:{self.token}")
        self._raw(f"NICK {self.login}")
        self._raw("CAP REQ :twitch.tv/tags twitch.tv/commands")
        self._raw(f"JOIN #{self.canal}")
        await writer.drain()
        try:
            while True:
                datos = await reader.readline()
                if not datos:
                    raise ConnectionError("Twitch cerró la conexión")
                linea = datos.decode("utf-8", errors="ignore").rstrip("\r\n")
                await self._procesar(linea)
        finally:
            self._writer = None
            writer.close()

    async def _procesar(self, linea: str):
        if linea.startswith("PING"):
            self._raw("PONG" + linea[4:])
            return
        tags, comando, canal, texto, prefijo = parsear_linea(linea)
        if comando == "001":
            print(f"[Twitch] Conectado al chat de #{self.canal} como {self.login} ✔")
            self.al_estado(True)
        elif comando == "NOTICE" and "Login authentication failed" in texto:
            raise RuntimeError(t("Twitch rechazó el inicio de sesión. Vuelve a «Iniciar sesión con Twitch»."))
        elif comando == "RECONNECT":
            raise ConnectionError("Twitch pidió reconectar")
        elif comando == "CLEARMSG":
            self.al_moderacion("borrado", tags.get("login", ""), tags.get("target-msg-id", ""))
        elif comando == "CLEARCHAT" and texto:
            self.al_moderacion("timeout" if tags.get("ban-duration") else "ban", texto.strip().lower(), None)
        elif comando == "PRIVMSG":
            login = prefijo.split("!", 1)[0]
            if login == self.login:
                return  # ignorar mis propios mensajes
            badges = {b.split("/")[0] for b in tags.get("badges", "").split(",") if b}
            if texto.startswith("\x01ACTION ") and texto.endswith("\x01"):   # mensajes /me
                texto = texto[8:-1]
            msg = Mensaje(usuario=tags.get("display-name") or login, login=login,
                          texto=texto, id=tags.get("id", ""), user_id=tags.get("user-id", ""),
                          room_id=tags.get("room-id", ""), badges=badges, emotes=tags.get("emotes", ""),
                          bits=int(tags.get("bits") or 0), source_room_id=tags.get("source-room-id", ""),
                          recompensa_id=tags.get("custom-reward-id", ""))
            asyncio.create_task(self.al_recibir(msg))

    def _raw(self, linea: str):
        if self._writer:
            self._writer.write((linea + "\r\n").encode("utf-8"))

    async def enviar(self, texto: str, responder_a: str = ""):
        """Envía un mensaje al chat respetando el límite de velocidad de Twitch."""
        texto = " ".join(texto.split())[:480]
        if not texto or not self._writer:
            return
        async with self._lock_envio:
            espera = 1.6 - (time.monotonic() - self._ultimo_envio)
            if espera > 0:
                await asyncio.sleep(espera)
            tag = f"@reply-parent-msg-id={responder_a} " if responder_a else ""
            self._raw(f"{tag}PRIVMSG #{self.canal} :{texto}")
            await self._writer.drain()
            self._ultimo_envio = time.monotonic()

    # ---------------- moderación ----------------
    async def borrar_mensaje(self, msg: Mensaje) -> bool:
        if not msg.id or not msg.user_id or "moderator:manage:chat_messages" not in self.scopes:
            return False
        async with self._http.delete(f"{HELIX}/moderation/chat", params={
                "broadcaster_id": self.broadcaster_id, "moderator_id": self.user_id,
                "message_id": msg.id}) as r:
            if r.status not in (200, 204):
                print(f"[Moderación] No pude borrar ({r.status}). ¿El bot es mod del canal?")
            return r.status in (200, 204)

    async def timeout(self, msg: Mensaje, segundos: int, motivo: str) -> bool:
        if not msg.user_id or "moderator:manage:banned_users" not in self.scopes:
            return False
        async with self._http.post(f"{HELIX}/moderation/bans", params={
                "broadcaster_id": self.broadcaster_id, "moderator_id": self.user_id},
                json={"data": {"user_id": msg.user_id, "duration": segundos, "reason": motivo}}) as r:
            if r.status != 200:
                print(f"[Moderación] No pude dar timeout ({r.status}).")
            return r.status == 200

    async def cerrar(self):
        if self._http:
            await self._http.close()


class ChatDePrueba:
    """Reemplaza a Twitch en modo prueba: escribes como si fueras un viewer
    (en la consola, o desde la app de escritorio)."""

    def __init__(self, al_recibir, consola: bool = True):
        self.al_recibir = al_recibir
        self.login = "voxia"
        self.consola = consola
        self.al_estado = lambda conectado: None
        self.al_moderacion = lambda tipo, login, msg_id: None

    async def preparar(self):
        if self.consola:
            print("\n[Prueba] Modo prueba: escribe mensajes como si fueras del chat.")
            print("[Prueba] Formato opcional  usuario: mensaje   (ej:  pepito: hola bot)")
            print("[Prueba] Empieza con 'mod ' para hablar como moderador. Ctrl+C para salir.\n")
        else:
            print("[Prueba] Modo prueba: escribe en la caja de abajo como si fueras del chat.")

    async def conectar_para_siempre(self):
        if not self.consola:
            await asyncio.Event().wait()   # en la app los mensajes llegan con Voxia (simular)
        loop = asyncio.get_running_loop()
        while True:
            try:
                linea = await loop.run_in_executor(None, input, "")
            except EOFError:
                await asyncio.sleep(3600)
                continue
            linea = linea.strip()
            if not linea:
                continue
            badges = set()
            if linea.startswith("mod "):
                badges.add("moderator")
                linea = linea[4:]
            usuario, texto = "viewer_prueba", linea
            if ":" in linea.split(" ", 1)[0]:
                usuario, texto = linea.split(":", 1)
            await self.al_recibir(Mensaje(usuario=usuario.strip(), login=usuario.strip().lower(),
                                          texto=texto.strip(), id=str(time.time()), badges=badges))

    async def enviar(self, texto: str, responder_a: str = ""):
        print(f"  💬 [chat] {self.login}: {texto}")

    async def borrar_mensaje(self, msg):
        print(f"  🗑️  [prueba] (se borraría el mensaje de {msg.usuario})")
        return True

    async def timeout(self, msg, segundos, motivo):
        print(f"  ⛔ [prueba] (timeout de {segundos}s a {msg.usuario}: {motivo})")
        return True

    async def cerrar(self):
        pass
