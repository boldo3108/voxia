"""
Inicia sesión con Twitch desde la consola (la app tiene el mismo botón en Configuración → Twitch).
Abre el navegador: entra con la cuenta que usará el bot y pulsa Autorizar.
"""
import asyncio
import sys

from bot import config_io
from bot.twitch_login import CLIENT_ID, iniciar_sesion


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    client_id = config_io.leer()["twitch"].get("client_id", "").strip() or CLIENT_ID
    if True:
        try:
            info = asyncio.run(iniciar_sesion(client_id))
            print(f"✅ Listo: conectado como {info.get('login')}")
        except RuntimeError as e:
            print(f"❌ {e}")
    input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    main()
