"""Opciones de leer (estilo Speaker.bot): qué se lee, quién puede hablar y cómo se limpia el mensaje."""
import json
import random
import re
import unicodedata
from pathlib import Path

import aiohttp

from bot import idioma

from bot.rutas import CARPETA
ARCHIVO_VOCES = CARPETA / "voces_usuarios.json"

FILTROS_URL = ["desactivado", "quitar links", "decir «link»", "decir el dominio"]
UNIDADES = ["palabras", "caracteres"]
MODO_TODO, MODO_PUNTOS = "todo el chat", "solo canjes de puntos"
MODOS = [MODO_TODO, MODO_PUNTOS]

LECTOR_DEFECTO = {
    # --- qué lee
    "modo_lectura": MODO_TODO,       # todo el chat, o solo los canjes de puntos del canal
    "recompensa_id": "",             # la recompensa que se lee ("" = cualquier canje con texto)
    # --- opciones de habla
    "decir_todo": True,              # leer todos los mensajes (si no, solo los comandos para hablar)
    "decir_usuario": True,           # decir quién escribió
    "sufijo_usuario": "dice",        # "fer_cl dice: ..."
    "voz_aleatoria": False,          # cada usuario recibe una voz al azar y la mantiene (solo voz Edge)
    "permitir_forzados": True,       # los comandos para hablar (!tts...) funcionan aunque «decir todo» esté apagado
    "usuario_solo_si_cambia": True,  # no repetir el nombre si habla la misma persona seguida
    "usar_apodos": False,            # decir el apodo en vez del usuario
    "apodos": [],                    # ["usuario=cómo se dice", ...]
    "gracia_segundos": 0,            # si la misma persona vuelve a hablar después de X s, se dice el nombre otra vez
    "maximo": 250,
    "maximo_unidad": "palabras",
    "texto_no_permitido": "No eres lo bastante cool para tener voz Kappa",
    "filtro_url": "decir «link»",
    # --- detener y saltar cuando...
    "saltar_borrado": True,
    "saltar_timeout": True,
    "saltar_ban": True,
    # --- comandos
    "silenciar_respuestas": False,   # el bot no escribe nada en el chat
    "prefijo_comandos": "!voz",      # mods: !voz skip · !voz callar · !voz off · !voz on
    "comandos_hablar": ["!tts", "!say"],
    # --- chat compartido
    "ignorar_chat_compartido": True,
    # --- emotes
    "ignorar_emotes_twitch": True,
    "ignorar_emotes_bttv": True,
    "ignorar_emotes_ffz": True,
    "ignorar_emotes_7tv": True,
    "ignorar_emojis": True,
    "ignorar_cheermotes": True,
    "permitir_primer_emote": False,
    "emotes_permitidos": [],
    # --- prefijos ignorados
    "ignorar_prefijos": True,
    "prefijos_ignorados": ["!"],
    # --- anti-spam
    "acortar_repeticiones": True,    # «jajajajaja» -> «jajaja», «aaaaaa» -> «aaa»
    "no_repetidos": True,            # no leer el mismo mensaje dos veces seguidas
    "segundos_repetidos": 60,
    "acortar_numeros": True,         # números larguísimos -> «un número largo»
    "digitos_maximos": 6,
    "max_emojis": 3,                 # solo si no se ignoran los emojis
    # --- palabras prohibidas
    "usar_palabras_prohibidas": True,
    "palabras_prohibidas": [],
    # --- permisos
    "perm_mods": True,
    "perm_subs": True,
    "perm_vips": True,
    "perm_regulares": True,
    "perm_todos": True,
    "regulares": [],
    # --- internas (no aparecen en la pantalla)
    "activado": True,
    "ignorar": ["nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "sery_bot", "wizebot"],
    "una_por_persona": True,
    "cooldown_por_usuario": 0,
    "pausa_entre_mensajes": 1,
    "fila_maxima": 15,
}

VOCES_EDGE_ES = [
    "es-CL-LorenzoNeural", "es-CL-CatalinaNeural", "es-MX-JorgeNeural", "es-MX-DaliaNeural",
    "es-AR-TomasNeural", "es-AR-ElenaNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural",
    "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-PE-AlexNeural", "es-PE-CamilaNeural",
    "es-US-AlonsoNeural", "es-US-PalomaNeural", "es-VE-SebastianNeural", "es-VE-PaolaNeural",
    "es-UY-MateoNeural", "es-UY-ValentinaNeural",
]

_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|cl|gg|tv|ly|io|xyz|me|app|link)(?:/\S*)?\b")
_EMOJIS = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️]+")
_CHEER = re.compile(r"^[A-Za-z]+\d+$")


# Opciones que ya no se muestran en la app: siempre con su valor de fábrica
FIJAS = ("decir_todo", "voz_aleatoria", "usar_apodos", "apodos", "silenciar_respuestas", "prefijo_comandos",
         "perm_regulares", "regulares")


def opciones(cfg_lector: dict) -> dict:
    op = {**LECTOR_DEFECTO, **idioma.textos_lectura(), **(cfg_lector or {})}
    for clave in FIJAS:
        op[clave] = LECTOR_DEFECTO[clave]
    op["perm_regulares"] = False
    return op


def es_canje(msg, op: dict) -> bool:
    """¿Es un canje de puntos del canal que hay que leer?"""
    rid = getattr(msg, "recompensa_id", "")
    if not rid:
        return False
    return not op["recompensa_id"] or rid == op["recompensa_id"]


def modo(msg, op: dict) -> str:
    """Qué se lee del chat de donde viene el mensaje (todo, o solo canjes)."""
    return op["modo_lectura"]



# ------------------------------------------------------ palabras prohibidas
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def normalizar(texto: str) -> str:
    """minúsculas, sin tildes, sin «leet» (p0t4 -> pota) y sin letras estiradas (puuuuta -> puta)."""
    s = unicodedata.normalize("NFKD", texto.lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).translate(_LEET)
    s = re.sub(r"(.)\1{2,}", r"\1", s)
    return " ".join(re.findall(r"\w+", s))


def palabra_prohibida(texto: str, lista) -> str | None:
    """Devuelve la palabra de la lista que aparece en el texto (o None).
    «palabra» = palabra exacta · «palabra*» = cualquier palabra que empiece así · «dos palabras» = frase."""
    palabras = normalizar(texto).split()
    frase = " " + " ".join(palabras) + " "
    for original in lista:
        p = original.strip()
        if not p:
            continue
        prefijo = p.endswith("*")
        buscada = normalizar(p.rstrip("*"))
        if not buscada:
            continue
        if " " in buscada:
            if f" {buscada}" in frase if prefijo else f" {buscada} " in frase:
                return p
        elif (any(w.startswith(buscada) for w in palabras) if prefijo else buscada in palabras):
            return p
    return None


# ----------------------------------------------------------------- anti-spam
def acortar_repeticiones(texto: str) -> str:
    texto = re.sub(r"(\w)\1{3,}", r"\1\1\1", texto)                      # aaaaaa -> aaa
    texto = re.sub(r"(\S{1,4}?)\1{3,}", r"\1\1\1", texto)                 # jajajajaja -> jajaja
    texto = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", r"\1 \1", texto, flags=re.I)  # lol lol lol lol -> lol lol
    return texto


def limitar_emojis(texto: str, maximo: int) -> str:
    quedan = max(0, int(maximo))

    def recortar(m):
        nonlocal quedan
        simbolos = [c for c in m.group(0) if c not in "\u200d\ufe0f"]
        dejar = simbolos[:quedan]
        quedan -= len(dejar)
        return "".join(dejar) if dejar else " "
    return _EMOJIS.sub(recortar, texto)


# ---------------------------------------------------------------- permisos
def puede_hablar(msg, op: dict) -> bool:
    if "broadcaster" in msg.badges or op["perm_todos"]:
        return True
    if op["perm_mods"] and "moderator" in msg.badges:
        return True
    if op["perm_vips"] and "vip" in msg.badges:
        return True
    if op["perm_subs"] and msg.badges & {"subscriber", "founder"}:
        return True
    if op["perm_regulares"] and msg.login in {r.strip().lower() for r in op["regulares"]}:
        return True
    return False


def es_chat_compartido(msg) -> bool:
    """En chat compartido, los mensajes que vienen de OTRO canal traen source-room-id distinto."""
    return bool(msg.source_room_id and msg.room_id and msg.source_room_id != msg.room_id)


# ------------------------------------------------------------------ nombres
def apodo(msg, op: dict) -> str:
    if op["usar_apodos"]:
        for linea in op["apodos"]:
            if "=" in linea:
                u, a = linea.split("=", 1)
                if u.strip().lower().lstrip("@") == msg.login and a.strip():
                    return a.strip()
    return msg.usuario


# ------------------------------------------------------------ limpiar texto
def _quitar_emotes_twitch(texto: str, emotes_tag: str, permitidos: set, primero: bool) -> str:
    """Borra los emotes de Twitch usando las posiciones que manda el chat (índices por carácter)."""
    rangos = []
    for parte in (emotes_tag or "").split("/"):
        if ":" not in parte:
            continue
        for r in parte.split(":", 1)[1].split(","):
            if "-" in r:
                a, b = r.split("-", 1)
                if a.isdigit() and b.isdigit():
                    rangos.append((int(a), int(b)))
    if not rangos:
        return texto
    rangos.sort()
    salida, pos, conservado = [], 0, False
    for a, b in rangos:
        nombre = texto[a:b + 1]
        salida.append(texto[pos:a])
        if nombre in permitidos or (primero and not conservado):
            salida.append(nombre)
            conservado = conservado or nombre not in permitidos
        pos = b + 1
    salida.append(texto[pos:])
    return "".join(salida)


def limpiar(msg, texto: str, op: dict, emotes_terceros: dict[str, set]) -> str:
    """Aplica emotes, emojis, cheermotes, links y el máximo de palabras/caracteres."""
    permitidos = {e.strip() for e in op["emotes_permitidos"] if e.strip()}
    primero = op["permitir_primer_emote"]
    conservado = False
    if op["ignorar_emotes_twitch"] and texto == msg.texto:       # las posiciones solo valen para el mensaje original
        texto = _quitar_emotes_twitch(texto, msg.emotes, permitidos, primero)
        conservado = primero and bool(msg.emotes)

    quitar = set()
    for clave in ("bttv", "ffz", "7tv"):
        if op[f"ignorar_emotes_{clave}"]:
            quitar |= emotes_terceros.get(clave, set())
    palabras = []
    for p in texto.split():
        es_cheer = op["ignorar_cheermotes"] and msg.bits and _CHEER.match(p)
        if (p in quitar or es_cheer) and p not in permitidos:
            if primero and not conservado and not es_cheer:
                conservado = True
                palabras.append(p)
            continue
        palabras.append(p)
    texto = " ".join(palabras)

    if op["ignorar_emojis"]:
        texto = _EMOJIS.sub(" ", texto)
    else:
        texto = limitar_emojis(texto, op["max_emojis"])
    filtro = op["filtro_url"]
    if filtro == "quitar links":
        texto = _URL.sub(" ", texto)
    elif filtro == "decir «link»":
        texto = _URL.sub(" link ", texto)
    elif filtro == "decir el dominio":
        texto = _URL.sub(lambda m: " " + re.sub(r"(?i)^(https?://)?(www\.)?", "", m.group(0)).split("/")[0] + " ", texto)

    if op["acortar_repeticiones"]:
        texto = acortar_repeticiones(texto)
    if op["acortar_numeros"]:
        largo = max(3, int(op["digitos_maximos"]))
        texto = re.sub(r"\d{%d,}" % (largo + 1), " " + idioma.t("un número largo") + " ", texto)

    texto = " ".join(texto.split())
    maximo = max(1, int(op["maximo"]))
    if op["maximo_unidad"] == "caracteres":
        texto = texto[:maximo].strip()
    else:
        texto = " ".join(texto.split()[:maximo])
    return texto


# ------------------------------------------------------- voces por usuario
class VocesUsuarios:
    """Voz al azar «pegada» a cada usuario (se recuerda entre streams)."""

    def __init__(self):
        try:
            self.mapa = json.loads(ARCHIVO_VOCES.read_text(encoding="utf-8"))
        except Exception:
            self.mapa = {}

    def de(self, login: str) -> str:
        if login not in self.mapa:
            self.mapa[login] = random.choice(VOCES_EDGE_ES)
            try:
                ARCHIVO_VOCES.write_text(json.dumps(self.mapa, indent=1), encoding="utf-8")
            except OSError:
                pass
        return self.mapa[login]


# ------------------------------------------------- emotes de BTTV/FFZ/7TV
async def cargar_emotes_terceros(canal_id: str) -> dict[str, set]:
    """Descarga los nombres de emotes globales y del canal. Si un servicio falla, sigue con los demás."""
    res = {"bttv": set(), "ffz": set(), "7tv": set()}

    async def obtener(s, url):
        try:
            async with s.get(url) as r:
                return await r.json(content_type=None) if r.status == 200 else None
        except Exception:
            return None

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
        g = await obtener(s, "https://api.betterttv.net/3/cached/emotes/global")
        res["bttv"] |= {e.get("code") for e in (g or []) if isinstance(e, dict)}
        g = await obtener(s, "https://api.frankerfacez.com/v1/set/global")
        for st in ((g or {}).get("sets") or {}).values():
            res["ffz"] |= {e.get("name") for e in st.get("emoticons", [])}
        g = await obtener(s, "https://7tv.io/v3/emote-sets/global")
        res["7tv"] |= {e.get("name") for e in ((g or {}).get("emotes") or [])}
        if canal_id:
            c = await obtener(s, f"https://api.betterttv.net/3/cached/users/twitch/{canal_id}") or {}
            for e in c.get("channelEmotes", []) + c.get("sharedEmotes", []):
                res["bttv"].add(e.get("code"))
            c = await obtener(s, f"https://api.frankerfacez.com/v1/room/id/{canal_id}") or {}
            for st in (c.get("sets") or {}).values():
                res["ffz"] |= {e.get("name") for e in st.get("emoticons", [])}
            c = await obtener(s, f"https://7tv.io/v3/users/twitch/{canal_id}") or {}
            res["7tv"] |= {e.get("name") for e in ((c.get("emote_set") or {}).get("emotes") or [])}
    for k in res:
        res[k].discard(None)
    return res
