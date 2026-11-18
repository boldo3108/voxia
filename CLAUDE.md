# Voxia — guía para Claude Code

Voxia es una app de Windows que **lee el chat de Twitch en voz alta** (TTS), con overlay para OBS.
Dueño: Patricio / **Boldo3108** (Chile). Repo: `boldo3108/voxia`. Página: boldo3108.cl (repo `boldo3108/portafolio`).

## Cómo trabajar con Boldo
- Habla siempre en **español (chileno)**. Es principiante en Python: explica paso a paso, sin jerga.
- Todo lo que ve el usuario (textos, mensajes, commits) va en español.
- Le gusta el estilo visual de **Stremia** (su otra app). No le gusta el morado ("muy IA").
- **Kick está fuera** por ahora: no agregar nada de Kick hasta que lo pida.
- Se quitaron a propósito (no volver a agregar): IA/LLM, pestaña Fila, Regulares, botones Saltar/Callar
  y Pausar fila del Panel, "Decir"/"También en el chat"/checkbox Mod, "Dónde suena" (la voz suena
  siempre en el PC), "Notificación activada" en Configuración, ventana de bienvenida, interruptor "Leer chat".

## Arquitectura (v2)
- `app.py` — capa de escritorio: ventana **pywebview** (WebView2), bandeja (pystray), teclas globales,
  una sola instancia (`bot/escritorio.Instancia`, puerto 47831). `--navegador` abre el panel en el navegador.
  Si WebView2 no está, cae solo al navegador.
- `bot/panel.py` — servidor **aiohttp** en 127.0.0.1:8766 (o el siguiente libre): sirve `web/`, `/ws` (eventos
  en vivo) y `/api/...` (todas las acciones). El bot corre en su propio hilo (`Runner`).
- `main.py` — el motor (`BoldoBot`): chat de Twitch / modo prueba, fila, voz, notificación, overlay.
- `web/panel.html` + `web/panel.css` + `web/js/{core,panel,lector,config,editor}.js` — la interfaz.
  Páginas: **Panel**, **Parámetros** (id `pLector`, antes "Opciones de leer"), **Configuración**.
- `bot/lector.py` (filtros/opciones de lectura), `bot/proveedores.py` (13 motores TTS), `bot/twitch.py`,
  `bot/twitch_login.py` (OAuth implícito, `CLIENT_ID` propio, puerto 3000), `bot/overlay.py` (OBS en :8765),
  `bot/notificacion.py` (sonido + recorte máx. 10 s), `bot/atajos.py` (F9 saltar), `bot/respaldo.py`,
  `bot/novedades.py` (avisos y auto-actualización desde GitHub Releases), `bot/config_io.py` (config.toml).

## Rutas (importante: es un solo .exe)
- `bot/rutas.CARPETA` = carpeta del .exe → lo **escribible**: `config.toml`, `voxia.log`, `overlay/audio`,
  `overlay/notificacion.wav`, `voces_usuarios.json`, `backups/`.
- `bot/rutas.INTERNOS` = `sys._MEIPASS` → lo que va **dentro** del .exe (solo lectura): `web/`, `recursos/`,
  `overlay/index.html`, `VERSION`. Con Python normal ambas son la carpeta del proyecto.
- Nunca guardes nada en INTERNOS. `novedades.NO_TOCAR` = lo que una actualización jamás pisa.

## Idiomas (es / en / pt)
- El texto en español es la clave: Python `t("Texto {x}", x=1)`, JS `t("...")`, HTML `data-t="..."`
  (`data-tp` placeholder, `data-ti` title).
- **Cada texto nuevo** va como fila `(es, en, pt)` en `bot/traducciones.py` (`FILAS`). Si falta, se ve en español.

## Probar
- `python app.py --navegador` (o sin el flag en Windows con WebView2).
- `python herramientas/servir_panel.py` levanta solo el panel en http://127.0.0.1:8766 (sirve para probar con
  Playwright/navegador en Linux; la voz y las teclas son solo de Windows).
- Botón **Modo prueba** + caja de abajo del Panel = mensajes falsos sin Twitch.
- Después de probar, no dejes cambios en `config.toml` (está en `.gitignore`).

## Publicar una versión (lo hace GitHub Actions)
1. Cambios en `main`. Novedades en `notas/vX.Y.Z.md`.
2. Boldo crea la Release en GitHub con la etiqueta **`vX.Y.Z`** ("Create new tag on publish") y publica sin adjuntar nada.
   (Desde Claude no se pueden crear releases ni empujar tags: lo hace él en la web.)
3. `.github/workflows/compilar.yml` compila `Voxia.exe` (PyInstaller `--onefile`) en Windows y adjunta
   `Voxia.exe` + `Voxia-X.Y.Z-portable.zip` (el .zip es para que las 1.x se actualicen).
4. Las apps abiertas muestran "Actualizar ahora": baja `Voxia.exe`, lo ejecuta con `--instalar <carpeta> --pid N`,
   se copia encima y borra lo que dejó la versión de carpeta (`_internal`, `web`, `recursos`, `VERSION`).
5. En `boldo3108/portafolio` (`index.html`, lista `APPS`) actualizar el número `ver:` de Voxia y agregar una
   entrada en `LOG`. El link ya apunta a `releases/latest/download/Voxia.exe`.

## Estado (nov 2026)
- Publicada **v2.0.0** (ventana nueva estilo Stremia, un solo .exe, pestaña Parámetros, arreglo de Detener).
- Falta confirmar en un PC real que la ventana WebView2 se ve bien (no se pudo probar fuera de Windows).
