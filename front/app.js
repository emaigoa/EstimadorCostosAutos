// ===== CONFIG =====
const API_URL = "https://estimadorcostosautos.onrender.com/predict";
const INDEX_URL = "./data/index.json";
const BRAND_URL = (brand) => `./data/brands/${encodeURIComponent(brand)}.json`;

const INDEX_CACHE_KEY = "autos_index_cache_v1";
const BRAND_CACHE_PREFIX = "autos_brand_cache_v1_";
const CACHE_TTL_MS = 1000 * 60 * 60 * 24; // 24h

const DEFAULT_COMBUSTIBLES = ["nafta", "diesel", "nafta-gnc", "gnc", "hibrido", "electrico"];
const DEFAULT_TRANSMISIONES = ["manual", "automatica"];
const DEFAULT_DIRECCIONES = ["electrica", "asistida", "mecanica", "hidraulica"];

// ===== DOM helpers =====
const $ = (id) => document.getElementById(id);
function show(el) { el?.classList.remove("hidden"); }
function hide(el) { el?.classList.add("hidden"); }

function setError(msg) {
  const box = $("errBox");
  if (!box) return;
  box.textContent = msg || "";
  msg ? show(box) : hide(box);
}

// Loader INLINE (solo predict)
function setPredictLoading(isOn, msg = "Cargando su estimación............") {
  const wrap = $("predictLoader");
  const m = $("loaderMsg");
  const btn = $("btnSubmit");

  if (m) m.textContent = msg;

  if (isOn) {
    show(wrap);
    if (btn) btn.disabled = true;
  } else {
    hide(wrap);
    if (btn) btn.disabled = false;
  }
}

function str(v) {
  const s = String(v ?? "").trim();
  return s || null;
}

function money(x) {
  return Number(x).toLocaleString("es-AR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  });
}

function setHint(id, text) {
  const el = $(id);
  if (!el) return;
  el.textContent = text || "";
}

/** Capitaliza SOLO el texto visible; el value se mantiene tal cual */
function prettyLabel(v) {
  const s = String(v ?? "").trim();
  if (!s) return "";

  return s
    .split(/(\s+|[-/])/g) // conserva separadores
    .map((part) => {
      if (part.trim() === "" || part === "-" || part === "/") return part;
      // códigos: AT, CVT, TDI, 1.6, etc.
      if (/^[A-Z0-9.]+$/.test(part)) return part;
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    })
    .join("");
}

function setOptions(select, values, placeholder, disableIfEmpty = false) {
  if (!select) return;

  select.innerHTML = "";
  const frag = document.createDocumentFragment();

  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  frag.appendChild(opt);

  (values || []).forEach((v) => {
    const o = document.createElement("option");
    o.value = v;                   // value real (API)
    o.textContent = prettyLabel(v); // label visible capitalizado
    frag.appendChild(o);
  });

  select.appendChild(frag);

  const empty = !(values && values.length);
  select.disabled = disableIfEmpty && empty;
}

function resetSelect(sel, placeholder) {
  setOptions(sel, [], placeholder, true);
}

// ===== Cache helpers =====
function cacheRead(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.ts || !parsed?.data) return null;
    if (Date.now() - parsed.ts > CACHE_TTL_MS) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

function cacheWrite(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
  } catch {}
}

// ===== DATA =====
let INDEX = null;        // { brand: [models] }
let BRAND_MODELS = null; // { model: meta } para la marca actual
let BRAND_LOADED = null;

async function loadIndex() {
  const cached = cacheRead(INDEX_CACHE_KEY);
  if (cached) { INDEX = cached; return; }

  const r = await fetch(INDEX_URL, { cache: "force-cache" });
  if (!r.ok) throw new Error(`No pude cargar ${INDEX_URL} (HTTP ${r.status})`);
  const data = await r.json();
  INDEX = data;
  cacheWrite(INDEX_CACHE_KEY, data);
}

async function loadBrand(brand) {
  if (!brand) return;
  if (BRAND_LOADED === brand && BRAND_MODELS) return;

  const key = BRAND_CACHE_PREFIX + brand;
  const cached = cacheRead(key);
  if (cached) {
    BRAND_LOADED = brand;
    BRAND_MODELS = cached;
    return;
  }

  const r = await fetch(BRAND_URL(brand), { cache: "force-cache" });
  if (!r.ok) throw new Error(`No pude cargar data de marca "${brand}" (HTTP ${r.status})`);
  const data = await r.json();
  BRAND_LOADED = brand;
  BRAND_MODELS = data;
  cacheWrite(key, data);
}

function getBrands() { return Object.keys(INDEX || {}).sort(); }
function getModelsForBrand(brand) { return (INDEX?.[brand] || []).slice(); }
function getMeta(model) { return BRAND_MODELS?.[model] || null; }

// ===== INIT =====
async function init() {
  setError("");

  // defaults
  resetSelect($("modelo_base"), "Elegí marca primero");
  resetSelect($("anio"), "Elegí modelo primero");
  resetSelect($("version_trim"), "(opcional) Elegí modelo primero");

  setOptions($("combustible"), DEFAULT_COMBUSTIBLES, "(opcional) Combustible");
  setOptions($("transmision"), DEFAULT_TRANSMISIONES, "(opcional) Transmisión");
  setOptions($("direccion"), DEFAULT_DIRECCIONES, "(opcional) Dirección");

  hide($("tipoWrap"));
  resetSelect($("tipo"), "(opcional) Elegí tipo");
  setHint("anioHint", "");

  // Cargar index (sin loader)
  try {
    await loadIndex();
    setOptions($("marca"), getBrands(), "Elegí marca...");
    $("marca").disabled = false;
  } catch (err) {
    console.error(err);
    setError(`❌ Error cargando índice: ${err?.message || err}`);
    return;
  }

  // Marca change
  $("marca")?.addEventListener("change", async () => {
    const brand = str($("marca").value);

    setError("");
    hide($("resultWrap"));

    resetSelect($("modelo_base"), "Elegí marca primero");
    resetSelect($("anio"), "Elegí modelo primero");
    resetSelect($("version_trim"), "(opcional) Elegí modelo primero");
    hide($("tipoWrap"));
    resetSelect($("tipo"), "(opcional) Elegí tipo");
    setHint("anioHint", "");

    if (!brand) return;

    setOptions($("modelo_base"), getModelsForBrand(brand), "Elegí modelo...");

    // data pesada por marca (sin loader)
    try {
      await loadBrand(brand);
    } catch (err) {
      console.error(err);
      setError(`❌ Error cargando marca: ${err?.message || err}`);
    }
  });

  // Modelo change
  $("modelo_base")?.addEventListener("change", () => {
    const model = str($("modelo_base").value);

    setError("");
    hide($("resultWrap"));

    resetSelect($("anio"), "Elegí modelo primero");
    resetSelect($("version_trim"), "(opcional) Elegí versión");
    hide($("tipoWrap"));
    resetSelect($("tipo"), "(opcional) Elegí tipo");
    setHint("anioHint", "");

    if (!model) return;

    const meta = getMeta(model);
    if (!meta) {
      setError("⚠️ Todavía no cargó la data de la marca. Elegí la marca y esperá un toque.");
      return;
    }

    // años
    const years = [];
    for (let y = meta.year_max; y >= meta.year_min; y--) years.push(String(y));
    setOptions($("anio"), years, "Elegí año...");
    setHint("anioHint", `Rango: ${meta.year_min}–${meta.year_max}`);

    // versiones
    setOptions($("version_trim"), meta.versiones || [], "(opcional) Versión");

    // tipos
    const tipos = meta.tipos || null;
    if (Array.isArray(tipos) && tipos.length) {
      show($("tipoWrap"));
      setOptions($("tipo"), tipos, "(opcional) Tipo");
    } else {
      hide($("tipoWrap"));
      resetSelect($("tipo"), "(opcional) Elegí tipo");
    }

    // overrides
    setOptions($("combustible"), meta.combustibles || DEFAULT_COMBUSTIBLES, "(opcional) Combustible");
    setOptions($("transmision"), meta.transmisiones || DEFAULT_TRANSMISIONES, "(opcional) Transmisión");
    setOptions($("direccion"), meta.direcciones || DEFAULT_DIRECCIONES, "(opcional) Dirección");
  });

  // Submit (acá sí aparece el loader inline)
  $("form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");
    hide($("resultWrap"));

    setPredictLoading(true);

    try {
      const payload = {
        marca: str($("marca").value),
        modelo_base: str($("modelo_base").value),
        version_trim: str($("version_trim").value),
        anio: Number($("anio").value),
        kms: Number($("kms").value),
        combustible: str($("combustible").value),
        transmision: str($("transmision").value),
        direccion: str($("direccion").value),
        aire: $("aireChk")?.checked,
        cristales: $("cristalesChk")?.checked,
        tipo: str($("tipo")?.value),
      };

      Object.keys(payload).forEach((k) => {
        if (payload[k] == null) delete payload[k];
        if (typeof payload[k] === "number" && Number.isNaN(payload[k])) delete payload[k];
      });

      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(`API error (HTTP ${res.status}) ${txt ? "- " + txt : ""}`);
      }

      const data = await res.json();

      $("p10").textContent = money(data.p10);
      $("p50").textContent = money(data.p50);
      $("p90").textContent = money(data.p90);

      show($("resultWrap"));
    } catch (err) {
      console.error(err);
      setError(`❌ Error al predecir: ${err?.message || err}`);
    } finally {
      setPredictLoading(false);
    }
  });
}

init();
