"""Servidor local para el overlay de OBS (fuente de navegador)."""
import asyncio
import json
from pathlib import Path

from aiohttp import WSMsgType, web

from bot.rutas import INTERNOS


class Overlay:
    def __init__(self, carpeta: Path, puerto: int, tiempo_visible: int, nombre: str = "BoldoBot"):
        self.nombre = nombre
        self.carpeta = carpeta
        self.puerto = puerto
        self.tiempo_visible = tiempo_visible
        self.clientes: set[web.WebSocketResponse] = set()
        self._fin = asyncio.Event()
        self._runner = None
        self.al_cambiar = lambda n: None   # la app lo reemplaza para mostrar cuántos overlays hay
        self.colores = None                 # (acento, hover, texto, fuerte, claro) de bot/tema.py

    @property
    def conectado(self) -> bool:
        return bool(self.clientes)

    async def iniciar(self):
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        app.router.add_static("/archivos", self.carpeta)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", self.puerto).start()
        print(f"[Overlay] Listo en  http://localhost:{self.puerto}  (agrégalo en OBS como Fuente de navegador)")

    async def _index(self, _):
        return web.FileResponse(INTERNOS / "overlay" / "index.html")

    async def _ws(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clientes.add(ws)
        print(f"[Overlay] Overlay conectado ({len(self.clientes)} abierto/s)")
        self.al_cambiar(len(self.clientes))
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT and json.loads(m.data).get("tipo") == "fin":
                    self._fin.set()
        finally:
            self.clientes.discard(ws)
            self.al_cambiar(len(self.clientes))
        return ws

    async def _emitir(self, datos: dict):
        for ws in list(self.clientes):
            try:
                await ws.send_json(datos)
            except ConnectionError:
                self.clientes.discard(ws)

    async def hablar(self, titulo: str, texto: str, audio: str | None, esperar_audio: bool,
                     duracion_max: float = 40):
        """Muestra el globo (titulo = quién habla). Si el overlay reproduce el audio, espera a que termine."""
        self._fin.clear()
        await self._emitir({"tipo": "hablar", "nombre": titulo or self.nombre, "usuario": "", "pregunta": "",
                            "respuesta": texto, "audio": audio if esperar_audio else None,
                            "visible": self.tiempo_visible,
                            "colores": self._colores_css()})
        if esperar_audio:
            try:
                await asyncio.wait_for(self._fin.wait(), duracion_max)
            except asyncio.TimeoutError:
                pass

    def _colores_css(self):
        if not self.colores:
            return None
        acento, _, _, fuerte, claro = self.colores
        return {"acento": acento, "fuerte": fuerte, "claro": claro}

    async def sonido(self, audio: str, volumen: float = 0.8):
        """Toca un sonido corto (la notificación) en el overlay, sin tapar la voz."""
        await self._emitir({"tipo": "sonido", "audio": audio, "volumen": max(0.0, min(1.0, volumen))})

    async def parar_sonido(self):
        await self._emitir({"tipo": "parar_sonido"})

    async def ocultar(self):
        await self._emitir({"tipo": "callar"})
        self._fin.set()

    async def detener(self):
        if self._runner:
            await self._runner.cleanup()
