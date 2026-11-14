"use strict";

const VARS = {
  razon_corriente: { nombre: "Razón corriente", tipo: "veces" },
  prueba_acida: { nombre: "Prueba ácida", tipo: "veces" },
  kt_activos: { nombre: "Capital de trabajo / activos", tipo: "pct" },
  efectivo_activos: { nombre: "Efectivo / activos", tipo: "pct" },
  endeudamiento: { nombre: "Endeudamiento", tipo: "pct" },
  concentracion_cp: { nombre: "Deuda de corto plazo / deuda total", tipo: "pct" },
  patrimonio_pasivos: { nombre: "Patrimonio / pasivos", tipo: "veces" },
  cobertura_intereses: { nombre: "Cobertura de intereses", tipo: "veces" },
  roa: { nombre: "Rentabilidad del activo (ROA)", tipo: "pct" },
  roe: { nombre: "Rentabilidad del patrimonio (ROE)", tipo: "pct" },
  margen_neto: { nombre: "Margen neto", tipo: "pct" },
  margen_operacional: { nombre: "Margen operacional", tipo: "pct" },
  utilidades_ret_activos: { nombre: "Ganancias acumuladas / activos", tipo: "pct" },
  rotacion_activos: { nombre: "Rotación de activos", tipo: "veces" },
  crecimiento_ingresos: { nombre: "Crecimiento de ingresos", tipo: "pct" },
  log_activos: { nombre: "Tamaño de la empresa", tipo: "tamano" },
  sector: { nombre: "Sector", tipo: "texto" },
  region: { nombre: "Región", tipo: "texto" },
};
const FICHA = ["razon_corriente", "endeudamiento", "roa", "margen_operacional", "cobertura_intereses", "crecimiento_ingresos"];
const SEM = {
  dificultad: { nombre: "En dificultad", clase: "p-dificultad" },
  rojo: { nombre: "Riesgo alto", clase: "p-rojo" },
  amarillo: { nombre: "Riesgo medio", clase: "p-amarillo" },
  verde: { nombre: "Riesgo bajo", clase: "p-verde" },
};
const MOTIVO = {
  patrimonio_negativo: "Su patrimonio es negativo: los pasivos superan a los activos.",
  perdida_sin_cobertura: "Tuvo pérdida neta y su resultado operativo no alcanzó a cubrir los costos financieros.",
};
const PAGINA = 30;

const nf = (d) => new Intl.NumberFormat("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const st = { resumen: null, filas: [], F: {}, dic: {}, filtradas: [], mostradas: 0, sel: -1, filtroSem: new Set(), indice: [] };

function fmtVar(nombre, valor) {
  const v = VARS[nombre] || { tipo: "veces" };
  if (valor === null || valor === undefined || valor === "") return "sin dato";
  if (v.tipo === "texto") {
    const lista = st.dic[nombre];
    return typeof valor === "number" && lista ? lista[valor] : String(valor);
  }
  if (v.tipo === "pct") return nf(1).format(valor * 100) + " %";
  if (v.tipo === "tamano") return dinero(Math.pow(10, valor));
  return nf(2).format(valor) + " veces";
}

function dinero(v) {
  if (v === null || v === undefined) return "sin dato";
  const factor = /miles/i.test(st.resumen.meta.unidad || "") ? 1000 : 1;
  const pesos = v * factor;
  if (Math.abs(pesos) >= 1e12) return "$" + nf(1).format(pesos / 1e12) + " billones";
  if (Math.abs(pesos) >= 1e9) return "$" + nf(1).format(pesos / 1e9) + " mil millones";
  if (Math.abs(pesos) >= 1e6) return "$" + nf(0).format(pesos / 1e6) + " millones";
  return "$" + nf(0).format(pesos);
}

function pctTexto(p) {
  const v = p * 100;
  return v >= 99 ? nf(1).format(Math.min(v, 99.9)) + " %" : nf(0).format(v) + " %";
}

const val = (fila, campo) => fila[st.F[campo]];
const texto = (fila, campo) => st.dic[campo][fila[st.F[campo]]] || "";

function estadoHTML(sem) {
  return `<span class="estado"><span class="punto ${SEM[sem].clase}" aria-hidden="true"></span>${SEM[sem].nombre}</span>`;
}

/* ---------- Carga ---------- */
async function cargar() {
  try {
    const [r, e] = await Promise.all([fetch("data/resumen.json"), fetch("data/empresas.json")]);
    if (!r.ok || !e.ok) throw new Error(`HTTP ${r.status}/${e.status}`);
    st.resumen = await r.json();
    const emp = await e.json();
    st.filas = emp.filas;
    st.dic = emp.diccionarios;
    emp.campos.forEach((c, i) => (st.F[c] = i));
    st.indice = st.filas.map((f) => norm(val(f, "nombre")) + " " + val(f, "nit"));
  } catch (err) {
    $("conteo").textContent = `No se pudieron cargar los datos (${err.message}). Si abriste el archivo directamente, sírvelo con: python -m http.server -d docs 8000`;
    return;
  }
  iniciar();
}

function iniciar() {
  const m = st.resumen.meta;
  if (m.demo) $("aviso-demo").hidden = false;
  $("entrada").textContent =
    `Un modelo de machine learning entrenado con los estados financieros que ${nf(0).format(m.n_empresas)} empresas reportaron a la Superintendencia de Sociedades con corte a ${m.anio_puntuado}. ` +
    `Cada una recibe un semáforo según su probabilidad de entrar en dificultad en ${m.anio_puntuado + 1}, con la explicación de qué indicadores la empujan.`;

  llenarSelect("f-sector", st.dic.sector);
  llenarSelect("f-region", st.dic.region);
  llenarSelect("f-depto", st.dic.departamento);
  const chips = $("f-sem");
  for (const k of Object.keys(SEM)) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.dataset.sem = k; b.setAttribute("aria-pressed", "false");
    b.innerHTML = `<span class="punto ${SEM[k].clase}" aria-hidden="true"></span>${SEM[k].nombre}`;
    b.addEventListener("click", () => {
      st.filtroSem.has(k) ? st.filtroSem.delete(k) : st.filtroSem.add(k);
      b.setAttribute("aria-pressed", st.filtroSem.has(k));
      filtrar();
    });
    chips.appendChild(b);
  }
  let t;
  $("q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(filtrar, 120); });
  ["f-sector", "f-region", "f-depto", "f-orden"].forEach((id) => $(id).addEventListener("change", filtrar));
  $("mas").addEventListener("click", () => pintarLista(st.mostradas + PAGINA));

  pieEspectro();
  filtrar();
  comparacion();
  factores();
  sectores();
  metodo();
  pie();
  iniciarEspectro();

  const hash = location.hash.match(/^#nit-(\d+)$/);
  if (hash) {
    const i = st.filas.findIndex((f) => val(f, "nit") === hash[1]);
    if (i >= 0) seleccionar(i, false);
  }
}

function llenarSelect(id, valores) {
  const s = $(id);
  for (const v of valores) if (v) s.insertAdjacentHTML("beforeend", `<option>${esc(v)}</option>`);
}

/* ---------- Filtros y lista ---------- */
function filtrar() {
  const q = norm($("q").value.trim());
  const sector = $("f-sector").value, region = $("f-region").value, depto = $("f-depto").value;
  const res = [];
  for (let i = 0; i < st.filas.length; i++) {
    const f = st.filas[i];
    if (q && !st.indice[i].includes(q)) continue;
    if (sector && texto(f, "sector") !== sector) continue;
    if (region && texto(f, "region") !== region) continue;
    if (depto && texto(f, "departamento") !== depto) continue;
    if (st.filtroSem.size && !st.filtroSem.has(val(f, "sem"))) continue;
    res.push(i);
  }
  const orden = $("f-orden").value;
  if (orden === "nombre") res.sort((a, b) => val(st.filas[a], "nombre").localeCompare(val(st.filas[b], "nombre"), "es"));
  if (orden === "ingresos") res.sort((a, b) => (val(st.filas[b], "ingresos") ?? -Infinity) - (val(st.filas[a], "ingresos") ?? -Infinity));
  st.filtradas = res;
  st.marcadas = new Set(res);
  pintarLista(PAGINA);
  dibujarEspectro();
}

function pintarLista(n) {
  const total = st.filtradas.length;
  st.mostradas = Math.min(n, total);
  $("conteo").textContent = total === st.filas.length
    ? `${nf(0).format(total)} empresas`
    : `${nf(0).format(total)} de ${nf(0).format(st.filas.length)} empresas coinciden`;
  const filas = st.filtradas.slice(0, st.mostradas).map((i) => {
    const f = st.filas[i];
    const p = val(f, "prob");
    const lugar = [texto(f, "ciudad"), texto(f, "sector")].filter(Boolean).join(", ");
    return `<tr data-i="${i}" tabindex="0" aria-selected="${i === st.sel}">
      <td><span class="nombre">${esc(val(f, "nombre"))}</span><span class="sub">NIT ${esc(val(f, "nit"))}${lugar ? ", " + esc(lugar) : ""}</span></td>
      <td class="num">${p === null ? "–" : nf(1).format(p * 100) + " %"}</td>
      <td>${estadoHTML(val(f, "sem"))}</td></tr>`;
  });
  $("filas").innerHTML = filas.length ? filas.join("")
    : `<tr><td colspan="3" class="vacio">Ninguna empresa coincide. Prueba con menos palabras, otro NIT o quita algún filtro.</td></tr>`;
  for (const tr of $("filas").querySelectorAll("tr[data-i]")) {
    const i = Number(tr.dataset.i);
    tr.addEventListener("click", () => seleccionar(i));
    tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); seleccionar(i); } });
  }
  const resto = total - st.mostradas;
  $("mas").hidden = resto <= 0;
  $("mas").textContent = `Mostrar ${Math.min(PAGINA, resto)} más`;
}

/* ---------- Ficha de empresa ---------- */
function seleccionar(i, actualizarHash = true) {
  st.sel = i;
  const f = st.filas[i];
  const m = st.resumen.meta;
  const sem = val(f, "sem");
  const sector = texto(f, "sector");
  const med = st.resumen.medianas_sector[sector] || st.resumen.medianas_sector["Todas"];
  const ficha = $("ficha");
  ficha.dataset.sem = sem;

  let veredicto;
  if (sem === "dificultad") {
    veredicto = `<div class="veredicto"><span class="punto ${SEM[sem].clase}" style="width:1.4rem;height:1.4rem" aria-hidden="true"></span>
      <p><b>Ya presenta dificultad en ${m.anio_puntuado}.</b> ${MOTIVO[val(f, "motivo")] || ""}</p></div>`;
  } else {
    const p = val(f, "prob"), pct = val(f, "pct");
    veredicto = `<div class="veredicto"><span class="cifra">${nf(0).format(p * 100)} %</span>
      <p>${estadoHTML(sem)}<br>Probabilidad estimada de entrar en dificultad en ${m.anio_puntuado + 1}. Tiene más riesgo que el ${pctTexto(pct)} de las empresas sin dificultad.</p></div>`;
  }

  const filasInd = FICHA.map((v) => `<tr><th scope="row">${VARS[v].nombre}</th><td class="num">${fmtVar(v, val(f, v))}</td><td class="num med">${fmtVar(v, med?.[v])}</td></tr>`).join("");

  let motivos = "";
  const sube = val(f, "sube"), baja = val(f, "baja");
  if (sube.length || baja.length) {
    const maximo = Math.max(...[...sube, ...baja].map((x) => Math.abs(x[2])), 1e-6);
    const item = (x, clase) => {
      const nombre = st.dic.variable[x[0]];
      return `<li><span>${VARS[nombre]?.nombre || nombre}: <b>${esc(fmtVar(nombre, x[1]))}</b></span>
        <span class="carril" title="Contribución SHAP ${nf(2).format(x[2])}"><span class="${clase}" style="width:${(Math.abs(x[2]) / maximo) * 100}%"></span></span></li>`;
    };
    motivos = (sube.length ? `<h4>Lo que más aumenta su riesgo</h4><ul class="motivos">${sube.map((x) => item(x, "sube")).join("")}</ul>` : "")
      + (baja.length ? `<h4>Lo que lo reduce</h4><ul class="motivos">${baja.map((x) => item(x, "baja")).join("")}</ul>` : "");
  }

  const z = val(f, "z");
  ficha.innerHTML = `
    <h3>${esc(val(f, "nombre"))}</h3>
    <p class="sub">${[`NIT ${esc(val(f, "nit"))}`, esc([texto(f, "ciudad"), texto(f, "departamento")].filter(Boolean).join(", ")), esc(sector)].filter(Boolean).join(". ")}.
      Ingresos ${dinero(val(f, "ingresos"))}; activos ${dinero(val(f, "activos"))}.</p>
    ${veredicto}
    <p class="altman">Z'' de Altman: <b>${z === null ? "sin dato" : nf(2).format(z)}</b>${z === null ? "" : `, zona ${esc(val(f, "zona")).toLowerCase()}`}.</p>
    ${motivos}
    <h4>Indicadores frente a la mediana del sector</h4>
    <table class="indicadores"><thead><tr><th></th><th class="num">Empresa</th><th class="num med">Mediana</th></tr></thead><tbody>${filasInd}</tbody></table>
    <p class="enlace-ficha"><a href="#nit-${esc(val(f, "nit"))}">Enlace directo a esta ficha</a></p>`;

  for (const tr of $("filas").querySelectorAll("tr[data-i]")) tr.setAttribute("aria-selected", Number(tr.dataset.i) === i);
  if (actualizarHash) history.replaceState(null, "", `#nit-${val(f, "nit")}`);
  dibujarEspectro();
  if (window.matchMedia("(max-width: 900px)").matches || !actualizarHash) ficha.scrollIntoView({ block: "nearest" });
}

/* ---------- Espectro de riesgo ---------- */
function colores() {
  const cs = getComputedStyle(document.documentElement);
  const c = (n) => cs.getPropertyValue(n).trim();
  return { dificultad: c("--dificultad"), rojo: c("--rojo"), amarillo: c("--amarillo"), verde: c("--verde"), tinta: c("--tinta"), regla: c("--regla"), foco: c("--foco") };
}

function altura(f) {
  return val(f, "sem") === "dificultad" ? 1 : 0.18 + 0.82 * (val(f, "pct") ?? 0);
}

function dibujarEspectro() {
  const cv = $("espectro");
  if (!cv || !st.filas.length) return;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const col = colores();
  const n = st.filas.length, paso = w / n;
  const filtro = st.marcadas && st.marcadas.size !== n;
  for (let i = 0; i < n; i++) {
    const f = st.filas[i];
    ctx.globalAlpha = !filtro || st.marcadas.has(i) ? 1 : 0.14;
    ctx.fillStyle = col[val(f, "sem")];
    const alto = h * altura(f);
    ctx.fillRect(i * paso, h - alto, Math.max(paso, 1), alto);
  }
  ctx.globalAlpha = 1;
  if (st.sel >= 0) {
    const x = st.sel * paso + paso / 2;
    ctx.fillStyle = col.tinta;
    ctx.fillRect(x - 1.5, 0, 3, h);
    ctx.beginPath(); ctx.moveTo(x - 7, 0); ctx.lineTo(x + 7, 0); ctx.lineTo(x, 9); ctx.closePath(); ctx.fill();
  }
}

function iniciarEspectro() {
  const cv = $("espectro"), tip = $("espectro-tip");
  const indice = (ev) => {
    const r = cv.getBoundingClientRect();
    return Math.min(st.filas.length - 1, Math.max(0, Math.floor(((ev.clientX - r.left) / r.width) * st.filas.length)));
  };
  cv.addEventListener("mousemove", (ev) => {
    const i = indice(ev), f = st.filas[i];
    const p = val(f, "prob");
    tip.textContent = `${val(f, "nombre")}: ${SEM[val(f, "sem")].nombre}${p === null ? "" : ", " + nf(1).format(p * 100) + " %"}`;
    tip.style.left = ev.clientX - cv.getBoundingClientRect().left + "px";
    tip.hidden = false;
  });
  cv.addEventListener("mouseleave", () => (tip.hidden = true));
  cv.addEventListener("click", (ev) => seleccionar(indice(ev)));
  new ResizeObserver(dibujarEspectro).observe(cv);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { dibujarEspectro(); comparacion(); });
}

function pieEspectro() {
  const s = st.resumen.semaforo, total = st.resumen.meta.n_empresas;
  $("espectro-pie").innerHTML = "Cada línea es una empresa, de mayor a menor riesgo. "
    + Object.keys(SEM).map((k) => `<span class="clave"><span class="punto ${SEM[k].clase}" aria-hidden="true"></span>${SEM[k].nombre}: <b>${nf(0).format(s[k])}</b> (${nf(1).format((s[k] / total) * 100)} %)</span>`).join("");
}

/* ---------- Comparación de modelos ---------- */
function comparacion() {
  const mo = st.resumen.modelo, col = colores();
  const tenue = getComputedStyle(document.documentElement).getPropertyValue("--tenue").trim();
  const series = [
    { clave: "altman", color: col.amarillo, i: 0 },
    { clave: "logit", color: tenue, i: 1 },
    { clave: "xgboost", color: col.foco, i: 2 },
  ];
  $("intro-comparacion").textContent =
    `Los modelos se entrenaron con empresas sanas de ${mo.anios_entrenamiento[0]} a ${mo.anios_entrenamiento.at(-1)}, se ajustaron con ${mo.anio_validacion} y se evaluaron con ${mo.anio_prueba}: ` +
    `¿cuáles de las ${nf(0).format(mo.n_prueba)} empresas sanas de ${mo.anio_prueba} entraron en dificultad en ${mo.anio_prueba + 1}? Le pasó al ${nf(1).format(mo.tasa_base_prueba * 100)} %. ` +
    `El Z'' de Altman se usa tal como se publicó en 1995, sin reentrenar.`;

  const svg = $("roc"), x0 = 44, y0 = 16, L = 296;
  const px = (v) => x0 + v * L, py = (v) => y0 + (1 - v) * L;
  let g = `<title id="roc-titulo">Curvas ROC de los tres modelos en el año de prueba</title>`;
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    g += `<line class="eje" x1="${px(t)}" y1="${py(0)}" x2="${px(t)}" y2="${py(1)}"/><line class="eje" x1="${px(0)}" y1="${py(t)}" x2="${px(1)}" y2="${py(t)}"/>`;
    g += `<text x="${px(t)}" y="${py(0) + 16}" text-anchor="middle">${nf(0).format(t * 100)}%</text><text x="${px(0) - 6}" y="${py(t) + 4}" text-anchor="end">${nf(0).format(t * 100)}%</text>`;
  }
  g += `<line x1="${px(0)}" y1="${py(0)}" x2="${px(1)}" y2="${py(1)}" stroke="${tenue}" stroke-dasharray="4 4"/>`;
  for (const s of series) {
    const pts = mo.roc[s.clave].map(([f, t]) => `${px(f).toFixed(1)},${py(t).toFixed(1)}`).join(" ");
    g += `<polyline class="linea" stroke="${s.color}" points="${pts}"/>`;
  }
  g += `<text x="${px(0.5)}" y="${py(0) + 34}" text-anchor="middle">Empresas sanas marcadas por error</text>`;
  g += `<text transform="translate(12 ${py(0.5)}) rotate(-90)" text-anchor="middle">Deterioros detectados</text>`;
  svg.setAttribute("viewBox", "0 0 360 372");
  svg.innerHTML = g;

  const mejor = mo.metricas.reduce((a, b, i) => (b.auc_roc > mo.metricas[a].auc_roc ? i : a), 0);
  $("tabla-metricas").innerHTML = `<thead><tr><th>Modelo</th><th>AUC-ROC</th><th>AUC-PR</th><th>Detecta en el 10 % más riesgoso</th></tr></thead><tbody>` +
    mo.metricas.map((m, i) => `<tr class="${i === mejor ? "destacada" : ""}"><td><span class="muestra" style="background:${series[i].color}"></span>${esc(m.modelo)}</td>
      <td>${nf(3).format(m.auc_roc)}</td><td>${nf(3).format(m.auc_pr)}</td><td>${nf(0).format(m.captura_top10 * 100)} %</td></tr>`).join("") + `</tbody>`;

  const z = mo.altman_zonas;
  $("nota-zonas").textContent =
    `La zona de peligro de Altman marcó al ${nf(1).format(z.fraccion_en_peligro * 100)} % de las empresas sanas; de ellas, el ${nf(0).format(z.peligro_precision * 100)} % sí entró en dificultad, ` +
    `y en total detectó el ${nf(0).format(z.peligro_recall * 100)} % de los casos. Si XGBoost marca la misma cantidad de empresas, acierta en el ${nf(0).format(z.xgb_mismo_tamano_precision * 100)} % ` +
    `y detecta el ${nf(0).format(z.xgb_mismo_tamano_recall * 100)} %. AUC-PR es la métrica más exigente cuando los casos positivos son pocos.`;
}

/* ---------- Factores (SHAP) ---------- */
function barras(id, items, etiqueta) {
  const max = Math.max(...items.map((x) => x.valor), 1e-9);
  $(id).innerHTML = items.map((x) => `<div class="barra"><span>${esc(etiqueta(x))}</span>
    <span class="carril"><span style="width:${(x.valor / max) * 100}%"></span></span><span class="num">${nf(2).format(x.valor)}</span></div>`).join("");
}

function factores() {
  const mo = st.resumen.modelo;
  barras("familias", mo.importancia_familias, (x) => x.familia);
  barras("variables", mo.importancia_variables.slice(0, 10), (x) => VARS[x.variable]?.nombre || x.variable);
}

/* ---------- Sectores ---------- */
function sectores() {
  const orden = ["dificultad", "rojo", "amarillo", "verde"];
  const col = { dificultad: "var(--dificultad)", rojo: "var(--rojo)", amarillo: "var(--amarillo)", verde: "var(--verde)" };
  $("tabla-sectores").innerHTML = `<thead><tr><th>Sector</th><th class="num col-n">Empresas</th><th>Semáforo</th><th class="num">En alerta</th><th class="num col-prob">Prob. media</th></tr></thead><tbody>` +
    st.resumen.por_sector.map((s) => `<tr><td>${esc(s.nombre)}</td><td class="num col-n">${nf(0).format(s.n)}</td>
      <td><span class="pila" role="img" aria-label="${orden.map((k) => `${SEM[k].nombre}: ${s[k]}`).join(", ")}">${orden.map((k) => `<span style="width:${(s[k] / s.n) * 100}%;background:${col[k]}"></span>`).join("")}</span></td>
      <td class="num">${nf(1).format(s.pct_alerta * 100)} %</td><td class="num col-prob">${s.prob_media === null ? "–" : nf(1).format(s.prob_media * 100) + " %"}</td></tr>`).join("") + `</tbody>`;
}

/* ---------- Metodología ---------- */
function metodo() {
  const m = st.resumen.meta, mo = st.resumen.modelo, u = m.umbrales;
  $("metodo").innerHTML = `
    <h3>Datos</h3>
    <p>Estados de situación financiera, de resultado integral y carátulas que las sociedades reportan a la Superintendencia de Sociedades bajo NIIF, publicados como datos abiertos en datos.gov.co. Se usa el corte del 31 de diciembre de cada año, los estados individuales o separados (no los consolidados) y el último reporte de cada empresa si lo retransmitió.</p>
    <h3>Qué se predice</h3>
    <p>Una empresa está en dificultad si su patrimonio es negativo, o si tuvo pérdida neta y su resultado operativo no alcanzó a cubrir los costos financieros. El modelo estima la probabilidad de que una empresa sin dificultad este año pase a estarlo el siguiente. Es un indicador aproximado de deterioro, no de quiebra: no existe una etiqueta pública de insolvencia lista para cruzar.</p>
    <h3>Modelos</h3>
    <p>El Z'' de Altman (1995) combina capital de trabajo, ganancias acumuladas y EBIT sobre activos con patrimonio sobre pasivos: Z'' = 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4, con zona de peligro por debajo de 1,1 y zona segura por encima de 2,6. Se compara con una regresión logística que reestima los pesos de esas cuatro razones y con XGBoost, que usa 16 indicadores de liquidez, endeudamiento, rentabilidad, actividad y tamaño, más sector y región. La validación es temporal: se entrena con años anteriores y se evalúa con el más reciente que tiene resultado conocido. La salida de XGBoost se calibra (método de Platt, con el año de validación) para que sus probabilidades se puedan leer como tales.</p>
    <h3>Semáforo y explicaciones</h3>
    <p>Las empresas que ya están en dificultad aparecen aparte. Entre las demás, riesgo alto es el ${nf(0).format((1 - u.rojo_desde_percentil) * 100)} % con mayor probabilidad, riesgo medio el siguiente ${nf(0).format((u.rojo_desde_percentil - u.amarillo_desde_percentil) * 100)} % y riesgo bajo el resto. Las explicaciones de cada empresa son valores SHAP exactos para árboles: cuánto movió cada indicador la predicción frente al promedio.</p>
    <h3>Límites</h3>
    <p>Solo incluye sociedades obligadas a reportar a Supersociedades; las vigiladas por otras superintendencias (financiera, de salud, de servicios públicos) pueden faltar. Las empresas que dejan de reportar salen de la muestra y no cuentan como deterioro, lo que puede subestimar el riesgo. Los indicadores dependen de la calidad de lo reportado. Un riesgo alto es una señal para revisar, no una conclusión sobre la empresa.</p>
    <p>Modelo entrenado con ${nf(0).format(mo.n_entrenamiento)} observaciones empresa-año y ${mo.mejor_iteracion + 1} árboles. Datos actualizados el ${esc(m.generado)}.</p>`;
}

function pie() {
  const m = st.resumen.meta;
  const autor = m.autoria?.nombre ? (m.autoria.enlace ? `<a href="${esc(m.autoria.enlace)}">${esc(m.autoria.nombre)}</a>` : esc(m.autoria.nombre)) : "";
  const repo = m.repositorio ? ` Código en <a href="${esc(m.repositorio)}">GitHub</a>.` : "";
  $("pie-fuente").innerHTML = `${autor ? "Elaborado por " + autor + ". " : ""}Fuente: ${esc(m.fuente)}, licencia ${esc(m.licencia)}. Los resultados derivados se comparten con la misma licencia.${repo}`;
}

cargar();
