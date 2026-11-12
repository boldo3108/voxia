"""Idioma de Voxia: español (base), inglés y portugués.

Los textos se escriben en español dentro del código y se traducen con t():
    t("Guardar")                         -> "Save"
    t("Fila: {n}", n=3)                  -> "Queue: 3"
Las traducciones están en bot/traducciones.py (si falta una, se muestra el español).
"""
import locale
import sys

from bot.traducciones import EN, PT

IDIOMAS = {"es": "Español", "en": "English", "pt": "Português"}
_TABLAS = {"en": EN, "pt": PT}
_actual = "es"

# Textos que se DICEN en voz alta (cambian con el idioma si no los personalizaste)
TEXTOS_LECTURA = {
    "es": {"sufijo_usuario": "dice", "texto_no_permitido": "No eres lo bastante cool para tener voz Kappa"},
    "en": {"sufijo_usuario": "says", "texto_no_permitido": "You're not cool enough to have a voice Kappa"},
    "pt": {"sufijo_usuario": "diz", "texto_no_permitido": "Você não é legal o bastante para ter voz Kappa"},
}


def detectar() -> str:
    """Idioma del sistema (para la primera vez que se abre Voxia)."""
    codigo = ""
    if sys.platform == "win32":
        try:
            import ctypes
            primario = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            codigo = {0x0A: "es", 0x09: "en", 0x16: "pt"}.get(primario, "")
        except Exception:
            pass
    if not codigo:
        try:
            nombre = (locale.getlocale()[0] or "").lower()
        except Exception:
            nombre = ""
        for cod, pistas in (("es", ("es", "spanish")), ("pt", ("pt", "portug")), ("en", ("en", "english"))):
            if nombre.startswith(pistas):
                codigo = cod
                break
    return codigo or "es"


def de_config(cfg: dict) -> str:
    cod = (cfg.get("app", {}) or {}).get("idioma", "")
    return cod if cod in IDIOMAS else detectar()


def poner(codigo: str):
    global _actual
    _actual = codigo if codigo in IDIOMAS else "es"


def actual() -> str:
    return _actual


def t(texto: str, **datos) -> str:
    s = _TABLAS[_actual].get(texto, texto) if _actual != "es" else texto
    if datos:
        try:
            return s.format(**datos)
        except (KeyError, IndexError, ValueError):
            return texto.format(**datos)
    return s


def textos_lectura(codigo: str | None = None) -> dict:
    return dict(TEXTOS_LECTURA[codigo or _actual])
