// ✅ tu API en Render (o cambiá a localhost si estás probando)
const API_URL = "https://estimadorcostosautos.onrender.com/predict";

// ✅ este archivo lo genera tu pipeline y queda en /front junto a index.html
const CATALOG_URL = "./catalog.json";

const $ = (id) => document.getElementById(id);
let CATALOG = null;

function setHint(el, text) {
  if (!el) return;
  if (!text) {
    el.classList.add("hidden");
    el.textContent = "";
  } else {
    el.textContent = text;
    el.classList.remove("hidden");
  }
}

function setOptions(selectEl, options, placeholder = "(opcional)") {
  selectEl.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  selectEl.appendChild(first);

  (options || []).forEach(v => {
    const opt = document.createElement("option");
    opt.value = String(v);
    opt.textContent = String(v);
    selectEl.appendChild(opt);
  });
}

function resetSelect(selectEl, text, disabled = true) {
  selectEl.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = text;
  selectEl.appendChild(opt);
  selectEl.disabled = disabled;
  selectEl.value = "";
}

function showLoader() {
  const el = $("loader");
  el.classList.remove("hidden");
  el.classList.add("flex");
}

function hideLoader() {
  const el = $("loader");
  el.classList.add("hidden");
  el.classList.remove("flex");
}

function fillBrandsFromCatalog() {
  const brands = Object.keys(CATALOG || {}).sort((a, b) => a.localeCompare(b));
  const sel = $("marca");
  sel.innerHTML = `<option value="">Elegí una marca...</option>`;
  for (const b of brands) {
    const opt = document.createElement("option");
    opt.value = b;
    opt.textContent = b.toUpperCase();
    sel.appendChild(opt);
  }
}

function fillModels(brand) {
  const models = Object.keys((CATALOG?.[brand]) || {}).sort((a, b) => a.localeCompare(b));
  const sel = $("modelo_base");
  sel.disabled = false;
  setOptions(sel, models, "Elegí modelo...");
  if (models.length === 1) {
    sel.value = models[0];
    onModelChange(); // auto cascade
  }
}

function fillYearsFor(brand, model) {
  const info = CATALOG?.[brand]?.[model];
  const sel = $("anio");
  const hint = $("anioHint");

  if (!info) {
    resetSelect(sel, "Elegí modelo primero", true);
    setHint(hint, "");
    return;
  }

  sel.disabled = false;
  sel.innerHTML = `<option value="">Elegí año...</option>`;

  for (let y = info.year_max; y >= info.year_min; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    sel.appendChild(opt);
  }

  sel.value = String(info.year_max);
  setHint(hint, `Rango disponible: ${info.year_min}–${info.year_max}`);
}

// ✅ Combustible NUNCA desaparece.
// - si el catálogo trae lista -> usarla
// - si no trae -> fallback a genéricos
// - si hay 1 -> autoseleccionar (pero visible)
function fillCombustibleFor(brand, model) {
  const info = CATALOG?.[brand]?.[model];
  const sel = $("combustible");
  const hint = $("combHint");

  const fuels = (info?.combustibles?.length)
    ? info.combustibles
    : ["nafta", "diesel", "nafta-gnc"];

  setOptions(sel, fuels, "(opcional) Elegí combustible...");
  if (fuels.length === 1) sel.value = fuels[0];

  if (info?.combustibles?.length) {
    setHint(hint, `Sugeridos para este modelo: ${info.combustibles.join(", ")}`);
  } else {
    setHint(hint, "");
  }
}

// ✅ Tipo: solo se muestra si hay >1 opción.
// - 0 -> oculto + disabled
// - 1 -> oculto + se setea auto
// - >1 -> visible + enabled
function fillTipoFor(brand, model) {
  const info = CATALOG?.[brand]?.[model];
  const wrap = $("tipoWrap");
  const sel = $("tipo");

  const tipos = info?.tipos || [];

  if (!info || tipos.length === 0) {
    wrap.classList.add("hidden");
    resetSelect(sel, "(opcional) Elegí modelo primero", true);
    return;
  }

  if (tipos.length === 1) {
    wrap.classList.add("hidden");
    setOptions(sel, tipos, "(auto)");
    sel.value = tipos[0];
    sel.disabled = true;
    return;
  }

  wrap.classList.remove("hidden");
  setOptions(sel, tipos, "(opcional) Elegí tipo...");
  sel.disabled = false;
  sel.value = "";
}

// ✅ Trim como LISTADO (select).
// - muestra opciones reales
// - si 1 -> autoselecciona
function fillTrimFor(brand, model) {
  const info = CATALOG?.[brand]?.[model];
  const sel = $("version_trim");

  if (!info) {
    resetSelect(sel, "(opcional) Elegí modelo primero", true);
    return;
  }

  const versiones = info.versiones || [];
  if (!versiones.length) {
    resetSelect(sel, "(opcional) Sin versiones sugeridas", true);
    return;
  }

  sel.disabled = false;
  setOptions(sel, versiones, "(opcional) Elegí versión...");
  if (versiones.length === 1) sel.value = versiones[0];
}

// ✅ CV:
// - por defecto disabled
// - si hay 1 opción -> auto y disabled
// - si hay >1 -> enabled
function fillCvForSelection() {
  const brand = $("marca").value;
  const model = $("modelo_base").value;
  const trim = ($("version_trim").value || "").trim();

  const sel = $("cvSelect");
  const hint = $("cvHint");

  if (!brand || !model) {
    resetSelect(sel, "(opcional) Elegí modelo/versión primero", true);
    setHint(hint, "");
    return;
  }

  const info = CATALOG?.[brand]?.[model];
  if (!info) {
    resetSelect(sel, "(opcional) No hay datos para ese modelo", true);
    setHint(hint, "");
    return;
  }

  const byModel = info.cv_by_model || [];
  const byTrim = (info.cv_by_trim && trim && info.cv_by_trim[trim]) ? info.cv_by_trim[trim] : [];
  const options = (byTrim.length ? byTrim : byModel).map(String);

  if (!options.length) {
    resetSelect(sel, "(opcional) Sin CV sugeridos", true);
    setHint(hint, "");
    return;
  }

  setOptions(sel, options, "(opcional) Elegí CV...");
  // regla pedida:
  if (options.length === 1) {
    sel.value = options[0];
    sel.disabled = true;
  } else {
    sel.value = "";
    sel.disabled = false;
  }

  if (byTrim.length) {
    setHint(hint, `CV sugeridos para la versión "${trim}" (más frecuentes).`);
  } else {
    setHint(hint, `CV sugeridos para el modelo (completá trim para más precisión).`);
  }
}

function fillTranHint(brand, model) {
  const info = CATALOG?.[brand]?.[model];
  const tranHint = $("tranHint");
  if (info?.transmisiones?.length) {
    setHint(tranHint, `Sugeridas: ${info.transmisiones.join(", ")}`);
  } else {
    setHint(tranHint, "");
  }
}

function onModelChange() {
  const brand = $("marca").value;
  const model = $("modelo_base").value;

  // resets dependientes
  resetSelect($("anio"), "Elegí modelo primero", true);
  resetSelect($("tipo"), "(opcional) Elegí modelo primero", true);
  resetSelect($("version_trim"), "(opcional) Elegí modelo primero", true);
  resetSelect($("cvSelect"), "(opcional) Elegí modelo/versión primero", true);

  setHint($("anioHint"), "");
  setHint($("cvHint"), "");

  if (!brand || !model) return;

  fillYearsFor(brand, model);
  fillCombustibleFor(brand, model);
  fillTipoFor(brand, model);
  fillTrimFor(brand, model);
  fillTranHint(brand, model);

  // CV depende de trim/modelo
  fillCvForSelection();
}

function numOrNull(v) {
  const t = String(v ?? "").trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function strOrNull(v) {
  const t = String(v ?? "").trim();
  return t ? t : null;
}

function showError(msg) {
  $("errWrap").textContent = msg;
  $("errWrap").classList.remove("hidden");
}

function hideError() {
  $("errWrap").classList.add("hidden");
  $("errWrap").textContent = "";
}

function showResult({ p10, p50, p90 }) {
  $("p10").textContent = `USD ${p10}`;
  $("p50").textContent = `USD ${p50}`;
  $("p90").textContent = `USD ${p90}`;
  $("rangeText").textContent = `Rango sugerido: USD ${p10} – USD ${p90} (central: USD ${p50}).`;
  $("resultWrap").classList.remove("hidden");
}

async function init() {
  // defaults
  resetSelect($("modelo_base"), "Primero elegí marca", true);
  resetSelect($("anio"), "Elegí modelo primero", true);
  resetSelect($("tipo"), "(opcional) Elegí modelo primero", true);
  resetSelect($("version_trim"), "(opcional) Elegí modelo primero", true);
  resetSelect($("cvSelect"), "(opcional) Elegí modelo/versión primero", true);

  $("tipoWrap").classList.add("hidden");

  setHint($("anioHint"), "");
  setHint($("combHint"), "");
  setHint($("tranHint"), "");
  setHint($("cvHint"), "");

  $("kms").value = "120000";

  // cargar catálogo
  const res = await fetch(CATALOG_URL, { cache: "no-store" });
  if (!res.ok) throw new Error("No se pudo cargar catalog.json");
  CATALOG = await res.json();
  fillBrandsFromCatalog();

  // combustible: si todavía no hay modelo, dejamos genéricos
  setOptions($("combustible"), ["nafta", "diesel", "nafta-gnc"], "(opcional) Elegí combustible...");
}

$("marca").addEventListener("change", () => {
  const brand = $("marca").value;

  // reset dependientes
  resetSelect($("modelo_base"), "Primero elegí marca", true);
  resetSelect($("anio"), "Elegí modelo primero", true);
  resetSelect($("tipo"), "(opcional) Elegí modelo primero", true);
  resetSelect($("version_trim"), "(opcional) Elegí modelo primero", true);
  resetSelect($("cvSelect"), "(opcional) Elegí modelo/versión primero", true);

  $("tipoWrap").classList.add("hidden");

  setHint($("anioHint"), "");
  setHint($("cvHint"), "");

  // opcional: limpiar algunos
  $("transmision").value = "";
  

  // combustible nunca se oculta
  setOptions($("combustible"), ["nafta", "diesel", "nafta-gnc"], "(opcional) Elegí combustible...");
  $("combustible").value = "";

  if (!brand) return;
  fillModels(brand);
});

$("modelo_base").addEventListener("change", onModelChange);

// cuando cambia el trim, recalculamos CV (por trim si existe)
$("version_trim").addEventListener("change", () => {
  fillCvForSelection();
});

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  $("resultWrap").classList.add("hidden");

  const marca = strOrNull($("marca").value);
  const modelo_base = strOrNull($("modelo_base").value);
  const anio = Number($("anio").value);
  const kms = Number($("kms").value);

  if (!marca || !modelo_base || !anio || !kms) {
    showError("Completá Marca, Modelo, Año y Kms.");
    return;
  }

  const payload = {
    marca,
    modelo_base,
    anio,
    kms,

    // opcionales
    cv: numOrNull($("cvSelect").value),
    combustible: strOrNull($("combustible").value),
    tipo: strOrNull($("tipo").value),
    transmision: strOrNull($("transmision").value),
    version_trim: strOrNull($("version_trim").value),
  };

  // limpiar nulls/vacíos
  Object.keys(payload).forEach(k => (payload[k] === null || payload[k] === "") && delete payload[k]);

  showLoader();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300000);

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    const data = await res.json();
    if (!res.ok) throw new Error(typeof data === "string" ? data : JSON.stringify(data));
    showResult(data);
  } catch (err) {
    const msg =
      err?.name === "AbortError"
        ? "La API tardó demasiado (timeout). Probá de nuevo."
        : "No se pudo estimar. Detalle: " + (err.message || err);
    showError(msg);
  } finally {
    clearTimeout(timeoutId);
    hideLoader();
  }
});

init().catch(err => showError(err.message));
