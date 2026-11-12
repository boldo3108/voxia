"""Convierte texto en voz con el motor elegido (Edge, Windows, Gemini, ElevenLabs, Azure...) y lo reproduce."""
import re
import sys
import time
from pathlib import Path

from bot import proveedores as P
from bot.reproductor import Reproductor

# Emojis y símbolos raros que la voz leería mal
_EMOJIS = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️]+")


def texto_para_voz(texto: str, reemplazos: list[tuple[str, str]] | None = None, quitar_emojis: bool = True) -> str:
    if quitar_emojis:
        texto = _EMOJIS.sub("", texto)
    for de, a in reemplazos or []:
        # palabra completa; sin distinguir mayúsculas salvo que la regla tenga mayúsculas
        flags = 0 if any(c.isupper() for c in de) else re.I
        texto = re.sub(rf"(?<!\w){re.escape(de)}(?!\w)", a, texto, flags=flags)
    texto = re.sub(r"@(\w+)", r"\1", texto)
    texto = re.sub(r"(\w)_(\w)", r"\1 \2", texto)  # nombre_de_usuario -> nombre de usuario
    return " ".join(texto.split())


class Voz:
    def __init__(self, cfg: dict, carpeta_audio: Path):
        """cfg = config.toml completo (lee [voz] y la sección del motor elegido)."""
        self.cfg = cfg["voz"]
        self.carpeta = carpeta_audio
        self.carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in self._audios():
            viejo.unlink(missing_ok=True)
        self.repro = Reproductor()
        self._contador = 0
        self.motor = (self.cfg.get("motor") or "edge").lower()
        if self.motor not in P.VOCES:
            print(f"[Voz] El motor «{self.motor}» no existe, uso Edge (gratis).")
            self.motor = "edge"
        self.p = P.config_de(cfg, P.VOCES, self.motor, "voz")
        self.p_edge = P.config_de(cfg, P.VOCES, "edge", "voz")
        nombre = P.VOCES[self.motor]["nombre"]
        voz = self.p.get("voz") or self.p.get("gemini_voz") or ""
        print(f"[Voz] Motor de voz: {nombre}{f' ({P.valor_id(voz)})' if voz else ''}")

    def _audios(self):
        return [p for p in self.carpeta.glob("voz_*") if p.suffix in (".mp3", ".wav", ".ogg")]

    async def generar(self, texto: str, voz: str | None = None, quitar_emojis: bool = True) -> Path | None:
        """Crea el audio con la voz (voz = otra voz de Edge para este mensaje). Si falla, usa Edge."""
        limpio = texto_para_voz(texto, quitar_emojis=quitar_emojis)
        if not limpio:
            return None
        self._contador += 1
        base = self.carpeta / f"voz_{int(time.time())}_{self._contador}"
        ruta = None
        try:
            p = {**self.p, "voz": voz} if voz and self.motor == "edge" else self.p
            ruta = await P.sintetizar(self.motor, p, limpio, base)
        except Exception as e:
            print(f"[Voz] {P.VOCES[self.motor]['nombre']} falló: {e}")
            if self.motor != "edge":
                print("[Voz] Uso la voz gratis (Edge) esta vez.")
                try:
                    ruta = await P.sintetizar("edge", self.p_edge, limpio, base)
                except Exception as e2:
                    print(f"[Voz] Tampoco pude con Edge: {e2}")
        self._limpiar_viejos()
        return ruta

    def _limpiar_viejos(self):
        archivos = sorted(self._audios(), key=lambda p: p.stat().st_mtime)
        for viejo in archivos[:-10]:
            viejo.unlink(missing_ok=True)

    async def reproducir_en_pc(self, ruta: Path):
        """Reproduce el audio por los parlantes del PC (espera a que termine)."""
        await self.repro.reproducir(_compatible(ruta), float(self.cfg.get("volumen", 0.9)))

    def callar(self):
        self.repro.parar()


def _compatible(ruta: Path) -> Path:
    """Windows no reproduce .ogg/.opus/.flac por sí solo: esos se pasan a .wav antes de sonar."""
    if ruta.suffix.lower() in (".mp3", ".wav"):
        return ruta
    try:
        import soundfile as sf
        datos, sr = sf.read(str(ruta), dtype="float32")
        destino = ruta.with_suffix(".wav")
        sf.write(str(destino), datos, sr)
        return destino
    except Exception as e:
        print(f"[Voz] No pude convertir {ruta.name} a .wav: {e}")
        return ruta
