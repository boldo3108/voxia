"""
Catálogo de motores de voz (TTS), con lo necesario para usarlos.

Cada campo es: (clave, etiqueta, tipo, valor_por_defecto, ayuda)
  tipo: "texto" | "secreto" | "voz" (con botón Cargar) | "opcion:a,b,c"
Las claves se guardan en config.toml en la sección indicada en "seccion".
"""
import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import re
import sys
import tempfile
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import aiohttp

# ================================================================== VOCES
VOCES = {
    "edge": {
        "nombre": "Edge (Microsoft)", "precio": "Gratis · necesita internet", "seccion": "voz",
        "campos": [("voz", "Voz", "voz", "es-CL-LorenzoNeural", ""),
                   ("velocidad", "Velocidad", "texto", "+10%", "ej: -10%  +0%  +25%"),
                   ("tono", "Tono", "texto", "+0Hz", "ej: -20Hz grave · +30Hz agudo")],
    },
    "windows": {
        "nombre": "Voces de Windows (SAPI5)", "precio": "Gratis · sin internet",
        "campos": [("voz", "Voz", "voz", "", "Las que tengas instaladas en Windows"),
                   ("velocidad", "Velocidad", "texto", "0", "de -10 a 10")],
    },
    "gemini": {
        "nombre": "Google Gemini TTS", "precio": "Pago por uso · muy expresiva", "seccion": "voz",
        "link": "https://aistudio.google.com/apikey",
        "campos": [("gemini_api_key", "API key", "secreto", "", ""),
                   ("gemini_voz", "Voz", "opcion:Puck,Fenrir,Charon,Orus,Algieba,Umbriel,Enceladus,Iapetus,"
                    "Kore,Aoede,Leda,Zephyr,Laomedeia,Despina,Callirrhoe,Sulafat", "Puck", ""),
                   ("gemini_estilo", "Estilo", "texto",
                    "Lee esto en español con acento chileno, como un joven bromista y buena onda, con energía y ritmo rápido",
                    "Cómo actúa (no se lee)"),
                   ("gemini_modelo", "Modelo", "texto", "gemini-3.1-flash-tts-preview", "")],
    },
    "openai": {
        "nombre": "OpenAI TTS", "precio": "Pago por uso", "link": "https://platform.openai.com/api-keys",
        "campos": [("api_key", "API key", "secreto", "", ""),
                   ("voz", "Voz", "opcion:marin,cedar,ash,ballad,coral,echo,fable,nova,onyx,sage,shimmer,verse,alloy",
                    "ash", ""),
                   ("modelo", "Modelo", "opcion:gpt-4o-mini-tts,tts-1,tts-1-hd", "gpt-4o-mini-tts", ""),
                   ("estilo", "Estilo", "texto", "Habla en español con acento chileno, alegre y bromista",
                    "Solo gpt-4o-mini-tts")],
    },
    "elevenlabs": {
        "nombre": "ElevenLabs.io", "precio": "Pago · tiene plan gratis", "link": "https://elevenlabs.io/app/settings/api-keys",
        "campos": [("api_key", "API key", "secreto", "", ""),
                   ("voz", "Voz (ID)", "voz", "", "Pulsa Cargar"),
                   ("modelo", "Modelo", "opcion:eleven_flash_v2_5,eleven_v4_turbo,eleven_v4,eleven_multilingual_v2,eleven_v3",
                    "eleven_flash_v2_5", "flash = más rápido")],
    },
    "google_cloud": {
        "nombre": "Google Cloud TTS", "precio": "Pago · tiene cuota gratis mensual",
        "link": "https://console.cloud.google.com/apis/credentials",
        "campos": [("api_key", "API key", "secreto", "", "Activa «Cloud Text-to-Speech API»"),
                   ("voz", "Voz", "voz", "es-US-Neural2-B", ""),
                   ("velocidad", "Velocidad", "texto", "1.1", "0.25 a 4.0")],
    },
    "azure": {
        "nombre": "Azure Cognitive Services", "precio": "Pago · tiene cuota gratis mensual",
        "link": "https://portal.azure.com",
        "campos": [("api_key", "Key", "secreto", "", "Recurso «Speech» en Azure"),
                   ("region", "Región", "texto", "eastus", "ej: eastus, brazilsouth"),
                   ("voz", "Voz", "voz", "es-CL-LorenzoNeural", ""),
                   ("velocidad", "Velocidad", "texto", "+10%", ""),
                   ("tono", "Tono", "texto", "+0Hz", "")],
    },
    "polly": {
        "nombre": "Amazon Polly", "precio": "Pago · tiene cuota gratis el primer año",
        "link": "https://console.aws.amazon.com/iam",
        "campos": [("access_key", "Access key ID", "texto", "", ""),
                   ("secret_key", "Secret access key", "secreto", "", ""),
                   ("region", "Región", "texto", "us-east-1", ""),
                   ("voz", "Voz", "opcion:Pedro,Lupe,Andres,Mia,Sergio,Lucia,Miguel,Penelope,Enrique,Conchita", "Pedro",
                    "Pedro/Lupe = latino EE.UU. · Andres/Mia = México"),
                   ("motor", "Motor", "opcion:neural,standard,generative", "neural", "")],
    },
    "ibm": {
        "nombre": "IBM Watson TTS", "precio": "Pago · tiene plan gratis", "link": "https://cloud.ibm.com/catalog/services/text-to-speech",
        "campos": [("api_key", "API key", "secreto", "", ""),
                   ("url", "URL del servicio", "texto", "", "La copias de tu instancia en IBM Cloud"),
                   ("voz", "Voz", "opcion:es-LA_AlejandroNatural,es-LA_DanielaNatural,es-LA_DanielaExpressive,"
                    "es-LA_SofiaV3Voice,es-US_SofiaV3Voice,es-ES_EnriqueV3Voice,es-ES_LauraV3Voice",
                    "es-LA_AlejandroNatural", "")],
    },
    "acapela": {
        "nombre": "Acapela Cloud", "precio": "Pago por créditos", "link": "https://www.acapela-cloud.com",
        "campos": [("email", "Email", "texto", "", "Tu cuenta de Acapela Cloud"),
                   ("password", "Contraseña", "secreto", "", ""),
                   ("voz", "Voz", "voz", "", "Pulsa Cargar")],
    },
    "cereproc": {
        "nombre": "CereProc Web Services", "precio": "Pago por créditos", "link": "https://www.cereproc.com/en/products/cloud",
        "campos": [("account_id", "Account ID", "texto", "", "Credenciales de CereVoice Cloud (no las de la web)"),
                   ("password", "Contraseña", "secreto", "", ""),
                   ("voz", "Voz", "texto", "", "ej: Jess")],
    },
    "ttsmonster": {
        "nombre": "TTSMonster", "precio": "Pago · voces IA para streamers", "link": "https://console.tts.monster",
        "campos": [("api_key", "API token", "secreto", "", "ttsm_..."),
                   ("voz", "Voz (ID)", "voz", "", "Pulsa Cargar")],
    },
    "uberduck": {
        "nombre": "Uberduck", "precio": "Pago", "link": "https://app.uberduck.ai",
        "campos": [("api_key", "API key", "secreto", "", ""),
                   ("voz", "Voz", "texto", "", "ID de la voz, ej: polly_lupe"),
                   ("modelo", "Modelo", "texto", "", "ej: polly_neural, azure_neural (opcional)")],
    },
}


def seccion_de(catalogo: dict, pid: str, prefijo: str) -> str:
    return catalogo[pid].get("seccion", f"{prefijo}_{pid}")


def config_de(cfg: dict, catalogo: dict, pid: str, prefijo: str) -> dict:
    """Junta los valores por defecto del catálogo con lo que haya en config.toml."""
    datos = {c[0]: c[3] for c in catalogo[pid]["campos"]}
    datos.update({k: v for k, v in cfg.get(seccion_de(catalogo, pid, prefijo), {}).items() if v not in ("", None)})
    return datos


def valor_id(texto: str) -> str:
    """Las listas cargadas muestran 'id  (nombre)': guardamos solo el id."""
    return str(texto).split("  (", 1)[0].strip()


def _timeout(seg=40):
    return aiohttp.ClientTimeout(total=seg)


async def _error(r) -> str:
    try:
        datos = await r.json(content_type=None)
        if isinstance(datos, dict):
            err = datos.get("error", datos.get("detail", datos.get("message", datos)))
            if isinstance(err, dict):
                err = err.get("message", err)
            return f"{r.status}: {str(err)[:250]}"
    except Exception:
        pass
    return f"{r.status}: {(await r.text())[:250]}"


# ================================================================== voces
async def _descargar(s: aiohttp.ClientSession, url: str, ruta_base: Path, ext_defecto: str) -> Path:
    ext = Path(url.split("?", 1)[0]).suffix.lower() or ext_defecto
    ruta = ruta_base.with_suffix(ext)
    async with s.get(url) as r:
        if r.status != 200:
            raise RuntimeError(f"no pude descargar el audio ({r.status})")
        ruta.write_bytes(await r.read())
    return ruta


def _firma_aws(metodo, host, region, servicio, ruta, cuerpo: bytes, access, secret, ahora=None):
    """Firma AWS Signature V4 (para Amazon Polly) sin librerías extra."""
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    amz_fecha, fecha = ahora.strftime("%Y%m%dT%H%M%SZ"), ahora.strftime("%Y%m%d")
    h = lambda k, m: hmac.new(k, m.encode(), hashlib.sha256).digest()
    cab_canon = f"content-type:application/json\nhost:{host}\nx-amz-date:{amz_fecha}\n"
    firmadas = "content-type;host;x-amz-date"
    canonica = "\n".join([metodo, ruta, "", cab_canon, firmadas, hashlib.sha256(cuerpo).hexdigest()])
    alcance = f"{fecha}/{region}/{servicio}/aws4_request"
    a_firmar = "\n".join(["AWS4-HMAC-SHA256", amz_fecha, alcance, hashlib.sha256(canonica.encode()).hexdigest()])
    clave = h(h(h(h(("AWS4" + secret).encode(), fecha), region), servicio), "aws4_request")
    firma = hmac.new(clave, a_firmar.encode(), hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Amz-Date": amz_fecha,
            "Authorization": f"AWS4-HMAC-SHA256 Credential={access}/{alcance}, SignedHeaders={firmadas}, Signature={firma}"}


_tokens_acapela: dict[str, str] = {}


async def _token_acapela(s, p) -> str:
    clave = p.get("email", "")
    if clave not in _tokens_acapela:
        async with s.post("https://www.acapela-cloud.com/api/login/",
                          json={"email": p.get("email", ""), "password": p.get("password", "")}) as r:
            if r.status != 200:
                raise RuntimeError(f"login Acapela {await _error(r)}")
            _tokens_acapela[clave] = (await r.json())["token"]
    return _tokens_acapela[clave]


async def _powershell(script: str) -> str:
    flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=flags)
    out, err = await asyncio.wait_for(proc.communicate(), 60)
    if proc.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "ignore")[:300])
    return out.decode("utf-8", "ignore")


async def sintetizar(mid: str, p: dict, texto: str, ruta_base: Path) -> Path:
    """Genera el audio con el motor `mid`. Devuelve la ruta del archivo (mp3/wav/ogg)."""
    async with aiohttp.ClientSession(timeout=_timeout(45)) as s:
        if mid == "edge":
            import edge_tts
            ruta = ruta_base.with_suffix(".mp3")
            await edge_tts.Communicate(texto, p["voz"], rate=p.get("velocidad", "+0%"),
                                       pitch=p.get("tono", "+0Hz")).save(str(ruta))
            return ruta

        if mid == "windows":
            if sys.platform != "win32":
                raise RuntimeError("las voces de Windows solo funcionan en Windows")
            ruta = ruta_base.with_suffix(".wav")
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(texto)
            voz = p.get("voz", "").replace("'", "''")
            elegir = f"$s.SelectVoice('{voz}');" if voz else ""
            vel = max(-10, min(10, int(float(p.get("velocidad", 0) or 0))))
            await _powershell(
                "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"{elegir} $s.Rate = {vel}; $s.SetOutputToWaveFile('{ruta}');"
                f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{f.name}')); $s.Dispose()")
            Path(f.name).unlink(missing_ok=True)
            return ruta

        if mid == "gemini":
            modelo = p.get("gemini_modelo") or "gemini-3.1-flash-tts-preview"
            estilo = (p.get("gemini_estilo") or "").strip()
            cuerpo = {"contents": [{"parts": [{"text": f"{estilo}:\n{texto}" if estilo else texto}]}],
                      "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {
                          "prebuiltVoiceConfig": {"voiceName": p.get("gemini_voz") or "Puck"}}}}}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
            for intento in range(2):   # Gemini TTS a veces da error 500: reintenta una vez
                async with s.post(url, json=cuerpo, headers={"x-goog-api-key": p.get("gemini_api_key", "").strip()}) as r:
                    if r.status >= 500 and intento == 0:
                        continue
                    if r.status != 200:
                        raise RuntimeError(f"Gemini {await _error(r)}")
                    datos = await r.json(content_type=None)
                    break
            pcm = b"".join(base64.b64decode(x["inlineData"]["data"])
                           for x in datos["candidates"][0]["content"]["parts"] if "inlineData" in x)
            if not pcm:
                raise RuntimeError("Gemini no devolvió audio")
            ruta = ruta_base.with_suffix(".wav")
            with wave.open(str(ruta), "wb") as w:   # PCM 24 kHz, mono, 16 bits
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000), w.writeframes(pcm)
            return ruta

        if mid == "openai":
            cuerpo = {"model": p["modelo"], "voice": p["voz"], "input": texto, "response_format": "mp3"}
            if p.get("estilo") and p["modelo"] == "gpt-4o-mini-tts":
                cuerpo["instructions"] = p["estilo"]
            async with s.post("https://api.openai.com/v1/audio/speech", json=cuerpo,
                              headers={"Authorization": f"Bearer {p.get('api_key', '').strip()}"}) as r:
                if r.status != 200:
                    raise RuntimeError(f"OpenAI {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "elevenlabs":
            if not p.get("voz"):
                raise RuntimeError("elige una voz de ElevenLabs (botón Cargar)")
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{valor_id(p['voz'])}?output_format=mp3_44100_128"
            async with s.post(url, json={"text": texto, "model_id": p["modelo"]},
                              headers={"xi-api-key": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(f"ElevenLabs {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "google_cloud":
            voz = valor_id(p["voz"])
            cuerpo = {"input": {"text": texto}, "voice": {"languageCode": "-".join(voz.split("-")[:2]), "name": voz},
                      "audioConfig": {"audioEncoding": "MP3", "speakingRate": float(p.get("velocidad") or 1)}}
            async with s.post("https://texttospeech.googleapis.com/v1/text:synthesize", json=cuerpo,
                              headers={"x-goog-api-key": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(f"Google Cloud {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(base64.b64decode((await r.json())["audioContent"]))
                return ruta

        if mid == "azure":
            voz = valor_id(p["voz"])
            idioma = "-".join(voz.split("-")[:2])
            ssml = (f"<speak version='1.0' xml:lang='{idioma}' xmlns='http://www.w3.org/2001/10/synthesis'>"
                    f"<voice name='{voz}'><prosody rate='{p.get('velocidad', '+0%')}' pitch='{p.get('tono', '+0Hz')}'>"
                    f"{escape(texto)}</prosody></voice></speak>")
            headers = {"Ocp-Apim-Subscription-Key": p.get("api_key", "").strip(),
                       "Content-Type": "application/ssml+xml", "User-Agent": "Voxia",
                       "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3"}
            url = f"https://{p['region'].strip()}.tts.speech.microsoft.com/cognitiveservices/v1"
            async with s.post(url, data=ssml.encode("utf-8"), headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"Azure {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "polly":
            region = p["region"].strip()
            host = f"polly.{region}.amazonaws.com"
            cuerpo = json.dumps({"OutputFormat": "mp3", "Text": texto, "VoiceId": p["voz"],
                                 "Engine": p.get("motor", "neural")}).encode()
            headers = _firma_aws("POST", host, region, "polly", "/v1/speech", cuerpo,
                                 p.get("access_key", "").strip(), p.get("secret_key", "").strip())
            async with s.post(f"https://{host}/v1/speech", data=cuerpo, headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"Polly {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "ibm":
            url = f"{p['url'].rstrip('/')}/v1/synthesize?voice={p['voz']}"
            async with s.post(url, json={"text": texto}, headers={"Accept": "audio/mp3"},
                              auth=aiohttp.BasicAuth("apikey", p.get("api_key", "").strip())) as r:
                if r.status != 200:
                    raise RuntimeError(f"IBM Watson {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "acapela":
            token = await _token_acapela(s, p)
            params = {"voice": valor_id(p["voz"]), "text": texto, "output": "file", "type": "mp3"}
            async with s.post("https://www.acapela-cloud.com/api/command/", data=params,
                              headers={"Authorization": f"Token {token}"}) as r:
                if r.status == 401:
                    _tokens_acapela.pop(p.get("email", ""), None)
                if r.status != 200 or "audio" not in r.headers.get("Content-Type", ""):
                    raise RuntimeError(f"Acapela {await _error(r)}")
                ruta = ruta_base.with_suffix(".mp3")
                ruta.write_bytes(await r.read())
                return ruta

        if mid == "cereproc":
            xml = (f"<?xml version='1.0' encoding='UTF-8'?><speakSimple><accountID>{escape(p.get('account_id', ''))}"
                   f"</accountID><password>{escape(p.get('password', ''))}</password><voice>{escape(p.get('voz', ''))}"
                   f"</voice><text>{escape(texto)}</text></speakSimple>")
            async with s.post("https://cerevoice.com/rest/rest_1_1.php", data=xml.encode("utf-8"),
                              headers={"Content-Type": "text/xml"}) as r:
                respuesta = await r.text()
            url = re.search(r"<fileUrl>(.*?)</fileUrl>", respuesta, re.S)
            if not url:
                desc = re.search(r"<resultDescription>(.*?)</resultDescription>", respuesta, re.S)
                raise RuntimeError(f"CereProc: {desc.group(1) if desc else respuesta[:200]}")
            return await _descargar(s, url.group(1).strip(), ruta_base, ".ogg")

        if mid == "ttsmonster":
            if not p.get("voz"):
                raise RuntimeError("elige una voz de TTSMonster (botón Cargar)")
            async with s.post("https://api.console.tts.monster/generate",
                              json={"voice_id": valor_id(p["voz"]), "message": texto[:500]},
                              headers={"Authorization": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(f"TTSMonster {await _error(r)}")
                url = (await r.json(content_type=None)).get("url")
            if not url:
                raise RuntimeError("TTSMonster no devolvió audio")
            return await _descargar(s, url, ruta_base, ".wav")

        if mid == "uberduck":
            cuerpo = {"text": texto, "voice": p.get("voz", "")}
            if p.get("modelo"):
                cuerpo["model"] = p["modelo"]
            async with s.post("https://api.uberduck.ai/v1/text-to-speech", json=cuerpo,
                              headers={"Authorization": f"Bearer {p.get('api_key', '').strip()}"}) as r:
                if r.status != 200:
                    raise RuntimeError(f"Uberduck {await _error(r)}")
                url = (await r.json(content_type=None)).get("audio_url")
            if not url:
                raise RuntimeError("Uberduck no devolvió audio")
            return await _descargar(s, url, ruta_base, ".mp3")
    raise RuntimeError(f"Motor de voz desconocido: {mid}")


async def listar_voces(mid: str, p: dict) -> list[str]:
    """Voces disponibles para el motor (formato 'id  (nombre)' cuando el id no se entiende solo)."""
    async with aiohttp.ClientSession(timeout=_timeout(20)) as s:
        if mid == "edge":
            import edge_tts
            voces = await edge_tts.list_voices()
            return sorted(v["ShortName"] for v in voces if v["Locale"].startswith("es-"))
        if mid == "windows":
            salida = await _powershell("Add-Type -AssemblyName System.Speech; "
                                       "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()"
                                       " | ForEach-Object { $_.VoiceInfo.Name }")
            return [l.strip() for l in salida.splitlines() if l.strip()]
        if mid == "elevenlabs":
            async with s.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(await _error(r))
                return [f"{v['voice_id']}  ({v['name']})" for v in (await r.json()).get("voices", [])]
        if mid == "google_cloud":
            async with s.get("https://texttospeech.googleapis.com/v1/voices?languageCode=es",
                             headers={"x-goog-api-key": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(await _error(r))
                return sorted(v["name"] for v in (await r.json()).get("voices", []))
        if mid == "azure":
            url = f"https://{p['region'].strip()}.tts.speech.microsoft.com/cognitiveservices/voices/list"
            async with s.get(url, headers={"Ocp-Apim-Subscription-Key": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(await _error(r))
                return sorted(v["ShortName"] for v in await r.json() if v.get("Locale", "").startswith("es-"))
        if mid == "acapela":
            token = await _token_acapela(s, p)
            async with s.get("https://www.acapela-cloud.com/api/account/", headers={"Authorization": f"Token {token}"}) as r:
                if r.status != 200:
                    raise RuntimeError(await _error(r))
                voces = (await r.json()).get("voices", [])
                return [v["name"] if isinstance(v, dict) else str(v) for v in voces]
        if mid == "ttsmonster":
            async with s.post("https://api.console.tts.monster/voices",
                              headers={"Authorization": p.get("api_key", "").strip()}) as r:
                if r.status != 200:
                    raise RuntimeError(await _error(r))
                datos = await r.json(content_type=None)
                return [f"{v['voice_id']}  ({v['name']})" for v in datos.get("customVoices", []) + datos.get("voices", [])]
    return []
