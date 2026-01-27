import re
import csv
from pathlib import Path

# ========= CONFIG =========
TEXT_ROOT = Path("textos")          # textos/<marca>/<combustible>/*.txt
OUT_CSV = Path("autos_dataset.csv")
USD_RATE = 1500  # ARS -> USD

MARCAS = ["volkswagen", "fiat", "renault", "ford", "chevrolet", "peugeot", "toyota", "citroen", "nissan", "honda"]
COMBUSTIBLES = ["nafta", "diesel", "nafta-gnc"]  # ajustá a tus carpetas reales

# ========= REGEX =========
RE_PRICE_ANY = re.compile(r"(?P<cur>US\$|USD|\$)\s*(?P<num>[\d\.\,]+)", re.IGNORECASE)
RE_YEAR_KM_ANY = re.compile(r"(?P<year>19\d{2}|20\d{2})\s*\|\s*(?P<km>[\d\.\,]+)\s*Km", re.IGNORECASE)

# ========= FILTROS DE “BASURA” =========
NOISE_CONTAINS = [
    "cupones", "supermercado", "vender", "ayuda", "mis compras", "favoritos",
    "creá tu cuenta", "ingresá", "categorías", "ofertas", "guardar esta búsqueda",
    "ordenar por", "más relevantes", "mostrar más", "tiendas oficiales", "ubicación",
    "modelo", "versiones", "kilómetros", "pago", "transmisión", "dirección",
    "detalles de la publicación", "otras personas buscaron", "enviar a",
    "cómo cuidamos tu privacidad", "información al usuario", "defensa del consumidor",
    "accesibilidad", "afiliados", "centro de privacidad", "consultar más",
    "anterior", "siguiente", "publicados hoy",
    "búsquedas relacionadas", "resultados", "autos, motos", "camionetas",
]

BAD_SINGLE_LINES = {
    "vehículo validado", "vehiculo validado",
}

BAD_VENDOR_WORDS = {
    "grupo","autos","automotores","motors","motor","srl","sa","usados","concesionaria",
    "taraborelli","chamonix","motormax","icars","autocity","diaz","meucci","merak","rs"
}

# ========= HELPERS =========
def norm_space(s: str) -> str:
    return " ".join(s.replace("\u00ad", "").split()).strip()

def is_noise(line: str) -> bool:
    s = norm_space(line).lower()
    if not s:
        return True
    if s in BAD_SINGLE_LINES:
        return True
    if s.startswith("--- page") or s.startswith("--- settings") or s.startswith("--- results"):
        return True
    if "sidebar_x" in s or "split_x" in s:
        return True
    if s in {"1", "2", "3", "4"}:
        return True
    if "anticipo de" in s:
        return True
    for k in NOISE_CONTAINS:
        if k in s:
            return True
    if all(ch in "" for ch in s):  # iconitos
        return True
    return False

def parse_price(line: str):
    s = norm_space(line)
    m = RE_PRICE_ANY.search(s)
    if not m:
        return None, None

    cur = m.group("cur").upper()
    num = m.group("num")

    digits = re.sub(r"[^\d]", "", num)
    if not digits:
        return None, None

    val = int(digits)
    if cur in ("US$", "USD"):
        return "USD", val
    return "ARS", val

def to_usd(moneda: str, precio_origen: int):
    if moneda == "USD":
        return int(precio_origen)
    if moneda == "ARS":
        return int(round(precio_origen / USD_RATE, 2))
    return None

def parse_year_km(line: str):
    s = norm_space(line)
    m = RE_YEAR_KM_ANY.search(s)
    if not m:
        return None, None
    year = int(m.group("year"))
    km_digits = re.sub(r"[^\d]", "", m.group("km"))
    kms = int(km_digits) if km_digits else None
    return year, kms

def looks_like_vendor(line: str, re_start_brand) -> bool:
    s = norm_space(line).lower()
    if not s:
        return True
    if not re_start_brand.match(line):
        for w in BAD_VENDOR_WORDS:
            if w in s.split() or w in s:
                return True
    return False

def find_model_and_version(back_lines, re_start_brand):
    idx_model = None
    for i in range(len(back_lines) - 1, -1, -1):
        s = norm_space(back_lines[i])
        if not s or is_noise(s):
            continue
        if RE_PRICE_ANY.search(s) or RE_YEAR_KM_ANY.search(s):
            continue
        if re_start_brand.match(s):
            idx_model = i
            break

    if idx_model is None:
        return "", ""

    model = norm_space(back_lines[idx_model])

    version = ""
    if idx_model + 1 < len(back_lines):
        cand = norm_space(back_lines[idx_model + 1])
        if cand and (not is_noise(cand)) and (not RE_PRICE_ANY.search(cand)) and (not RE_YEAR_KM_ANY.search(cand)):
            if not looks_like_vendor(cand, re_start_brand) and not re_start_brand.match(cand):
                version = cand

    return model, version

def is_location_like(line: str) -> bool:
    s = norm_space(line)
    if not s or is_noise(s):
        return False
    return " - " in s

def extract_records_from_txt(txt_path: Path, marca: str, combustible: str):
    records = []

    # regex dinámica para la marca
    brand_title = marca.strip().capitalize()
    re_start_brand = re.compile(rf"^\s*{re.escape(brand_title)}\b", re.IGNORECASE)

    lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    # solo results left/right
    in_results = False
    content = []
    for raw in lines:
        s = raw.strip()
        if s.startswith("--- RESULTS LEFT") or s.startswith("--- RESULTS RIGHT"):
            in_results = True
            continue
        if s.startswith("--- PAGE") or s.startswith("--- SETTINGS"):
            in_results = False
            continue
        if in_results:
            content.append(s)

    back_buf = []
    i = 0
    while i < len(content):
        line = norm_space(content[i])

        if not line or is_noise(line):
            i += 1
            continue

        back_buf.append(line)
        if len(back_buf) > 25:
            back_buf.pop(0)

        moneda, precio_origen = parse_price(line)
        if moneda and precio_origen:
            year = kms = None
            ubic = ""

            # buscar year|km adelante
            j = i + 1
            for _ in range(10):
                if j >= len(content):
                    break
                cand = norm_space(content[j])
                if not cand or is_noise(cand):
                    j += 1
                    continue
                y, k = parse_year_km(cand)
                if y and k is not None:
                    year, kms = y, k
                    j += 1
                    break
                j += 1

            # buscar ubicación
            if year is not None:
                kidx = j
                for _ in range(12):
                    if kidx >= len(content):
                        break
                    cand = norm_space(content[kidx])
                    if not cand or is_noise(cand):
                        kidx += 1
                        continue
                    if is_location_like(cand):
                        ubic = cand
                        break
                    kidx += 1

            if year is None or kms is None or not ubic:
                i += 1
                continue

            model, version = find_model_and_version(back_buf, re_start_brand)
            if not model or is_noise(model) or (brand_title.lower() not in model.lower()):
                i += 1
                continue

            full_model = model if not version else f"{model} {version}"
            precio_usd = to_usd(moneda, precio_origen)

            records.append({
                "marca": marca,
                "combustible": combustible,
                "modelo": full_model,
                "precio_usd": int(precio_usd) if precio_usd is not None else "",
                "moneda_origen": moneda,
                "precio_origen": int(precio_origen),
                "anio": int(year),
                "kms": int(kms),
                "ubicacion": ubic,
                "fuente_archivo": str(txt_path).replace("\\", "/"),
            })

        i += 1

    return records

def main():
    all_rows = []

    for marca in MARCAS:
        for combustible in COMBUSTIBLES:
            folder = TEXT_ROOT / marca / combustible
            if not folder.exists():
                print(f"⚠️ No existe carpeta: {folder}")
                continue

            txt_files = sorted(folder.glob("*.txt"))
            if not txt_files:
                print(f"⚠️ Sin .txt en: {folder}")
                continue

            print(f"\n=== Parseando {marca}/{combustible}: {len(txt_files)} txt ===")
            for txt_path in txt_files:
                rows = extract_records_from_txt(txt_path, marca, combustible)
                all_rows.extend(rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "marca", "combustible", "modelo", "precio_usd", "moneda_origen", "precio_origen",
            "anio", "kms", "ubicacion", "fuente_archivo"
        ])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Listo: {len(all_rows)} filas -> {OUT_CSV}")

if __name__ == "__main__":
    main()
