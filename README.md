# 🎙️ Voxia

App de voz para streams: **lee tu chat de Twitch en voz alta** (TTS) en español, inglés y portugués. Para Windows, por Boldo3108.

## Descargar
👉 **[Última versión](https://github.com/boldo3108/voxia/releases/latest)**: descarga `Voxia.exe`, ponlo en una carpeta propia y ábrelo. No se instala nada.

- 🗣️ Voces gratis (Edge, Windows) o con tu API key (Gemini, OpenAI, ElevenLabs, Google Cloud, Azure, Polly…)
- 🎁 Lee todo el chat o solo los canjes de puntos del canal
- 🛡️ Anti-spam, palabras prohibidas, permisos, emotes (Twitch, BTTV, FFZ, 7TV)
- 🔔 Notificación con tu propio sonido (recortas el trozo que quieras)
- ⌨️ Tecla rápida (F9) para saltar un mensaje, aunque estés en un juego
- 🖥️ Overlay para OBS: `http://localhost:8765`
- 🔄 Se actualiza sola cuando hay una versión nueva

Más detalles en [LEEME.md](LEEME.md).

## Publicar una versión (para el dueño del repo)
1. Escribe las novedades en `notas/vX.Y.Z.md`.
2. `git tag vX.Y.Z && git push origin vX.Y.Z`
3. GitHub Actions compila `Voxia.exe` y crea la Release sola (ver `.github/workflows/compilar.yml`).
