const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// Marcas comunes en Argentina (podés sumar/sacar)
const BRANDS = [
  "volkswagen",
  "fiat",
  "renault",
  "ford",
  "chevrolet",
  "peugeot",
  "toyota",
  "citroen",
  "nissan",
  "honda",
];

// Combustibles pedidos
const FUELS = ["nafta", "diesel", "nafta-gnc"];

// Desde 1 hasta 42*48 (=2016), sumando 48
const START_FROM = 1;
const END_FROM = 42 * 48; // 2016
const STEP = 48;

// Settings
const BASE_OUT_DIR = path.join(__dirname, "pdfs");
const HEADLESS = true;
const VIEWPORT = { width: 1280, height: 800 };
const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

function safeName(s) {
  return String(s)
    .replace(/^https?:\/\//, "")
    .replace(/[^\w\-]+/g, "_")
    .slice(0, 180);
}

function pad3(n) {
  return String(n).padStart(3, "0");
}

function buildDesdeList() {
  const list = [];
  for (let d = START_FROM; d <= END_FROM; d += STEP) list.push(d);
  return list;
}

// Formato principal (el que usabas): /marca/combustible/marca_Desde_X_...
function buildUrlWithBrandPrefix(brand, fuel, desde) {
  return `https://autos.mercadolibre.com.ar/${brand}/${fuel}/${brand}_Desde_${desde}_ITEM*CONDITION_2230581_NoIndex_True`;
}

// Fallback alternativo: /marca/combustible/_Desde_X_...
function buildUrlWithoutBrandPrefix(brand, fuel, desde) {
  return `https://autos.mercadolibre.com.ar/${brand}/${fuel}/_Desde_${desde}_ITEM*CONDITION_2230581_NoIndex_True`;
}

async function acceptCookiesIfAny(page) {
  const candidates = [/aceptar cookies/i, /aceptar/i, /entendido/i, /^ok$/i];
  for (const rx of candidates) {
    try {
      const btn = page.getByRole("button", { name: rx });
      await btn.waitFor({ timeout: 2500 });
      await btn.click({ timeout: 2500 });
      await page.waitForTimeout(600);
      return;
    } catch (_) {}
  }
}

async function gotoWithFallback(page, primaryUrl, fallbackUrl) {
  try {
    await page.goto(primaryUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    return primaryUrl;
  } catch (_) {
    await page.goto(fallbackUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    return fallbackUrl;
  }
}

// ✅ Detecta la pantalla de "No encontramos resultados..."
async function hasNoResults(page) {
  // La frase de tu captura
  const noResultsTitle = page.getByText(/no encontramos resultados para tu búsqueda/i);

  // A veces MercadoLibre usa otro texto similar
  const altNoResults = page.getByText(/no hay publicaciones que coincidan|sin resultados/i);

  // Espera por si carga tarde
  try {
    await Promise.race([
      noResultsTitle.waitFor({ timeout: 2000 }),
      altNoResults.waitFor({ timeout: 2000 }),
    ]);
  } catch (_) {
    // si no aparece, ok
  }

  return (await noResultsTitle.isVisible().catch(() => false)) ||
         (await altNoResults.isVisible().catch(() => false));
}

(async () => {
  const desdeList = buildDesdeList();

  fs.mkdirSync(BASE_OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    userAgent: USER_AGENT,
  });

  let globalIndex = 0;
  const totalJobs = BRANDS.length * FUELS.length * desdeList.length;

  for (const brand of BRANDS) {
    for (const fuel of FUELS) {
      const outDir = path.join(BASE_OUT_DIR, brand, fuel);
      fs.mkdirSync(outDir, { recursive: true });

      for (let i = 0; i < desdeList.length; i++) {
        const desde = desdeList[i];
        const url1 = buildUrlWithBrandPrefix(brand, fuel, desde);
        const url2 = buildUrlWithoutBrandPrefix(brand, fuel, desde);

        globalIndex++;
        const page = await context.newPage();

        try {
          console.log(`(${globalIndex}/${totalJobs}) ${brand} | ${fuel} | Desde_${desde}`);

          const finalUrl = await gotoWithFallback(page, url1, url2);
          await acceptCookiesIfAny(page);

          // Dejá respirar a la página
          await page.waitForTimeout(1200);

          // ✅ Si aparece “No encontramos resultados…”, salteamos
          if (await hasNoResults(page)) {
            console.log(`   ⚠️ Sin resultados. Salteo: ${brand}/${fuel}/Desde_${desde}`);
            break; // pasa al siguiente "desde"
          }

          // Si querés, podés esperar a que aparezca algo del listado
          // (no es obligatorio, pero ayuda a evitar PDFs vacíos)
          // Si falla, igual intenta imprimir
          try {
            await page.waitForSelector("li.ui-search-layout__item", { timeout: 6000 });
          } catch (_) {}

          const file = path.join(
            outDir,
            `${pad3(i + 1)}_Desde_${desde}_${safeName(finalUrl)}.pdf`
          );

          await page.pdf({
            path: file,
            format: "A4",
            printBackground: true,
            margin: { top: "10mm", right: "10mm", bottom: "10mm", left: "10mm" },
            preferCSSPageSize: true,
          });

          console.log(`   ✅ Guardado: ${file}`);
        } catch (err) {
          console.log(
            `   ❌ Error en ${brand}/${fuel}/Desde_${desde}: ${err?.message || err}`
          );
        } finally {
          await page.close().catch(() => {});
        }
      }
    }
  }

  await browser.close();
  console.log("✅ Listo. PDFs en ./pdfs/<marca>/<combustible>/");
})();
