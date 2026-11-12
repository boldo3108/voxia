"""Inicio de sesión con Twitch (OAuth oficial): abre el navegador, recibe el token y lo guarda en config.toml."""
import asyncio
import json
import re
import webbrowser
from urllib.parse import urlencode

from aiohttp import web

from bot import config_io
from bot.idioma import t
from bot.twitch import validar_token

PUERTO = 3000
# App «Voxia» registrada en dev.twitch.tv (cliente público): los usuarios solo inician sesión
CLIENT_ID = "cbmo1rwoilze0sfcjt07hc05t2k8mn"
PERMISOS = ["chat:read", "chat:edit", "moderator:manage:chat_messages", "moderator:manage:banned_users"]

def pagina() -> str:
    """Página que ve el usuario en el navegador al volver de Twitch."""
    textos = {k: json.dumps(v) for k, v in {
        "guardando": t("Guardando..."),
        "sin_token": t("No llegó el token: "),
        "reintenta": t("intenta de nuevo"),
        "listo": t("✅ ¡Listo! Sesión de Twitch guardada.") + "<br><br>" +
                 t("Ya puedes cerrar esta pestaña y volver a Voxia."),
        "error": t("❌ Error guardando la sesión"),
    }.items()}
    return f"""<!doctype html><meta charset="utf-8"><title>Voxia</title>
<body style="font-family:sans-serif;background:#16161a;color:#fff;display:grid;place-items:center;height:100vh;margin:0">
<div id="t" style="font-size:22px;text-align:center"></div>
<script>
const p = new URLSearchParams(location.hash.slice(1));
const t = document.getElementById('t');
t.textContent = {textos["guardando"]};
if (!p.get('access_token')) {{ t.textContent = {textos["sin_token"]} + (new URLSearchParams(location.search).get('error_description') || {textos["reintenta"]}); }}
else fetch('/guardar', {{method:'POST', body:p.get('access_token')}})
  .then(r => r.ok ? t.innerHTML = {textos["listo"]} : t.textContent = {textos["error"]});
</script>"""


def url_autorizar(client_id: str) -> str:
    return "https://id.twitch.tv/oauth2/authorize?" + urlencode({
        "response_type": "token", "client_id": client_id.strip(),
        "redirect_uri": f"http://localhost:{PUERTO}", "scope": " ".join(PERMISOS), "force_verify": "true"})


async def iniciar_sesion(client_id: str = CLIENT_ID, espera_max: int = 300, abrir=True) -> dict:
    """Abre el navegador para autorizar, guarda el token y devuelve los datos de la cuenta
    (login, user_id, expires_in...). Lanza RuntimeError si algo falla o se acaba el tiempo."""
    client_id = (client_id or "").strip() or CLIENT_ID
    if not client_id:
        raise RuntimeError(t("Falta el Client ID de tu app de Twitch."))
    recibido: asyncio.Future = asyncio.get_running_loop().create_future()

    async def inicio(_):
        return web.Response(text=pagina(), content_type="text/html")

    async def guardar(request):
        token = (await request.text()).strip()
        if not re.fullmatch(r"[a-z0-9]{20,64}", token):
            return web.Response(status=400)
        if not recibido.done():
            recibido.set_result(token)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", inicio)
    app.router.add_post("/guardar", guardar)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "localhost", PUERTO).start()
    except OSError:
        await runner.cleanup()
        raise RuntimeError(t("El puerto {puerto} está ocupado. Cierra otras ventanas de Voxia e intenta de nuevo.", puerto=PUERTO))
    try:
        url = url_autorizar(client_id)
        print("[Twitch] Abriendo el navegador para iniciar sesión...")
        print(f"[Twitch] Si no se abre solo, copia este link en el navegador:\n{url}")
        if abrir:
            webbrowser.open(url)
        try:
            token = await asyncio.wait_for(recibido, espera_max)
        except asyncio.TimeoutError:
            raise RuntimeError(t("Se acabó el tiempo para iniciar sesión. Intenta de nuevo."))
        await asyncio.sleep(0.5)   # que la página alcance a mostrar el ✅
    finally:
        await runner.cleanup()
    info = await validar_token(token)
    cambios = {"token": token}
    if not config_io.leer().get("twitch", {}).get("canal", "").strip():   # sin canal: usa el de la cuenta
        cambios["canal"] = info.get("login", "")
    config_io.guardar({"twitch": cambios})
    print(f"[Twitch] Sesión guardada: cuenta «{info.get('login')}» ✔")
    return info


async def cuenta_actual(token: str) -> dict | None:
    """Datos de la cuenta del token guardado, o None si no sirve."""
    if not token:
        return None
    try:
        return await validar_token(token)
    except Exception:
        return None
