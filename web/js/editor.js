/* Voxia — editor para recortar el sonido de la notificación (máximo 10 s) */
"use strict";
const Editor = {
  d: null, ini: 0, fin: 0, arrastre: null, sonando: null,

  iniciar() {
    const c = $("#edCanvas");
    c.addEventListener("pointerdown", e => { c.setPointerCapture(e.pointerId); this.presionar(this.xEv(e)); });
    c.addEventListener("pointermove", e => { if (this.arrastre) this.mover(this.xEv(e)); else this.cursor(this.xEv(e)); });
    c.addEventListener("pointerup", () => this.soltar());
    ["edIni", "edFin"].forEach(id => {
      const el = $("#" + id);
      el.addEventListener("change", () => this.desdeCajas());
      el.addEventListener("keydown", e => { if (e.key === "Enter") this.desdeCajas(); });
    });
    $("#edEscuchar").onclick = () => this.escuchar();
    $("#edParar").onclick = () => this.parar();
    $("#edCancelar").onclick = () => this.cerrar();
    $("#edGuardar").onclick = () => this.guardar();
    $("#edAudio").addEventListener("ended", () => this.parar());
    window.addEventListener("resize", () => { if (this.d) this.dibujar(); });
  },

  abrir(d) {
    this.d = d; this.ini = d.ini; this.fin = d.fin;
    $("#edInfo").textContent = t("{archivo}  ·  dura {dur} s.  Arrastra las marcas para elegir el trozo (máximo {max} s). Haz clic fuera de la selección para empezar una nueva.",
      { archivo: d.nombre, dur: (+d.dur).toFixed(1), max: (+d.max).toFixed(0) });
    $("#edFundido").checked = true; $("#edNorm").checked = false;
    $("#mEditor").hidden = false;
    this.dibujarRegla();
    this.dibujar();
  },

  cerrar() { this.parar(); $("#mEditor").hidden = true; this.d = null; },

  // conversión píxel <-> segundos (el lienzo mide 1640 px internos)
  get W() { return $("#edCanvas").width; },
  x(seg) { return this.d.dur ? seg / this.d.dur * this.W : 0; },
  seg(x) { return Math.max(0, Math.min(this.d.dur, x / this.W * this.d.dur)); },
  xEv(e) { const r = e.target.getBoundingClientRect(); return (e.clientX - r.left) / r.width * this.W; },

  colores() {
    const cs = getComputedStyle(document.documentElement);
    const v = n => cs.getPropertyValue(n).trim();
    return { acento: v("--accent"), txt: v("--accent-txt"), onda: v("--line2"), sel: v("--accent-soft"), texto: v("--text"), gris: v("--muted") };
  },

  dibujarRegla() {
    const c = $("#edRegla"), g = c.getContext("2d"), col = this.colores(), dur = this.d.dur;
    g.clearRect(0, 0, c.width, c.height);
    const paso = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].find(p => dur / p <= 14) || 600;
    g.fillStyle = g.strokeStyle = col.gris;
    g.font = "20px Segoe UI, sans-serif";
    g.textAlign = "center";
    for (let s = 0; s <= dur + 1e-6; s += paso) {
      const x = this.x(s);
      g.fillRect(x, 0, 2, 9);
      g.fillText(`${+s.toFixed(1)}s`, Math.min(Math.max(x, 20), c.width - 24), 30);
    }
  },

  dibujar() {
    const c = $("#edCanvas"), g = c.getContext("2d"), W = c.width, H = c.height, col = this.colores();
    g.clearRect(0, 0, W, H);
    const x1 = this.x(this.ini), x2 = this.x(this.fin);
    g.fillStyle = col.sel; g.fillRect(x1, 0, x2 - x1, H);
    const n = this.d.mn.length, mitad = H / 2, amp = H / 2 * 0.88, ancho = W / n;
    for (let i = 0; i < n; i++) {
      const x = i * ancho;
      g.fillStyle = x >= x1 && x <= x2 ? col.acento : col.onda;
      const arriba = mitad - this.d.mx[i] * amp, abajo = mitad - this.d.mn[i] * amp;
      g.fillRect(x, arriba, Math.max(1, ancho - 0.3), Math.max(2, abajo - arriba));
    }
    g.fillStyle = col.acento;
    [x1, x2].forEach(x => {
      g.fillRect(x - 2, 0, 4, H);
      g.beginPath(); g.roundRect(x - 13, 0, 26, 30, 6); g.fill();
    });
    g.fillStyle = col.txt; g.font = "bold 20px Segoe UI, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    [x1, x2].forEach(x => g.fillText("⇔", x, 15));
    if (this.sonando !== null) {
      const pos = this.ini + $("#edAudio").currentTime;
      if (pos <= this.fin) { g.fillStyle = col.texto; g.fillRect(this.x(pos) - 1.5, 0, 3, H); }
    }
    const largo = this.fin - this.ini;
    const lbl = $("#edLargo");
    lbl.textContent = t("Recorte: {largo} s / máx {max} s", { largo: largo.toFixed(2), max: (+this.d.max).toFixed(0) });
    lbl.className = "largo " + (largo <= this.d.max + 1e-6 ? "ok-t" : "bad-t");
    if (document.activeElement !== $("#edIni")) $("#edIni").value = this.ini.toFixed(2);
    if (document.activeElement !== $("#edFin")) $("#edFin").value = this.fin.toFixed(2);
  },

  cursor(x) {
    const x1 = this.x(this.ini), x2 = this.x(this.fin), cerca = 18;
    $("#edCanvas").style.cursor = Math.abs(x - x1) <= cerca || Math.abs(x - x2) <= cerca ? "ew-resize" : (x > x1 && x < x2 ? "grab" : "crosshair");
  },

  presionar(x) {
    const x1 = this.x(this.ini), x2 = this.x(this.fin), cerca = 18;
    if (Math.abs(x - x1) <= cerca) this.arrastre = ["ini", 0];
    else if (Math.abs(x - x2) <= cerca) this.arrastre = ["fin", 0];
    else if (x > x1 && x < x2) this.arrastre = ["mover", this.seg(x) - this.ini];
    else { this.ini = this.fin = this.seg(x); this.arrastre = ["fin", 0]; }
    this.dibujar();
  },

  mover(x) {
    const [modo, desfase] = this.arrastre, s = this.seg(x), d = this.d;
    if (modo === "ini") this.ini = Math.max(Math.min(s, this.fin - d.min), this.fin - d.max, 0);
    else if (modo === "fin") this.fin = Math.min(Math.max(s, this.ini + d.min), this.ini + d.max, d.dur);
    else { const largo = this.fin - this.ini; this.ini = Math.max(0, Math.min(s - desfase, d.dur - largo)); this.fin = this.ini + largo; }
    this.dibujar();
  },

  soltar() {
    if (!this.arrastre) return;
    this.arrastre = null;
    const d = this.d;
    if (this.fin - this.ini < d.min) {        // fue solo un clic: selección nueva de hasta 10 s
      this.fin = Math.min(d.dur, this.ini + d.max);
      if (this.fin - this.ini < d.min) this.ini = Math.max(0, this.fin - d.max);
    }
    this.dibujar();
  },

  desdeCajas() {
    const d = this.d;
    let ini = parseFloat($("#edIni").value.replace(",", ".")), fin = parseFloat($("#edFin").value.replace(",", "."));
    if (isNaN(ini) || isNaN(fin)) { this.dibujar(); return; }
    ini = Math.max(0, Math.min(ini, d.dur - d.min));
    fin = Math.max(ini + d.min, Math.min(fin, d.dur, ini + d.max));
    this.ini = ini; this.fin = fin;
    document.activeElement?.blur();
    this.dibujar();
  },

  params() {
    return `ini=${this.ini.toFixed(3)}&fin=${this.fin.toFixed(3)}&fundido=${$("#edFundido").checked ? 1 : 0}&normalizar=${$("#edNorm").checked ? 1 : 0}`;
  },

  escuchar() {
    this.parar();
    const a = $("#edAudio");
    a.src = `/api/notif/recorte.wav?${this.params()}&r=${Date.now()}`;
    a.volume = Math.max(0, Math.min(1, +$("#notifVol").value || 0.8));
    a.play().then(() => {
      this.sonando = true;
      const anim = () => { if (this.sonando === null || !this.d) return; this.dibujar(); requestAnimationFrame(anim); };
      requestAnimationFrame(anim);
    }).catch(err => Voxia.error(err));
  },

  parar() {
    const a = $("#edAudio");
    a.pause();
    this.sonando = null;
    if (this.d) this.dibujar();
  },

  async guardar() {
    this.parar();
    try {
      const r = await Voxia.api("/api/notif/guardar", {
        ini: this.ini, fin: this.fin, fundido: $("#edFundido").checked, normalizar: $("#edNorm").checked,
      });
      this.cerrar();
      Config.infoSonido(r);
      Voxia.toast(t("Notificación guardada ✔"));
    } catch (err) { Voxia.error(t("No pude guardar:\n{error}", { error: err.message })); }
  },
};
