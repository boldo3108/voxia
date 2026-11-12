/* Voxia — núcleo de la página: traducciones, servidor, eventos en vivo, avisos y navegación */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const Voxia = {
  T: {}, estado: {}, manejadores: {}, guardas: {}, pagina: "pPanel", salidaPendiente: null,

  // ------------------------------------------------------------ traducciones
  t(s, kw) {
    let r = this.T[s] ?? s;
    const datos = { app: "Voxia", ...(kw || {}) };
    return r.replace(/\{(\w+)\}/g, (m, k) => (k in datos ? datos[k] : m));
  },
  traducir(raiz = document) {
    $$("[data-t]", raiz).forEach(el => { el.textContent = this.t(el.dataset.t); });
    $$("[data-tp]", raiz).forEach(el => { el.placeholder = this.t(el.dataset.tp); });
    $$("[data-ti]", raiz).forEach(el => { el.title = this.t(el.dataset.ti); });
  },

  // ---------------------------------------------------------------- servidor
  async get(ruta) {
    const r = await fetch(ruta, { cache: "no-store" });
    return r.json();
  },
  async api(ruta, datos = {}) {
    const r = await fetch(ruta, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "Error");
    return j;
  },
  async subir(ruta, archivo) {
    const fd = new FormData();
    fd.append("archivo", archivo, archivo.name);
    const r = await fetch(ruta, { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "Error");
    return j;
  },

  // ---------------------------------------------------------- eventos en vivo
  on(ev, fn) { (this.manejadores[ev] ||= []).push(fn); },
  conectar() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = e => {
      let d; try { d = JSON.parse(e.data); } catch { return; }
      (this.manejadores[d.ev] || []).forEach(fn => { try { fn(d); } catch (err) { console.error(err); } });
    };
    ws.onclose = () => {
      this._caido = true;
      setTimeout(() => this.conectar(), 1500);
    };
    ws.onopen = () => {
      if (this._caido) { this._caido = false; location.reload(); }   // el servidor volvió: refrescar todo
    };
  },

  // ----------------------------------------------------------------- avisos
  toast(texto, tipo = "") {
    const el = document.createElement("div");
    el.className = "toast " + tipo;
    el.textContent = texto;
    $("#toasts").append(el);
    setTimeout(() => { el.style.transition = "opacity .3s"; el.style.opacity = "0"; }, tipo === "error" ? 6000 : 3200);
    setTimeout(() => el.remove(), tipo === "error" ? 6400 : 3600);
  },
  error(e) { this.dialogo({ titulo: "Voxia", texto: String(e?.message || e), botones: [{ v: true, txt: "OK", cls: "accent" }] }); },

  /** Ventanita con botones. botones: [{v, txt, cls}] — devuelve el v del botón (o null si se cierra). */
  dialogo({ titulo = "Voxia", texto = "", html = "", botones }) {
    const m = $("#mDialogo");
    $("#dlgTitulo").textContent = titulo;
    $("#dlgTexto").textContent = texto;
    $("#dlgTexto").hidden = !texto;
    $("#dlgExtra").innerHTML = html;
    const caja = $("#dlgBotones");
    caja.innerHTML = "";
    botones ||= [{ v: true, txt: "OK", cls: "accent" }];
    return new Promise(res => {
      const fin = v => { m.hidden = true; document.removeEventListener("keydown", tecla); res(v); };
      const tecla = e => { if (e.key === "Escape") fin(null); };
      botones.forEach(b => {
        const btn = document.createElement("button");
        btn.className = "btn " + (b.cls || "");
        btn.textContent = b.txt;
        btn.onclick = () => fin(b.v);
        caja.append(btn);
      });
      m.onclick = e => { if (e.target === m) fin(null); };
      document.addEventListener("keydown", tecla);
      m.hidden = false;
      caja.lastChild?.focus();
    });
  },
  async confirmar(texto, si = "Sí", no = "No") {
    return (await this.dialogo({ texto, botones: [{ v: false, txt: this.t(no) }, { v: true, txt: this.t(si), cls: "accent" }] })) === true;
  },

  // ------------------------------------------------------------ apariencia
  aplicarColor(nombre) {
    const c = this.estado.colores[nombre] || this.estado.colores.Naranjo;
    const r = document.documentElement.style;
    r.setProperty("--accent", c[0]); r.setProperty("--accent2", c[1]); r.setProperty("--accent-txt", c[2]);
    r.setProperty("--accent-strong", c[3]);
    const h = c[0].replace("#", "");
    const [R, G, B] = [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16));
    r.setProperty("--accent-soft", `rgba(${R},${G},${B},.14)`);
    this.estado.color = nombre;
    $$(".sw").forEach(s => s.classList.toggle("on", s.dataset.color === nombre));
  },
  aplicarModo(modo) {
    document.documentElement.dataset.modo = modo;
    this.estado.modo = modo;
    $("#btnModo").textContent = modo === "claro" ? "☀️" : "🌙";
    $$("#segModo button").forEach(b => b.classList.toggle("on", b.dataset.modo === modo));
  },
  iniciarApariencia() {
    const caja = $("#swatches");
    Object.entries(this.estado.colores).forEach(([nombre, c]) => {
      const s = document.createElement("div");
      s.className = "sw"; s.dataset.color = nombre; s.style.background = c[0];
      s.title = this.t(nombre);
      s.innerHTML = `<span>${esc(this.t(nombre))}</span>`;
      s.onclick = () => { this.aplicarColor(nombre); this.api("/api/apariencia", { color: nombre }).catch(() => {}); };
      caja.append(s);
    });
    $("#btnColor").onclick = e => { e.stopPropagation(); $("#popColor").hidden = !$("#popColor").hidden; };
    $("#popColor").onclick = e => e.stopPropagation();
    document.addEventListener("click", () => { $("#popColor").hidden = true; });
    const poner = modo => { this.aplicarModo(modo); this.api("/api/apariencia", { modo }).catch(() => {}); };
    $("#btnModo").onclick = () => poner(this.estado.modo === "claro" ? "oscuro" : "claro");
    $$("#segModo button").forEach(b => { b.onclick = () => poner(b.dataset.modo); });
    this.aplicarColor(this.estado.color);
    this.aplicarModo(this.estado.modo || "oscuro");
  },

  // ------------------------------------------------------------- navegación
  /** Cambia de página. Si la página actual tiene cambios sin guardar: 1er clic avisa, 2º clic descarta. */
  mostrar(id) {
    const actual = this.pagina, g = this.guardas[actual];
    if (id !== actual && g && g.sucio()) {
      if (this.salidaPendiente !== id) {
        this.salidaPendiente = id;
        g.vibrar(true);
        this.toast(this.t("Tienes cambios sin guardar 💾"), "error");
        return false;
      }
      g.descartar();
    }
    this.salidaPendiente = null;
    this.pagina = id;
    $$("main.page").forEach(p => { p.hidden = p.id !== id; });
    $$("#nav button").forEach(b => b.classList.toggle("on", b.dataset.page === id));
    (this.alMostrar?.[id] || (() => {}))();
    return true;
  },

  /** Botón Guardar: rojo y sacudiéndose mientras haya cambios sin guardar. */
  vigilarCambios() {
    let tic = 0;
    setInterval(() => {
      tic++;
      Object.entries(this.guardas).forEach(([id, g]) => {
        const sucio = g.sucio();
        g.boton.classList.toggle("sucio", sucio);
        g.barra.classList.toggle("sucio", sucio);
        g.textoBoton.textContent = this.t(sucio ? "¡Guarda los cambios!" : g.texto);
        if (sucio && id === this.pagina && tic % 3 === 1) g.vibrar(false);
      });
    }, 500);
  },
  registrarGuarda(id, { barra, sucio, descartar, guardar }) {
    const boton = $(".guardar", barra);
    const textoBoton = $("span", boton);
    const g = {
      barra, boton, textoBoton, texto: textoBoton.dataset.t, sucio, descartar,
      vibrar(fuerte) {
        boton.classList.remove("sacudir", "fuerte");
        void boton.offsetWidth;
        boton.classList.add("sacudir");
        if (fuerte) boton.classList.add("fuerte");
      },
    };
    boton.onclick = guardar;
    $("[data-deshacer]", barra).onclick = () => { descartar(); this.salidaPendiente = null; };
    this.guardas[id] = g;
  },

  // ------------------------------------------------------------------- inicio
  async arrancar() {
    try {
      const [i18n, estado] = await Promise.all([this.get("/api/i18n"), this.get("/api/estado")]);
      this.T = i18n.tabla || {};
      this.estado = estado;
      document.documentElement.lang = i18n.idioma;
    } catch (e) {
      document.body.innerHTML = "<p style='padding:30px'>Voxia no responde. Cierra y vuelve a abrir la app.</p>";
      return;
    }
    this.traducir();
    $("#verTxt").textContent = "v" + this.estado.version;
    this.iniciarApariencia();
    $$("#nav button").forEach(b => { b.onclick = () => this.mostrar(b.dataset.page); });
    this.alMostrar = {};
    Panel.iniciar(this.estado);
    Lector.iniciar();
    Config.iniciar();
    Editor.iniciar();
    this.vigilarCambios();
    this.conectar();
    let guardado = null;
    try {
      guardado = sessionStorage.getItem("voxia_pagina");
      const aviso = sessionStorage.getItem("voxia_toast");
      sessionStorage.removeItem("voxia_pagina"); sessionStorage.removeItem("voxia_toast");
      if (aviso) this.toast(aviso);
    } catch { /* sin almacenamiento: no pasa nada */ }
    if (guardado && $("#" + guardado)) this.mostrar(guardado);
    (this.estado.avisos || []).forEach(a => this.dialogo({ texto: a }));
    // Ctrl+S guarda la página abierta
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        this.guardas[this.pagina]?.boton.click();
      }
    });
  },
};
const t = (s, kw) => Voxia.t(s, kw);

/* Lista editable (palabras, emotes, comandos…): etiquetas con ✕ y un campo para agregar */
function crearLista(el) {
  let valores = [];
  el.innerHTML = `<div class="tags"></div><div class="add"><input placeholder="${esc(t(el.dataset.ej || ""))}"><button class="btn sm">${esc(t("Agregar"))}</button></div>`;
  const tags = $(".tags", el), inp = $("input", el);
  const pintar = () => {
    tags.innerHTML = valores.length ? "" : `<span class="vacia">${esc(t("(vacía)"))}</span>`;
    valores.forEach((v, i) => {
      const s = document.createElement("span");
      s.className = "tag";
      s.innerHTML = `${esc(v)}<button title="${esc(t("Borrar"))}">✕</button>`;
      $("button", s).onclick = () => { valores.splice(i, 1); pintar(); };
      tags.append(s);
    });
  };
  const agregar = () => {
    inp.value.split(/[\n,]+/).map(x => x.trim()).filter(Boolean).forEach(v => { if (!valores.includes(v)) valores.push(v); });
    inp.value = "";
    pintar();
  };
  $("button", el.lastChild).onclick = agregar;
  inp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); agregar(); } });
  el._poner = v => { valores = [...(v || [])]; pintar(); };
  el._leer = () => {           // lo escrito sin pulsar «Agregar» también cuenta
    const extra = inp.value.split(/[\n,]+/).map(x => x.trim()).filter(x => x && !valores.includes(x));
    return [...valores, ...extra];
  };
  el._poner([]);
}
