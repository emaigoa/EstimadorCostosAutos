const fs = require("fs");
const path = require("path");

const INPUT = path.join(__dirname, "catalog.json");
const OUT_DIR = path.join(__dirname, "data");
const BRANDS_DIR = path.join(OUT_DIR, "brands");

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function safeName(name) {
  return String(name)
    .trim()
    .replace(/[\/\\:*?"<>|]/g, "_");
}

function main() {
  if (!fs.existsSync(INPUT)) {
    console.error("No encuentro catalog.json en:", INPUT);
    process.exit(1);
  }

  const raw = fs.readFileSync(INPUT, "utf-8");
  const catalog = JSON.parse(raw);

  ensureDir(OUT_DIR);
  ensureDir(BRANDS_DIR);

  // index liviano: marca -> [modelos]
  const index = {};

  for (const brand of Object.keys(catalog)) {
    const modelsObj = catalog[brand] || {};
    const models = Object.keys(modelsObj).sort();
    index[brand] = models;

    const brandFile = path.join(BRANDS_DIR, `${safeName(brand)}.json`);
    fs.writeFileSync(brandFile, JSON.stringify(modelsObj, null, 0), "utf-8");
  }

  const indexFile = path.join(OUT_DIR, "index.json");
  fs.writeFileSync(indexFile, JSON.stringify(index, null, 0), "utf-8");

  console.log("✅ Listo:");
  console.log(" -", indexFile);
  console.log(" -", BRANDS_DIR);
}

main();
