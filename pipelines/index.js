// index.js
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// =====================
// MARCAS
// =====================
const BRANDS_RAW = [
  "Alfa Romeo","Audi","BAIC","BMW","BYD","Changan","Chery","Chevrolet","Chrysler","Citroën",
  "D.S.","Daihatsu","Dodge","Ferrari","Fiat","Ford","GMC","GWM","Honda","Hyundai","Isuzu","Iveco",
  "JAC","Jaguar","Jeep","Kia","Lancia","Land Rover","Lexus","Mazda","Mercedes-Benz","MG","Mini",
  "Mitsubishi","Nissan","Opel","Peugeot","Porsche","RAM","Range Rover","Renault","Seat","SsangYong",
  "Subaru","Suzuki","SWM","Toyota","Volkswagen","Volvo",
];

// =====================
// SETTINGS
// =====================
const BASE_OUT_DIR = path.join(__dirname, "pdfs");
const HEADLESS = true;
const VIEWPORT = { width: 1280, height: 800 };
const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

// =====================
// PODA + SPEED
// =====================
const WAIT_SHORT = 200;         // antes 1200
const MIN_BRAND_RESULTS = 20;   // marca
const MIN_VAR_RESULTS = 1;     // filtros por nivel
const START_FROM = 1;
const STEP = 48;
const MAX_PAGES = 42;           // bajalo mientras probás

// Títulos (con alias por si cambia ML)
const TITLE_ALIASES = {
  fuel: ["Tipo de combustible", "Combustible"],
  trans: ["Transmisión", "Transmision"],
  dir: ["Dirección", "Direccion"],
};

// EXTRAS fijos que querés (y “ambos”)
const EXTRAS_TO_USE = [
  { slug: "sin-extras", path: "" },
  { slug: "con-aire-acondicionado", path: "con-aire-acondicionado" },
  { slug: "con-cristales-electricos", path: "con-cristales-electricos" },
  { slug: "aire__cristales", path: "con-aire-acondicionado/con-cristales-electricos" },
];

function safeName(s) {
  return String(s).replace(/^https?:\/\//, "").replace(/[^\w\-]+/g, "_").slice(0, 180);
}

function slugifyBrand(name) {
  let s = String(name).trim();
  s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  s = s.replace(/\./g, "");
  s = s.replace(/&/g, "and");
  s = s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+/g, "-").replace(/(^-|-$)/g, "");
  return s;
}

const BRAND_SLUG_OVERRIDES = {
  "d-s": "ds",
  "mercedes-benz": "mercedes-benz",
  "alfa-romeo": "alfa-romeo",
  "land-rover": "land-rover",
  "range-rover": "range-rover",
  "ssangyong": "ssangyong",
};

function brandToSlug(brandRaw) {
  const s = slugifyBrand(brandRaw);
  return BRAND_SLUG_OVERRIDES[s] || s;
}

function buildBrandBaseUrl(brandSlug) {
  return `https://autos.mercadolibre.com.ar/${brandSlug}/_ITEM*CONDITION_2230581`;
}

async function acceptCookiesIfAny(page) {
  const candidates = [/aceptar cookies/i, /aceptar/i, /entendido/i, /^ok$/i];
  for (const rx of candidates) {
    try {
      const btn = page.getByRole("button", { name: rx });
      await btn.waitFor({ timeout: 1500 });
      await btn.click({ timeout: 1500 });
      await page.waitForTimeout(150);
      return;
    } catch (_) {}
  }
}

async function hasNoResults(page) {
  const noResultsTitle = page.getByText(/no encontramos resultados para tu búsqueda/i);
  const altNoResults = page.getByText(/no hay publicaciones que coincidan|sin resultados/i);

  try {
    await Promise.race([
      noResultsTitle.waitFor({ timeout: 1200 }),
      altNoResults.waitFor({ timeout: 1200 }),
    ]);
  } catch (_) {}

  return (
    (await noResultsTitle.isVisible().catch(() => false)) ||
    (await altNoResults.isVisible().catch(() => false))
  );
}

// total resultados arriba ("12.345 resultados")
async function getResultsCount(page) {
  try {
    const el = await page.waitForSelector("span.ui-search-search-result__quantity-results", { timeout: 4000 });
    const text = (await el.textContent()) || "";
    const clean = text.replace(/\./g, "");
    const m = clean.match(/\d+/);
    return m ? parseInt(m[0], 10) : 0;
  } catch {
    return 0;
  }
}

function normalizeCountFromTitle(title) {
  const clean = String(title || "").replace(/\./g, "");
  const m = clean.match(/(\d+)\s*resultados?/i);
  return m ? parseInt(m[1], 10) : 0;
}

function slugFromFilterLabel(label) {
  // "Nafta, 62 resultados" -> "nafta"
  const base = String(label || "").split(",")[0].trim().toLowerCase();
  return base.replace(/[^\w]+/g, "-").replace(/-+/g, "-").replace(/(^-|-$)/g, "") || "unknown";
}

/**
 * Devuelve opciones disponibles de un filtro en el sidebar:
 * [{ label, href, count, slug }]
 */
async function getAvailableFilterOptions(page, possibleTitles, minCount = MIN_VAR_RESULTS) {
  await page.waitForSelector("div.ui-search-filter-dl", { timeout: 4000 }).catch(() => {});

  const raw = await page.evaluate(({ possibleTitles }) => {
    const blocks = Array.from(document.querySelectorAll("div.ui-search-filter-dl"));

    const pickBlock = () => {
      for (const t of possibleTitles) {
        const found = blocks.find(b => {
          const h3 = b.querySelector("h3.ui-search-filter-dt-title");
          return h3 && (h3.textContent || "").trim().toLowerCase() === t.trim().toLowerCase();
        });
        if (found) return found;
      }
      return null;
    };

    const block = pickBlock();
    if (!block) return [];

    const links = Array.from(block.querySelectorAll("a.ui-search-link"));
    return links.map(a => ({
      label: (a.getAttribute("aria-label") || a.getAttribute("title") || a.textContent || "").trim(),
      href: a.href,
      title: a.getAttribute("title") || "",
    }));
  }, { possibleTitles });

  return raw
    .map(o => ({ ...o, count: normalizeCountFromTitle(o.title), slug: slugFromFilterLabel(o.label) }))
    .filter(o => o.href && o.count > minCount);
}

// Inserta extras antes de "/_ITEM"
function injectExtrasToUrl(url, extrasPath) {
  if (!extrasPath) return url;
  if (url.includes("/_ITEM")) return url.replace("/_ITEM", `/${extrasPath}/_ITEM`);
  return url.replace(/\/$/, "") + `/${extrasPath}`;
}

// Pagina agregando/reemplazando _Desde_
function withDesde(url, desde) {
  if (/_Desde_\d+/i.test(url)) return url.replace(/_Desde_\d+/i, `_Desde_${desde}`);
  if (/_ITEM/i.test(url)) return url.replace(/\/_ITEM/i, `/_Desde_${desde}_ITEM`);
  return url.replace(/\/?$/, `/_Desde_${desde}`);
}

(async () => {
  fs.mkdirSync(BASE_OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ viewport: VIEWPORT, userAgent: USER_AGENT });

  // Acelera: bloquea imágenes/fonts/media
  await context.route("**/*", (route) => {
    const type = route.request().resourceType();
    if (type === "image" || type === "font" || type === "media") return route.abort();
    route.continue();
  });

  // Reusar una sola page (mucho más rápido)
  const page = await context.newPage();

  for (const brandRaw of BRANDS_RAW) {
    const brandSlug = brandToSlug(brandRaw);
    const brandUrl = buildBrandBaseUrl(brandSlug);

    console.log(`\n🔍 Marca: ${brandSlug}`);
    console.log(`   → ${brandUrl}`);

    try {
      // ===== Nivel Marca =====
      await page.goto(brandUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
      await acceptCookiesIfAny(page);
      await page.waitForTimeout(WAIT_SHORT);

      const brandCount = await getResultsCount(page);
      if (brandCount <= MIN_BRAND_RESULTS) {
        console.log(`   ⛔ Salteo marca (${brandCount} <= ${MIN_BRAND_RESULTS})`);
        continue;
      }
      console.log(`   ✅ Marca OK (${brandCount})`);

      // ===== Nivel Combustible =====
      const fuels = await getAvailableFilterOptions(page, TITLE_ALIASES.fuel, MIN_VAR_RESULTS);
      if (!fuels.length) {
        console.log(`   ⚠️ No pude leer combustibles en sidebar. Salteo marca.`);
        continue;
      }

      for (const fuel of fuels) {
        console.log(`\n   ⛽ Fuel: ${fuel.slug} (${fuel.count})`);

        await page.goto(fuel.href, { waitUntil: "domcontentloaded", timeout: 90000 });
        await acceptCookiesIfAny(page);
        await page.waitForTimeout(WAIT_SHORT);
        if (await hasNoResults(page)) continue;

        // ===== Nivel Transmisión =====
        const trans = await getAvailableFilterOptions(page, TITLE_ALIASES.trans, MIN_VAR_RESULTS);
        if (!trans.length) {
          console.log(`      ⚠️ Sin transmisiones con >${MIN_VAR_RESULTS}.`);
          continue;
        }

        for (const tr of trans) {
          console.log(`\n      ⚙️ Trans: ${tr.slug} (${tr.count})`);

          await page.goto(tr.href, { waitUntil: "domcontentloaded", timeout: 90000 });
          await acceptCookiesIfAny(page);
          await page.waitForTimeout(WAIT_SHORT);
          if (await hasNoResults(page)) continue;

          // ===== Nivel Dirección =====
          const dirs = await getAvailableFilterOptions(page, TITLE_ALIASES.dir, MIN_VAR_RESULTS);
          if (!dirs.length) {
            console.log(`         ⚠️ Sin direcciones con >${MIN_VAR_RESULTS}.`);
            continue;
          }

          for (const dir of dirs) {
            console.log(`\n         🧭 Dir: ${dir.slug} (${dir.count})`);

            await page.goto(dir.href, { waitUntil: "domcontentloaded", timeout: 90000 });
            await acceptCookiesIfAny(page);
            await page.waitForTimeout(WAIT_SHORT);
            if (await hasNoResults(page)) continue;

            // ===== Nivel Extras (SOLO aire / cristales / ambos) =====
            for (const ex of EXTRAS_TO_USE) {
              const exUrlBase = injectExtrasToUrl(dir.href, ex.path);
              const outDir = path.join(BASE_OUT_DIR, brandSlug, fuel.slug, tr.slug, dir.slug, ex.slug);
              fs.mkdirSync(outDir, { recursive: true });

              console.log(`\n            🎛️ Extra: ${ex.slug}`);

              // ===== Paginación + PDF =====
              for (let p = 0; p < MAX_PAGES; p++) {
                const desde = START_FROM + p * STEP;
                const pagedUrl = withDesde(exUrlBase, desde);

                console.log(`               Página ${p + 1}/${MAX_PAGES} Desde_${desde}`);
                await page.goto(pagedUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
                await acceptCookiesIfAny(page);

                // Sin sleep grande: espera real del listado
                await page.waitForSelector("li.ui-search-layout__item", { timeout: 4000 }).catch(() => {});
                if (await hasNoResults(page)) {
                  console.log(`               ⚠️ Sin resultados. Corto paginación.`);
                  break;
                }

                const file = path.join(
                  outDir,
                  `${safeName(`${brandSlug}_${fuel.slug}_${tr.slug}_${dir.slug}_${ex.slug}_Desde_${desde}`)}.pdf`
                );

                await page.pdf({
                  path: file,
                  format: "A4",
                  printBackground: true,
                  margin: { top: "10mm", right: "10mm", bottom: "10mm", left: "10mm" },
                  preferCSSPageSize: true,
                });

                console.log(`               ✅ Guardado: ${file}`);
                await page.waitForTimeout(WAIT_SHORT);
              }
            }
          }
        }
      }
    } catch (err) {
      console.log(`   ❌ Error en marca ${brandSlug}: ${err?.message || err}`);
      continue;
    }
  }

  await page.close().catch(() => {});
  await browser.close();
  console.log("✅ Listo. PDFs en ./pdfs/<marca>/<combustible>/<transmision>/<direccion>/<extras>/");
})();
