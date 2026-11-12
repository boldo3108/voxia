# 🎙️ Voxia — Voz para tu stream

Voxia **lee en voz alta el chat de Twitch**:
- 🎛️ Se maneja desde una **app de escritorio** (sin tocar código), con el mismo estilo que Stremia, en **español, inglés o portugués**
- 🗣️ Usa la voz que elijas: **Edge** o **Voces de Windows** (gratis), o con tu API key: Google Gemini TTS · OpenAI TTS · ElevenLabs · Google Cloud TTS · Azure · Amazon Polly · IBM Watson · Acapela Cloud · CereProc · TTSMonster · Uberduck
- 🔔 **Notificación** con sonido propio: subes un mp3/wav y recortas el trozo que quieras (máx. 10 s)
- 🖥️ **Aparece en OBS** con un avatar que mueve la boca y un globo con el nombre y el mensaje

Si la voz elegida falla en vivo, Voxia usa la voz gratis de Edge para no quedarse mudo.

---

## 📋 Instalación (solo la primera vez)

1. **Python:** descarga Python 3.12 o más nuevo desde https://www.python.org/downloads/ y al instalar
   **marca la casilla "Add python.exe to PATH"**.
2. Doble clic en **`INSTALAR.bat`** y espera a que diga `[OK] Instalacion lista`.
3. Abre **Voxia** con el acceso directo del escritorio (o doble clic en **`VOXIA.bat`**). La voz se elige en *Configuración → Voz* (de fábrica usa Edge, gratis).
4. Pulsa **🧪 Modo prueba** y escribe abajo como si fueras del chat: lo leerá en voz alta.

---

## 🖥️ La app

| Pestaña | Para qué sirve |
|---|---|
| 🎛️ **Panel** | Iniciar / Modo prueba / Detener · estado de Twitch y voz · interruptores (**Voz** = leer el chat en voz alta, **Notificación**) · chat en vivo · escribir como viewer para probar (con «🎁 Como canje» si lees solo canjes) |
| 📖 **Parámetros** | Qué mensajes lee, de quiénes, cómo lo dice, ritmo y fila (se aplica al tiro al guardar) |
| ⚙️ **Configuración** | **Idioma** y acceso directo · **Twitch** (iniciar sesión) · **Voz** (motor, key, «Cargar» voces, «Probar esta voz») · **Notificación** · **Actualizaciones** |

Arriba a la derecha: 🎨 eliges el **color** de la app y del overlay, y 🌙/☀️ cambia entre modo **oscuro / claro**.
La ventana es una página que muestra Voxia por dentro (como Stremia). Si quieres verla en el navegador: `Voxia.exe --navegador`.
Necesita «Microsoft Edge WebView2», que ya viene en Windows 10 y 11 (si falta, Voxia se abre en el navegador).
Si algo falla, el detalle queda en el archivo **`voxia.log`** (en la carpeta de Voxia).

### 🌐 Idioma
En *Configuración → Idioma* eliges **Español, English o Português**: la app cambia al tiro.
Si no cambiaste el «texto después del nombre» (ej. «dice»), también se cambia al idioma nuevo (says / diz).
La voz no cambia sola: elige una voz del idioma que quieras en *Configuración → Voz* (botón «Cargar»).

### 📖 Parámetros (estilo Speaker.bot)
- **Opciones de habla:** decir el nombre (+ texto después del nombre, ej. «dice») · permitir mensajes forzados
  (comandos para hablar) · decir el nombre solo si cambió quien habla (+ tiempo de gracia) · máximo de
  palabras/caracteres · texto para quien no tiene permiso · filtro de links
- **Detener y saltar** cuando un mod borra el mensaje, da timeout o banea
- **Qué lee:** todo el chat, o **solo los canjes de puntos del canal** (botón «Detectar recompensa»)
- **Permisos:** moderadores, suscriptores, VIPs y todos (los canjes de puntos se leen siempre)
- **Anti-spam:** acorta «jajajajaja» y letras estiradas, no repite mensajes iguales, acorta números largos y limita emojis
- **Palabras prohibidas:** si un mensaje trae una, no se lee (detecta tildes, mayúsculas, «p4l4br4» y «palaaabra»; `palabra*` = empieza con)
- **Chat compartido:** ignorar mensajes que llegan de otros canales
- **Emotes:** ignorar emotes de Twitch, BTTV, FFZ, 7TV, emojis y cheermotes · permitir el primer emote · emotes permitidos
- **Comandos para hablar** (`!tts`, `!say`…) y **prefijos ignorados** (por defecto, los mensajes que empiezan con `!`)

> 💾 Apenas cambias algo, el botón Guardar (abajo a la derecha, o Ctrl+S) se pone **rojo y vibra** hasta que guardes (o pulses «Deshacer cambios»).
> Si intentas ir a otra pestaña sin guardar, no te deja y vibra más fuerte; pulsa la pestaña otra vez si quieres
> salir sin guardar (los cambios se descartan). Funciona en Parámetros y en Configuración.

### 🔔 Notificación (Configuración)
- Suena **cada vez que alguien escribe** en el chat, aunque «Voz» esté apagada
  (así puedes usar Voxia solo como aviso de mensajes nuevos)
- Si «Voz» está prendida, primero suena la notificación completa y después se lee el mensaje
- **Subir sonido…** → eliges un audio (aunque dure minutos) y se abre el **editor**: arrastra las marcas sobre la forma de onda
  para elegir el trozo (máximo 10 s, o menos si quieres), pulsa **Escuchar recorte** y luego **Guardar notificación**
- **Recortar de nuevo** vuelve a abrir el editor con tu archivo · **Sonido por defecto** vuelve al «ding» de Voxia
- Se activa o desactiva con el interruptor **Notificación** del Panel

---

## 🔄 Actualizaciones, ⌨️ teclas rápidas, 🪟 bandeja y 💾 respaldo

- **Actualizaciones:** al abrirse, Voxia revisa si hay una versión nueva publicada en
  `github.com/boldo3108/voxia` (Releases). Si hay, aparece un aviso arriba con **«Actualizar ahora»**:
  se descarga, se cierra, se instala sola y se vuelve a abrir. No toca tu configuración, sesión, keys, avatar ni notificación.
- **Teclas rápidas** (*Configuración → Teclas rápidas*): **F9** salta el mensaje que está sonando (y puedes poner
  otra para «Callar todo»). Funcionan aunque estés dentro de un juego.
- **Bandeja / Windows** (*Configuración → Windows*): minimizar a la bandeja (junto al reloj), seguir funcionando al
  cerrar con la X, iniciar con el PC (escondida en la bandeja) y conectar a Twitch apenas se abre.
  Si abres Voxia otra vez mientras ya está abierta, se muestra la que ya estaba (nunca quedan dos).
- **Respaldo** (*Configuración → Respaldo*): **Exportar…** guarda todo en un .zip (puedes elegir dejar fuera la
  sesión y las keys) e **Importar…** lo recupera; tu configuración anterior queda en la carpeta `backups`.

### 🚀 Cómo publicar una versión nueva (para el dueño de Voxia)
1. En GitHub crea el repositorio **público** `voxia` (en la cuenta `boldo3108`).
2. *Releases → Draft a new release* · **Tag:** `v1.3.0` (el número de la versión nueva) · **Descripción:** las novedades.
3. Adjunta el `Voxia-X.Y.Z-portable.zip` y pulsa **Publish release**. Las Voxia instaladas avisarán solas.

---

## 🟣 Conectar a Twitch

No hay que crear nada en Twitch: Voxia ya trae su app registrada.

1. Pulsa **▶ Iniciar Twitch**: si todavía no conectas tu cuenta, te lleva directo a *Configuración → Twitch*.
2. Pulsa **🟣 Iniciar sesión con Twitch** y autoriza en el navegador. Al volver dirá **✔ Conectado como …**
   y el campo *Tu canal* se llena solo.
3. *(Opcional)* Si quieres que los mensajes del bot salgan con otro nombre, inicia sesión con una cuenta
   aparte (por ejemplo una ventana de incógnito) y escribe tu canal a mano en *Tu canal*.

La sesión dura ~2 meses; cuando venza, la app te avisa y repites el paso 2.

> ⚠️ La sesión y las API keys son como contraseñas: **no muestres `config.toml` en stream**.

### Overlay en OBS
1. **Fuentes → + → Navegador** · URL `http://localhost:8765` · Ancho `900` · Alto `320`
2. La voz y la notificación suenan por los **parlantes del PC**: OBS las toma con tu fuente de **Audio del escritorio**
   (el overlay solo muestra el avatar y el globo).
3. **Avatar propio:** pon una imagen cuadrada llamada `avatar.png` en la carpeta `overlay/`

---

## 🎮 Comandos del chat

| Comando | Quién | Qué hace |
|---|---|---|
| `!tts <mensaje>` · `!say <mensaje>` | quien tenga permiso | Lee ese mensaje (se cambian en *Comandos para hablar*) |
| `!voz skip` | mods | Salta el mensaje que está sonando (o **F9** en tu PC) |
| `!voz callar` | mods | Corta la voz y vacía la fila |
| `!voz off` / `!voz on` | mods | Apaga / prende la voz |

---

## 🆘 Problemas comunes

| Problema | Solución |
|---|---|
| La sesión de Twitch venció | Configuración → Twitch → «Iniciar sesión con Twitch» |
| `El puerto 3000 está ocupado` | Cierra otras ventanas de Voxia y vuelve a intentar |
| La voz no suena o dice "falló" | Revisa la key con «Probar esta voz». Edge necesita internet |
| No se escucha en el stream | Revisa que OBS tenga «Audio del escritorio» y que Voxia suene en los parlantes que captura |
| El editor dice que falta una librería | Ejecuta `INSTALAR.bat` otra vez |
| CereProc no suena por parlantes | Entrega audio .ogg: usa «Dónde suena: overlay» |
