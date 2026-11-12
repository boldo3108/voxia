/* Voxia — página Panel: iniciar/detener, Voz y Notificación, «Ahora», chat y mensaje de prueba */
"use strict";
const Panel = {
  activo: false, prueba: false,

  iniciar(e) {
    $("#btnIniciar").onclick = () => this.iniciarBot(false);
    $("#btnPrueba").onclick = () => this.iniciarBot(true);
    $("#btnDetener").onclick = () => { $("#btnDetener").disabled = true; Voxia.api("/api/detener").catch(err => Voxia.error(err)); };
    $("#swVoz").checked = e.voz;
    $("#swNotif").checked = e.notificacion;
    $("#swVoz").onchange = () => Voxia.api("/api/voz", { activa: $("#swVoz").checked }).catch(err => Voxia.error(err));
    $("#swNotif").onchange = () => Voxia.api("/api/notificacion", { activa: $("#swNotif").checked }).catch(err => Voxia.error(err));
    $("#simSend").onclick = () => this.simular();
    $("#simText").addEventListener("keydown", ev => { if (ev.key === "Enter") this.simular(); });
    $("#chatLimpiar").onclick = () => { $("#chat").innerHTML = ""; this.vacio(); };
    this.puntos(e.puntos);
    this.tecla(e.tecla_saltar);
    this.estado(e);
    (e.chat || []).forEach(m => this.chat(m, false));
    this.vacio();
    this.abajo();

    Voxia.on("estado", d => this.estado(d));
    Voxia.on("chip", d => this.chip(d.clave, d.color, d.texto));
    Voxia.on("chat", d => this.chat(d));
    Voxia.on("fila", d => this.fila(d.n));
    Voxia.on("hablando", d => this.ahora(d));
    Voxia.on("switch", d => { (d.clave === "voz" ? $("#swVoz") : $("#swNotif")).checked = d.valor; });
    Voxia.on("puntos", d => this.puntos(d.valor));
    Voxia.on("tecla", d => this.tecla(d.valor));
    Voxia.on("aviso", d => d.tipo === "error" ? Voxia.error(d.texto) : Voxia.toast(d.texto, d.tipo));
  },

  async iniciarBot(prueba) {
    try {
      const r = await Voxia.api("/api/iniciar", { prueba });
      if (r.ir_a === "twitch") Config.irATwitch();
    } catch (err) { Voxia.error(err); }
  },

  estado(d) {
    this.activo = d.activo; this.prueba = d.prueba;
    $("#btnIniciar").disabled = d.activo;
    $("#btnPrueba").disabled = d.activo;
    $("#btnDetener").disabled = !d.activo;
    const g = $("#estadoG");
    g.className = "estado-g " + (d.activo ? (d.prueba ? "prueba" : "vivo") : "");
    $("span", g).textContent = t(d.activo ? (d.prueba ? "Modo prueba" : "En vivo") : "Apagado");
    Object.entries(d.chips || {}).forEach(([k, [color, texto]]) => this.chip(k, color, texto));
    this.ahora(d.ahora || {});
    this.fila(d.fila || 0);
  },

  chip(clave, color, texto) {
    const el = clave === "twitch" ? $("#chipTwitch") : $("#chipVoz");
    el.className = "chip " + (color || "");
    $("span", el).textContent = t(texto);
  },

  ahora(d) {
    const el = $("#ahoraTxt");
    if (!d.texto) { el.innerHTML = '<span class="muted">—</span>'; return; }
    el.innerHTML = `<span class="hablando"><i></i><i></i><i></i></span>` +
      (d.usuario ? `<span class="u">${esc(d.usuario)}</span>` : "") + esc(d.texto);
  },

  fila(n) { $("#filaTxt").textContent = t("Fila: {n}", { n }); },

  tecla(tecla) {
    const el = $("#teclaTxt");
    el.hidden = !tecla;
    if (tecla) el.innerHTML = "⌨️ " + esc(t("{tecla} = saltar mensaje", { tecla: "\u0000" })).replace("\u0000", `<span class="tecla">${esc(tecla)}</span>`);
  },

  puntos(si) {
    $("#chkCanjeL").hidden = !si;
    if (!si) $("#chkCanje").checked = false;
  },

  vacio() {
    const c = $("#chat");
    if (!c.querySelector(".cm") && !c.querySelector(".empty")) {
      c.innerHTML = `<div class="empty">💬 ${esc(t("Aquí aparece el chat cuando inicias Voxia."))}</div>`;
    }
  },

  abajo() { const c = $("#chat"); c.scrollTop = c.scrollHeight; },

  chat(m, desplazar = true) {
    const c = $("#chat");
    c.querySelector(".empty")?.remove();
    const pegado = c.scrollHeight - c.scrollTop - c.clientHeight < 40;
    const el = document.createElement("div");
    el.className = "cm" + (m.bot ? " bot" : m.mod ? " mod" : "");
    el.innerHTML = `<span class="h">${esc(m.hora || "")}</span>` +
      (m.bot ? "🎙️ " : m.mod ? '<span class="role">MOD</span>' : "") +
      `<span class="n">${esc(m.usuario)}:</span><span class="x">${esc(m.texto)}</span>`;
    c.append(el);
    while (c.children.length > 500) c.firstChild.remove();
    if (desplazar && pegado) this.abajo();
  },

  async simular() {
    const texto = $("#simText").value.trim();
    if (!texto) return;
    if (!this.activo) { Voxia.toast(t("Primero inicia el bot (▶ Iniciar o 🧪 Modo prueba)."), "warn"); return; }
    try {
      await Voxia.api("/api/simular", { usuario: $("#simUser").value, texto, canje: $("#chkCanje").checked });
      $("#simText").value = "";
    } catch (err) { Voxia.error(err); }
  },
};
