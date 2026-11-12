/* Voxia — página Parámetros (estilo Speaker.bot) */
"use strict";
const Lector = {
  foto: null, cargado: false,

  iniciar() {
    $$("#lectorForm .lista[data-k]").forEach(crearLista);
    $("#recDetectar").onclick = () => this.detectar();
    $("#recQuitar").onclick = () => { $("#recId").value = ""; this.pintarRecompensa(); };
    Voxia.registrarGuarda("pLector", {
      barra: $("#sbLector"),
      sucio: () => this.cargado && JSON.stringify(this.leer()) !== this.foto,
      descartar: () => this.cargar(),
      guardar: () => this.guardar(),
    });
    Voxia.on("recompensa", d => this.recompensa(d));
    Voxia.on("estado", d => { if (!d.activo && this.esperando) { this.esperando = false; this.pintarRecompensa(); } });
    this.cargar();
  },

  campos() { return $$("#lectorForm [data-k]"); },

  async cargar() {
    const d = await Voxia.get("/api/lector");
    const opciones = (sel, pares) => { sel.innerHTML = pares.map(([v, txt]) => `<option value="${esc(v)}">${esc(txt)}</option>`).join(""); };
    opciones($("#selModo"), d.modos);
    opciones($("#selUnidad"), d.unidades);
    opciones($("#selFiltro"), d.filtros);
    this.campos().forEach(el => {
      const v = d.op[el.dataset.k];
      if (el.classList.contains("lista")) el._poner(v);
      else if (el.type === "checkbox") el.checked = !!v;
      else el.value = v ?? "";
    });
    this.esperando = d.esperando;
    this.pintarRecompensa();
    this.cargado = true;
    this.foto = JSON.stringify(this.leer());
  },

  leer() {
    const op = {};
    this.campos().forEach(el => {
      const k = el.dataset.k;
      if (el.classList.contains("lista")) op[k] = el._leer();
      else if (el.type === "checkbox") op[k] = el.checked;
      else op[k] = el.value.trim();
    });
    return op;
  },

  async guardar() {
    const op = this.leer();
    for (const el of $$("#lectorForm input.num")) {
      if (!/^-?\d+$/.test(el.value.trim())) {
        el.focus();
        Voxia.toast(t("«{campo}» tiene que ser un número entero.", { campo: t(el.dataset.n || el.dataset.k) }), "error");
        return;
      }
    }
    try {
      await Voxia.api("/api/lector", { op });
    } catch (err) { Voxia.error(t("No pude guardar:\n{error}", { error: err.message })); return; }
    this.foto = JSON.stringify(this.leer());
    Voxia.salidaPendiente = null;
    Voxia.toast(t("Parámetros guardados ✔"));
  },

  pintarRecompensa(usuario = "") {
    const el = $("#recEstado");
    if (this.esperando) { el.className = "estado warn-t"; el.textContent = t("⏳ Canjea la recompensa en tu chat…"); return; }
    if ($("#recId").value) {
      el.className = "estado ok-t";
      el.textContent = t("✔ Detectada") + (usuario ? `  (${t("canjeada por {usuario}", { usuario })})` : "");
    } else {
      el.className = "estado muted";
      el.textContent = t("Cualquier canje con texto");
    }
  },

  async detectar() {
    try {
      await Voxia.api("/api/recompensa/detectar");
    } catch (err) { Voxia.dialogo({ texto: err.message }); return; }
    this.esperando = true;
    this.pintarRecompensa();
  },

  /** Llegó el canje que se esperaba (el servidor ya lo guardó). */
  recompensa(d) {
    const estabaSucio = Voxia.guardas.pLector.sucio();
    this.esperando = false;
    $("#recId").value = d.id;
    if (!estabaSucio) this.foto = JSON.stringify(this.leer());
    else {      // lo guardado ya trae la recompensa: que la «foto» también la tenga
      const f = JSON.parse(this.foto); f.recompensa_id = d.id; this.foto = JSON.stringify(f);
    }
    this.pintarRecompensa(d.usuario);
    Voxia.toast(t("Recompensa detectada ✔"));
  },
};
