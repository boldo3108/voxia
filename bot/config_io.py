"""Leer y guardar config.toml sin borrar los comentarios."""
import json
import re
import shutil
import tomllib
from pathlib import Path

from bot.rutas import CARPETA
CONFIG = CARPETA / "config.toml"


PLANTILLA = """# ============================================================
#  CONFIGURACIÓN DE VOXIA
#  Se cambia desde la app. Las líneas con # son comentarios.
# ============================================================

[twitch]
canal = ""
client_id = ""
token = ""

[bot]
nombre = "Voxia"

[lector]

[voz]
activada = true
motor = "edge"
voz = "es-CL-LorenzoNeural"
velocidad = "+10%"
tono = "+0Hz"
volumen = 0.9

[overlay]
activado = true
puerto = 8765
tiempo_visible = 6
"""


def leer() -> dict:
    if not CONFIG.exists():              # primera vez (o si alguien lo borró): uno nuevo
        CONFIG.write_text(PLANTILLA, encoding="utf-8")
    try:
        with open(CONFIG, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        from bot.idioma import t
        raise RuntimeError(t("Hay un error de escritura en config.toml: {error}", error=e))


def a_toml(valor) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, (list, tuple)):
        return "[" + ", ".join(a_toml(v) for v in valor) + "]"
    return json.dumps(str(valor), ensure_ascii=False)


def _rango_seccion(lineas: list[str], seccion: str) -> tuple[int, int]:
    """Devuelve (inicio, fin) de las líneas de una sección [seccion] (sin el encabezado)."""
    ini = None
    for i, l in enumerate(lineas):
        s = l.strip()
        if s.startswith("[") and not s.startswith("[["):
            nombre = s.strip("[]").strip()
            if ini is not None:
                return ini, i
            if nombre == seccion:
                ini = i + 1
    if ini is None:
        lineas.append(f"\n[{seccion}]\n")
        return len(lineas), len(lineas)
    return ini, len(lineas)


def _fin_valor(lineas: list[str], i: int) -> int:
    """Si el valor es un arreglo de varias líneas, devuelve la última línea que ocupa."""
    valor = lineas[i].split("=", 1)[1]
    sin_coment = re.sub(r'"(?:[^"\\]|\\.)*"', "", valor)
    if sin_coment.count("[") > sin_coment.count("]"):
        j = i + 1
        while j < len(lineas) and not lineas[j].strip().startswith("]"):
            j += 1
        return min(j, len(lineas) - 1)
    return i


def _comentario_final(linea: str) -> str:
    """Devuelve el '   # comentario' al final de una línea (ignorando # dentro de textos)."""
    en_texto, escape = False, False
    for k, c in enumerate(linea):
        if escape:
            escape = False
        elif c == "\\" and en_texto:
            escape = True
        elif c == '"':
            en_texto = not en_texto
        elif c == "#" and not en_texto:
            inicio = k
            while inicio > 0 and linea[inicio - 1] in " \t":
                inicio -= 1
            return linea[inicio:].rstrip("\n")
    return ""


def guardar(cambios: dict[str, dict], tablas: dict[str, dict] | None = None):
    """cambios = {"seccion": {"clave": valor}}. tablas = {"seccion": {...}} reemplaza la sección completa.
    Hace copia de seguridad y valida antes de guardar."""
    texto = CONFIG.read_text(encoding="utf-8")
    lineas = texto.splitlines(keepends=True)
    if lineas and not lineas[-1].endswith("\n"):
        lineas[-1] += "\n"

    for seccion, valores in cambios.items():
        for clave, valor in valores.items():
            ini, fin = _rango_seccion(lineas, seccion)
            patron = re.compile(rf"^\s*{re.escape(clave)}\s*=")
            for i in range(ini, fin):
                if patron.match(lineas[i]):
                    j = _fin_valor(lineas, i)
                    comentario = _comentario_final(lineas[i]) if j == i else ""
                    lineas[i:j + 1] = [f"{clave} = {a_toml(valor)}{comentario}\n"]
                    break
            else:
                lineas.insert(fin, f"{clave} = {a_toml(valor)}\n")

    for seccion, tabla in (tablas or {}).items():
        ini, fin = _rango_seccion(lineas, seccion)
        cuerpo = [l for l in lineas[ini:fin] if l.strip().startswith("#")]
        cuerpo += [f"{k} = {a_toml(v)}\n" for k, v in tabla.items()] + ["\n"]
        lineas[ini:fin] = cuerpo

    nuevo = "".join(lineas)
    tomllib.loads(nuevo)  # si quedó mal, lanza error y no guardamos nada
    shutil.copyfile(CONFIG, CONFIG.with_suffix(".toml.bak"))
    CONFIG.write_text(nuevo, encoding="utf-8")
