/* Voxia — página Configuración */
"use strict";
const Config = {
  d: null, foto: null, cargado: false, motor: "", editado: {},

  iniciar() {
    $("#selMotor").onchange = () => { this.guardarEdicion(); this.pintarMotor($("#selMotor").value); };
    $("#btnKey").onclick = () => { const l = this.d.catalogo[this.motor]?.link; if (l) Voxia.api("/api/abrir", { url: l }); };
    $("#btnProbarVoz").onclick = () => this.probarVoz();
    $("#btnLogin").onclick = () => this.login();
    $("#btnLogout").onclick = () => this.logout();
    $("#btnAcceso").onclick = () => this.accesoDirecto();
    $("#btnEscuchar").onclick = () => Voxia.api("/api/notif/escuchar", { volumen: +$("#notifVol").value }).catch(e => Voxia.error(e));
    $("#btnSubir").onclick = () => $("#fileSonido").click();
    $("#fileSonido").onchange = () => this.subirSonido();
    $("#btnRecortar").onclick = () => this.recortarDeNuevo();
    $("#btnDefecto").onclick = () => this.sonidoDefecto();
    $("#btnExportar").onclick = () => this.exportar();
    $("#btnImportar").onclick = () => $("#fileRespaldo").click();
    $("#fileRespaldo").onchange = () => this.importar();
    $("#btnBuscar").onclick = () => this.buscarNovedades();
    $$("#configForm input[type=range]").forEach(r => {
      const o = r.nextElementSibling;
      r.addEventListener("input", () => { o.textContent = (+r.value).toFixed(2); });
    });
    Voxia.registrarGuarda("pConfig", {
      barra: $("#sbConfig"),
      sucio: () => this.cargado && JSON.stringify(this.leer()) !== this.foto,
      descartar: () => this.cargar(),
      guardar: () => this.guardar(),
    });
    Novedades.iniciar();
    this.cargar();
  },

  // ---------------------------------------------------------------- cargar
  async cargar() {
    const d = this.d = await Voxia.get("/api/config");
    this.editado = {};
    // idioma
    const seg = $("#segIdioma");
    seg.innerHTML = "";
    Object.entries(Voxia.estado.idiomas).forEach(([cod, nombre]) => {
      const b = document.createElement("button");
      b.textContent = nombre;
      b.classList.toggle("on", cod === Voxia.estado.idioma);
      b.onclick = () => this.cambiarIdioma(cod);
      seg.append(b);
    });
    $("#btnAcceso").disabled = !d.windows;
    // campos simples
    $$("#configForm [data-s][data-k]").forEach(el => {
      const v = this.valor(el.dataset.s, el.dataset.k);
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v ?? "";
      if (el.type === "range") el.nextElementSibling.textContent = (+el.value).toFixed(2);
    });
    // motor de voz
    const sel = $("#selMotor");
    sel.innerHTML = `<option value="">${esc(t("— Elige uno —"))}</option>` +
      Object.entries(d.catalogo).map(([pid, info]) => `<option value="${pid}">${esc(info.nombre)}</option>`).join("");
    sel.value = d.motor;
    this.pintarMotor(d.motor);
    // teclas rápidas
    $$("[data-tecla]").forEach(s => {
      const pares = s.dataset.parte === "mod" ? d.modificadores : d.teclas;
      s.innerHTML = pares.map(([v, txt]) => `<option value="${esc(v)}">${esc(txt)}</option>`).join("");
      const [mod, tecla] = d.atajos[s.dataset.tecla] || ["Ninguno", ""];
      s.value = s.dataset.parte === "mod" ? mod : (tecla || "Desactivada");
      s.disabled = !d.atajos_disponibles;
    });
    $("#verInst").textContent = d.version;
    this.cuenta();
    this.infoSonido();
    this.cargado = true;
    this.foto = JSON.stringify(this.leer());
  },

  valor(seccion, clave) {
    if (seccion === "twitch" && clave === "canal") return this.d.canal;
    if (seccion === "voz" && clave === "volumen") return this.d.volumen_voz;
    if (seccion === "notificacion" && clave === "volumen") return this.d.volumen_notif;
    if (seccion === "app") return this.d.app[clave];
    return "";
  },

  // --------------------------------------------------------- motor de voz
  guardarEdicion() {
    if (!this.motor) return;
    const vals = {};
    $$("#camposVoz [data-campo]").forEach(el => { vals[el.dataset.campo] = el.value; });
    this.editado[this.motor] = vals;
  },

  pintarMotor(pid) {
    this.motor = pid;
    const caja = $("#camposVoz");
    caja.innerHTML = "";
    const info = this.d.catalogo[pid];
    $("#motorPrecio").textContent = info?.precio || "";
    $("#btnKey").hidden = !(info && info.link && info.campos.some(c => c.tipo === "secreto"));
    if (!info) return;
    const vals = { ...this.d.valores_voz[pid], ...(this.editado[pid] || {}) };
    info.campos.forEach((c, i) => {
      const f = document.createElement("div");
      f.className = "f";
      const id = `campo_${pid}_${i}`;
      let entrada;
      if (c.tipo.startsWith("opcion:") || c.tipo === "voz" || c.tipo === "modelo") {
        const opciones = c.tipo.startsWith("opcion:") ? c.tipo.slice(7).split(",") : [];
        entrada = `<input id="${id}" list="${id}_l" data-campo="${esc(c.clave)}" autocomplete="off"><datalist id="${id}_l">` +
          opciones.map(o => `<option value="${esc(o)}">`).join("") + "</datalist>";
        if (c.tipo !== "opcion" && !c.tipo.startsWith("opcion:")) entrada += `<button class="btn sm" data-cargar="${esc(c.clave)}">${esc(t("Cargar"))}</button>`;
      } else {
        entrada = `<input id="${id}" data-campo="${esc(c.clave)}" ${c.tipo === "secreto" ? 'type="password" autocomplete="off"' : ""}>`;
      }
      f.innerHTML = `<label for="${id}">${esc(c.etiqueta)}</label><div class="in">${entrada}</div>` +
        (c.ayuda ? `<div class="ayuda">${esc(c.ayuda)}</div>` : "");
      caja.append(f);
      $(`#${id}`, f).value = vals[c.clave] ?? "";
      const b = $("[data-cargar]", f);
      if (b) b.onclick = () => this.cargarVoces(pid, $(`#${id}`, f), b);
    });
  },

  valoresMotor() {
    if (!this.motor) return {};
    const info = this.d.catalogo[this.motor];
    const salida = { voz: { motor: this.motor } };
    $$("#camposVoz [data-campo]").forEach(el => {
      (salida[info.seccion] ||= {})[el.dataset.campo] = el.value.trim();
    });
    return salida;
  },

  async cargarVoces(pid, input, boton) {
    const datos = {};
    $$("#camposVoz [data-campo]").forEach(el => { datos[el.dataset.campo] = el.value.trim(); });
    boton.disabled = true; boton.textContent = t("cargando…");
    try {
      const r = await Voxia.api("/api/voces", { pid, datos });
      $(`#${input.getAttribute("list")}`).innerHTML = r.lista.map(v => `<option value="${esc(v)}">`).join("");
      const actual = input.value.trim();
      if (!r.lista.some(v => v === actual || v.split("  (")[0] === actual)) input.value = r.lista[0];
      Voxia.toast(t("{n} voces cargadas: elige una de la lista", { n: r.lista.length }));
      input.focus();
    } catch (err) { Voxia.error(err); }
    boton.disabled = false; boton.textContent = t("Cargar");
  },

  async probarVoz() {
    const cambios = this.valoresMotor();
    if (!cambios.voz) { Voxia.toast(t("Primero elige un motor de voz."), "warn"); return; }
    cambios.voz.volumen = +$('[data-s="voz"][data-k="volumen"]').value;
    const b = $("#btnProbarVoz");
    b.disabled = true;
    try { await Voxia.api("/api/probar_voz", { cambios }); } catch (err) { Voxia.error(err); }
    b.disabled = false;
  },

  // ------------------------------------------------------------ leer / guardar
  leer() {
    const c = {};
    $$("#configForm [data-s][data-k]").forEach(el => {
      (c[el.dataset.s] ||= {})[el.dataset.k] = el.type === "checkbox" ? el.checked : el.type === "range" ? +el.value : el.value.trim();
    });
    Object.entries(this.valoresMotor()).forEach(([s, vals]) => Object.assign(c[s] ||= {}, vals));
    c.atajos = {};
    ["saltar", "callar"].forEach(acc => {
      const mod = $(`[data-tecla="${acc}"][data-parte="mod"]`).value;
      const tecla = $(`[data-tecla="${acc}"][data-parte="tecla"]`).value;
      c.atajos[acc] = !tecla || tecla === "Desactivada" ? "" : (!mod || mod === "Ninguno" ? tecla : `${mod}+${tecla}`);
    });
    return c;
  },

  async guardar() {
    let r;
    try {
      r = await Voxia.api("/api/config", { cambios: this.leer() });
    } catch (err) { Voxia.error(t("No pude guardar:\n{error}", { error: err.message })); return; }
    this.d.canal = $("#inCanal").value.trim().toLowerCase().replace(/^#/, "");
    $("#inCanal").value = this.d.canal;
    this.foto = JSON.stringify(this.leer());
    Voxia.salidaPendiente = null;
    if (r.fallidas?.length) {
      Voxia.dialogo({ texto: t("No pude usar estas teclas porque otro programa ya las ocupa:\n{teclas}\n\nElige otras en Configuración → Teclas rápidas.", { teclas: r.fallidas.join(", ") }) });
    }
    if (r.activo) {
      if (await Voxia.confirmar(t("Configuración guardada ✔") + "\n\n" + t("¿Reinicio el bot ahora para aplicar los cambios?"))) {
        Voxia.api("/api/reiniciar").catch(e => Voxia.error(e));
      }
    } else Voxia.toast(t("Configuración guardada ✔"));
  },

  // ----------------------------------------------------------------- idioma
  async cambiarIdioma(cod) {
    if (cod === Voxia.estado.idioma) return;
    if (Voxia.guardas.pConfig.sucio()) {
      Voxia.guardas.pConfig.vibrar(true);
      Voxia.toast(t("Guarda o deshaz los cambios antes de cambiar el idioma"), "error");
      return;
    }
    try { await Voxia.api("/api/idioma", { codigo: cod }); } catch (err) { Voxia.error(err); return; }
    try { sessionStorage.setItem("voxia_pagina", "pConfig"); } catch { /* no importa */ }
    location.reload();
  },

  async accesoDirecto() {
    try {
      await Voxia.api("/api/acceso_directo");
      Voxia.toast(t("Listo: quedó «Voxia» en tu escritorio ✔"));
    } catch (err) { Voxia.error(err); }
  },

  // ------------------------------------------------------------------ Twitch
  irATwitch() {
    Voxia.mostrar("pConfig");
    if (Voxia.pagina !== "pConfig") return;
    const c = $("#cardTwitch");
    c.scrollIntoView({ behavior: "smooth", block: "center" });
    c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash");
    Voxia.toast(t("Conecta tu cuenta de Twitch 👉"), "acc");
  },

  async cuenta() {
    const el = $("#cuentaTxt");
    $("#btnLogout").hidden = !this.d.tiene_token;
    if (!this.d.tiene_token) { el.className = "estado bad-t"; el.textContent = t("✖ Sin sesión"); return; }
    el.className = "estado muted"; el.textContent = t("verificando…");
    try {
      const r = await Voxia.get("/api/twitch/cuenta");
      if (r.estado === "ok") { el.className = "estado ok-t"; el.textContent = t("✔ Conectado como {login}  (vence en ~{dias} días)", r); }
      else { el.className = "estado bad-t"; el.textContent = t(r.estado === "sin" ? "✖ Sin sesión" : "✖ La sesión venció: inicia sesión de nuevo"); }
    } catch { el.textContent = ""; }
  },

  async login() {
    const el = $("#cuentaTxt"), b = $("#btnLogin");
    el.className = "estado warn-t"; el.textContent = t("⏳ Esperando que autorices en el navegador…");
    b.disabled = true;
    try {
      const r = await Voxia.api("/api/twitch/login", { canal: $("#inCanal").value });
      this.d.tiene_token = true;
      // el canal quedó guardado: que no cuente como cambio sin guardar
      const sucio = Voxia.guardas.pConfig.sucio();
      this.d.canal = r.canal; $("#inCanal").value = r.canal;
      if (!sucio) this.foto = JSON.stringify(this.leer());
      else { const f = JSON.parse(this.foto); f.twitch.canal = r.canal; this.foto = JSON.stringify(f); }
      Voxia.dialogo({ texto: t("✔ ¡Conectado como {login}!\n\nYa puedes pulsar «Iniciar (Twitch)».", { login: r.login }) });
    } catch (err) { Voxia.error(err); }
    b.disabled = false;
    this.cuenta();
  },

  async logout() {
    if (!(await Voxia.confirmar(t("¿Cerrar la sesión de Twitch de {app}?")))) return;
    await Voxia.api("/api/twitch/logout").catch(e => Voxia.error(e));
    this.d.tiene_token = false;
    this.cuenta();
  },

  // ----------------------------------------------------------- notificación
  async infoSonido(r) {
    r ||= await Voxia.get("/api/notif/info");
    $("#sonidoTxt").textContent = `${r.nombre} · ${(+r.dur).toFixed(1)} s`;
    $("#btnRecortar").disabled = !r.original;
  },

  async subirSonido() {
    const f = $("#fileSonido").files[0];
    $("#fileSonido").value = "";
    if (!f) return;
    try {
      Editor.abrir(await Voxia.subir("/api/notif/subir", f));
    } catch (err) { Voxia.error(err); }
  },

  async recortarDeNuevo() {
    try { Editor.abrir(await Voxia.api("/api/notif/original")); } catch (err) { Voxia.error(err); }
  },

  async sonidoDefecto() {
    if (!(await Voxia.confirmar(t("¿Volver al sonido que trae {app}?")))) return;
    try {
      this.infoSonido(await Voxia.api("/api/notif/defecto"));
      Voxia.toast(t("Notificación guardada ✔"));
    } catch (err) { Voxia.error(err); }
  },

  // ---------------------------------------------------------------- respaldo
  async exportar() {
    const con = await Voxia.dialogo({
      texto: t("¿Incluir tu sesión de Twitch y tus API keys en el respaldo?\n\nSí: para pasarlo a otro PC tuyo.\nNo: más seguro si lo vas a compartir (después solo inicias sesión de nuevo)."),
      botones: [{ v: null, txt: t("Cancelar") }, { v: "no", txt: t("No") }, { v: "si", txt: t("Sí"), cls: "accent" }],
    });
    if (!con) return;
    try {
      const r = await Voxia.api("/api/respaldo/exportar", { claves: con === "si" });
      if (r.descargar) {
        const a = document.createElement("a");
        a.href = `/api/respaldo/exportar?claves=${con === "si" ? 1 : 0}`;
        a.download = "";
        document.body.append(a); a.click(); a.remove();
        Voxia.toast(t("Respaldo guardado ✔"));
      } else if (r.ruta) {
        Voxia.dialogo({ texto: t("Respaldo guardado ✔\n\n{ruta}", { ruta: r.ruta }) });
      }
    } catch (err) { Voxia.error(t("No pude guardar:\n{error}", { error: err.message })); }
  },

  async importar() {
    const f = $("#fileRespaldo").files[0];
    $("#fileRespaldo").value = "";
    if (!f) return;
    if (Panel.activo) { Voxia.dialogo({ texto: t("Primero detén el bot (■ Detener) y vuelve a intentarlo.") }); return; }
    let info;
    try { info = await Voxia.subir("/api/respaldo/info", f); } catch (err) { Voxia.error(err); return; }
    const detalle = t("Respaldo del {fecha} (versión {v}).", { fecha: info.fecha, v: info.version });
    if (!(await Voxia.confirmar(t("¿Reemplazar tu configuración por la de este respaldo?") + "\n\n" + detalle + "\n" +
      t("Tu configuración actual queda guardada en la carpeta «backups».")))) return;
    try {
      await Voxia.api("/api/respaldo/importar", { clave: info.clave });
    } catch (err) { Voxia.error(err); return; }
    try {
      sessionStorage.setItem("voxia_toast", t("Configuración importada ✔"));
      sessionStorage.setItem("voxia_pagina", "pConfig");
    } catch { /* no importa */ }
    location.reload();
  },

  async buscarNovedades() {
    const el = $("#novTxt");
    el.className = "estado muted"; el.textContent = t("Buscando…");
    const r = await Voxia.api("/api/novedades/buscar").catch(() => ({ estado: "error" }));
    const m = {
      error: ["bad-t", "✖ " + t("No pude revisar (¿hay internet?)")],
      nada: ["muted", t("Todavía no hay versiones publicadas")],
      al_dia: ["ok-t", "✔ " + t("Tienes la última versión")],
      nueva: ["acc-t", "🎉 " + t("Hay una versión nueva: {v}", { v: r.version })],
    }[r.estado];
    el.className = "estado " + m[0]; el.textContent = m[1];
  },
};

/* Aviso de versión nueva (barra de arriba) */
const Novedades = {
  info: null,
  iniciar() {
    $("#updClose").onclick = () => { $("#updBar").hidden = true; Voxia.api("/api/novedades/cerrar"); };
    $("#updNotes").onclick = () => this.notas();
    $("#updNow").onclick = () => this.actualizar();
    Voxia.on("novedad", d => this.mostrar(d));
    Voxia.on("descarga", d => this.progreso(d));
    if (Voxia.estado.novedad) this.mostrar(Voxia.estado.novedad);
    if (Voxia.estado.descarga) this.progreso(Voxia.estado.descarga);
  },
  mostrar(info) {
    this.info = info;
    $("#updTxt").textContent = t("Hay una versión nueva de {app}: {v}", { v: info.version });
    $("#updBar").hidden = false;
    $("#novTxt").className = "estado acc-t";
    $("#novTxt").textContent = "🎉 " + t("Hay una versión nueva: {v}", { v: info.version });
  },
  async notas() {
    const i = this.info;
    const v = await Voxia.dialogo({
      titulo: t("Novedades de la versión {v}:", { v: i.version }),
      html: `<div class="notas">${esc(i.notas || t("(Sin descripción)"))}</div><div style="height:14px"></div>`,
      botones: [{ v: false, txt: t("Cerrar") }, { v: true, txt: t("Abrir la página de descarga"), cls: "accent" }],
    });
    if (v) Voxia.api("/api/abrir", { url: i.pagina });
  },
  async actualizar() {
    const i = this.info;
    if (!Voxia.estado.es_exe) { Voxia.api("/api/abrir", { url: i.pagina }); return; }
    if (!(await Voxia.confirmar(t("¿Descargar e instalar la versión {v}?\n\nVoxia se va a cerrar y se abrirá sola con la versión nueva. Tu configuración no se toca.", { v: i.version })))) return;
    $("#updNow").disabled = true;
    try { await Voxia.api("/api/novedades/actualizar"); } catch (err) { $("#updNow").disabled = false; Voxia.error(err); }
  },
  progreso(d) {
    $("#updBar").hidden = false;
    if (d.error) {
      $("#updNow").disabled = false;
      $("#updTxt").textContent = "✖ " + t("No pude actualizar");
      Voxia.error(d.error);
      return;
    }
    $("#updNow").disabled = true;
    $("#updTxt").textContent = d.listo ? t("Instalando… Voxia se abrirá sola en unos segundos.")
      : t("Descargando la versión {v}… {p}%", { v: this.info?.version || "", p: d.p });
  },
};
