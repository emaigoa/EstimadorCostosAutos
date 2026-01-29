const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// =====================
// MARCAS 
// =====================
const BRANDS_RAW = [
  "Agrale",
  "Alfa Romeo",
  "Audi",
  "BAIC",
  "BMW",
  "BYD",
  "Changan",
  "Chery",
  "Chevrolet",
  "Chrysler",
  "Citroën",
  "Coradir",
  "D.S.",
  "Daewoo",
  "Daihatsu",
  "DFSK",
  "Dodge",
  "Ferrari",
  "Fiat",
  "Ford",
  "Foton",
  "GMC",
  "GWM",
  "Honda",
  "Hyundai",
  "IKA",
  "IME",
  "Isuzu",
  "Iveco",
  "JAC",
  "Jaguar",
  "Jeep",
  "Jetour",
  "Kia",
  "Lancia",
  "Land Rover",
  "Lexus",
  "Lifan",
  "Lotus",
  "Mazda",
  "Mercedes-Benz",
  "MG",
  "Mini",
  "Mitsubishi",
  "Nissan",
  "Opel",
  "Peugeot",
  "Polaris",
  "Porsche",
  "RAM",
  "Range Rover",
  "Renault",
  "Seat",
  "Sero Electric",
  "Shineray",
  "Smart",
  "SsangYong",
  "Subaru",
  "Suzuki",
  "SWM",
  "Toyota",
  "UAZ",
  "Volkswagen",
  "Volvo",
];

// =====================
// COMBUSTIBLES 
// =====================
const FUELS = [
  "nafta",
  "diesel",
  "nafta-gnc",
  "gnc",
  "hibrido",
  "hibrido-diesel",
  "hibrido-nafta",
  "electrico",
];

// =====================
// TRANSMISIONES 
// =====================
const TRANSMISSIONS = ["manual", "automatica", "automatica-secuencial"];

// =====================
// DIRECCIÓN
// =====================

const DIRECCION = ["electrica", "asistida", "mecanica", "hidraulica"]

// =====================
// OTROS
// =====================

const OTROS = ["con-aire-acondicionado", "con-cristales-electricos"]

// =====================
// SETTINGS
// =====================
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

function slugifyBrand(name) {
  // Normaliza acentos (Citroën -> Citroen)
  let s = String(name).trim();

  s = s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, ""); // quita diacríticos

  // Casos con puntos / símbolos
  s = s.replace(/\./g, ""); // D.S. -> DS
  s = s.replace(/&/g, "and");

  // Espacios a guiones, doble guion limpieza
  s = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/(^-|-$)/g, "");

  return s;
}

// Si alguna marca no coincide con el slug real de ML, la corregís acá
const BRAND_SLUG_OVERRIDES = {
  "d-s": "ds", // a veces aparece como ds
  "mercedes-benz": "mercedes-benz",
  "alfa-romeo": "alfa-romeo",
  "land-rover": "land-rover",
  "range-rover": "range-rover",
  "sero-electric": "sero-electric",
  "ssangyong": "ssangyong",
};

function brandToSlug(brandRaw) {
  const s = slugifyBrand(brandRaw);
  return BRAND_SLUG_OVERRIDES[s] || s;
}

// URL final pedida
function buildUrl(brandSlug, fuel, transmission, direccion, otros) {
  return `https://autos.mercadolibre.com.ar/${brandSlug}/${fuel}/${transmission}/${direccion}/${otros}/_ITEM*CONDITION_2230581`;
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

// Detecta “No encontramos resultados…”
async function hasNoResults(page) {
  const noResultsTitle = page.getByText(/no encontramos resultados para tu búsqueda/i);
  const altNoResults = page.getByText(/no hay publicaciones que coincidan|sin resultados/i);

  try {
    await Promise.race([
      noResultsTitle.waitFor({ timeout: 2000 }),
      altNoResults.waitFor({ timeout: 2000 }),
    ]);
  } catch (_) {}

  return (
    (await noResultsTitle.isVisible().catch(() => false)) ||
    (await altNoResults.isVisible().catch(() => false))
  );
}

(async () => {
  fs.mkdirSync(BASE_OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    userAgent: USER_AGENT,
  });

  const totalJobs = BRANDS_RAW.length * FUELS.length * TRANSMISSIONS.length * DIRECCION.length * OTROS.length;
  let jobIndex = 0;

  for (const brandRaw of BRANDS_RAW) {
    const brandSlug = brandToSlug(brandRaw);

    for (const fuel of FUELS) {
      for (const transmission of TRANSMISSIONS) {
        for (const direccion of DIRECCION){
          for (const otros of OTROS){
            jobIndex++;

            const outDir = path.join(BASE_OUT_DIR, brandSlug, fuel, transmission, direccion, otros);
            fs.mkdirSync(outDir, { recursive: true });

            const url = buildUrl(brandSlug, fuel, transmission, direccion, otros);
            const page = await context.newPage();

            try {
              console.log(`(${jobIndex}/${totalJobs}) ${brandSlug} | ${fuel} | ${transmission} | ${direccion} | ${otros}`);
              console.log(`   → ${url}`);

              await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
              await acceptCookiesIfAny(page);

              // dejar que cargue algo
              await page.waitForTimeout(1200);

              // si no hay resultados, salteo
              if (await hasNoResults(page)) {
                console.log(`   ⚠️ Sin resultados. Salteo: ${brandSlug}/${fuel}/${transmission}/${direccion}/${otros}`);
                continue;
              }

              // intenta esperar a que aparezca el listado (si falla no corta)
              try {
                await page.waitForSelector("li.ui-search-layout__item", { timeout: 6000 });
              } catch (_) {}

              const file = path.join(
                outDir,
                `${safeName(`${brandSlug}_${fuel}_${transmission}_${direccion}_${otros}`)}.pdf`
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
                `   ❌ Error en ${brandSlug}/${fuel}/${transmission}/${direccion}/${otros}: ${err?.message || err}`
              );
            } finally {
              await page.close().catch(() => {});
            }
          }
        }
      }
    }
  }

  await browser.close();
  console.log("✅ Listo. PDFs en ./pdfs/<marca>/<combustible>/<transmision>/<direccion>/<otros>");
})();
