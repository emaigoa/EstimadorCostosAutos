import re
import csv
from pathlib import Path
import unicodedata

# ========= CONFIG =========
TEXT_ROOT = Path("textos")
OUT_CSV = Path("autos_dataset.csv")
USD_RATE = 1500  # ARS -> USD

# ========= REGEX =========
RE_PRICE_ANY = re.compile(r"(?P<cur>US\$|USD|\$)\s*(?P<num>[\d\.\,]+)", re.IGNORECASE)
RE_ANTICIPO = re.compile(r"^\s*anticipo\s+de\s+", re.IGNORECASE)

RE_YEAR_KM_ANY = re.compile(
    r"(?P<year>19\d{2}|20\d{2})\s*\|\s*(?P<km>[\d\.\,]+)\s*Km",
    re.IGNORECASE
)

# ========= FILTROS =========
NOISE_CONTAINS = [
    "cupones", "supermercado", "vender", "ayuda", "mis compras", "favoritos",
    "creá tu cuenta", "crea tu cuenta", "ingresá", "ingresa", "(cid:0)",
    "ordenar por", "más relevantes", "mas relevantes", "mostrar más", "mostrar mas",
    "tiendas oficiales", "ir a la tienda",
    "detalles de la publicación", "detalles de la publicacion",
    "otras personas buscaron", "búsquedas relacionadas", "busquedas relacionadas",
    "resultados", "autos, motos", "camionetas",
    "cómo cuidamos tu privacidad", "como cuidamos tu privacidad",
    "información al usuario", "informacion al usuario",
    "defensa del consumidor", "accesibilidad", "programa de afiliados",
    "libro de quejas", "centro de privacidad", "consultar más", "consultar mas",
    "anterior", "siguiente", "publicados hoy",
    # el “index” de letras que te aparece al final
    "r - s - t - u - v - w - x - y - z",
    "j - k - l - m - n - o - p - q",
]

BAD_SINGLE_LINES = {
    "vehículo validado", "vehiculo validado",
    "ad",  # MercadoLibre pone "Ad"
}

BAD_VENDOR_WORDS = {
    "grupo","autos","automotores","motors","motor","srl","sa","usados","concesionaria",
    "taraborelli","chamonix","motormax","icars","autocity","diaz","meucci","merak",
    # ojo: "rs" a veces es Audi RS (modelo real). lo saco de vendor para no romper Audi RS
}

# ========= HELPERS =========
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def norm_space(s: str) -> str:
    return " ".join(s.replace("\u00ad", "").split()).strip()

def is_noise(line: str) -> bool:
    s = norm_space(line)
    low = strip_accents(s).lower()
    if not low:
        return True
    if low in BAD_SINGLE_LINES:
        return True
    if low.startswith("---"):   # meta/settings/pages
        return True
    if "sidebar_x" in low or "split_x" in low or "crop_y" in low or "anchor_cut" in low:
        return True
    if low in {"1", "2", "3", "4"}:
        return True
    if RE_ANTICIPO.search(low):
        # "Anticipo de $..." no es basura, pero no es precio real => lo tratamos aparte
        return False
    for k in NOISE_CONTAINS:
        if k in low:
            return True
    return False

def is_price_line_anticipo(line: str) -> bool:
    """True si es un precio pero de 'Anticipo de ...' (hay que ignorarlo como precio real)."""
    low = strip_accents(norm_space(line)).lower()
    return low.startswith("anticipo de") and RE_PRICE_ANY.search(line) is not None

def parse_price(line: str):
    """Devuelve (moneda, valor_int) si es precio REAL. Si es anticipo, devuelve (None,None)."""
    if is_price_line_anticipo(line):
        return None, None

    s = norm_space(line)
    m = RE_PRICE_ANY.search(s)
    if not m:
        return None, None

    digits = re.sub(r"[^\d]", "", m.group("num") or "")
    if not digits:
        return None, None

    val = int(digits)
    cur = (m.group("cur") or "").upper()
    return ("USD", val) if cur in ("US$", "USD") else ("ARS", val)

def to_usd(moneda: str, precio: int):
    if moneda == "USD":
        return int(precio)
    if moneda == "ARS":
        return float(precio) / float(USD_RATE)
    return None

def parse_year_km(line: str):
    s = norm_space(line)
    m = RE_YEAR_KM_ANY.search(s)
    if not m:
        return None, None
    year = int(m.group("year"))
    kms = int(re.sub(r"[^\d]", "", m.group("km") or "0") or "0")
    return year, kms

def is_location_like(line: str) -> bool:
    s = norm_space(line)
    if not s:
        return False
    return " - " in s

def looks_like_vendor(line: str) -> bool:
    s = strip_accents(norm_space(line)).lower()
    if not s:
        return False
    # si tiene pinta de nombre de agencia, lo marcamos
    for w in BAD_VENDOR_WORDS:
        if w in s.split() or w in s:
            return True
    return False

def parse_extras(otros_folder: str):
    s = strip_accents((otros_folder or "").lower())
    aire = ("aire" in s) or ("con-aire-acondicionado" in s)
    cristales = ("cristales" in s) or ("con-cristales-electricos" in s) or ("vidrios" in s)
    return bool(aire), bool(cristales)

def dedupe_consecutive(lines):
    out = []
    prev = None
    for s in lines:
        s2 = norm_space(s)
        if not s2:
            continue
        if prev is not None and strip_accents(s2).lower() == strip_accents(prev).lower():
            continue
        out.append(s2)
        prev = s2
    return out

def merge_page_cuts(lines):
    """
    Une cortes entre páginas/columnas:
    - si la línea nueva empieza en minúscula y la anterior no termina en puntuación
    - o si la anterior termina con '…' o '-' o queda 'a mitad de palabra'
    """
    merged = []
    for line in lines:
        line = norm_space(line)
        if not line:
            continue
        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]

        prev_end_bad = prev.endswith(("…", "-", "·"))
        starts_lower = line and line[0].islower()

        if (not prev.endswith((".", ":", ";", "!", "?")) and starts_lower) or prev_end_bad:
            merged[-1] = prev + " " + line
        else:
            merged.append(line)

    return merged

def build_brand_regex(marca_slug: str):
    """
    marca_slug puede venir: 'alfa-romeo', 'citroen', 'd-s', etc.
    Creamos regex que matchee inicio de línea con la marca (tolerante a espacios/guiones/acentos).
    """
    brand = strip_accents(marca_slug.replace("-", " ")).strip()
    # permitimos multiples espacios
    pat = r"^\s*" + re.escape(brand).replace(r"\ ", r"\s+") + r"\b"
    return re.compile(pat, re.IGNORECASE)

def model_has_brand_prefix(model: str, marca_slug: str) -> bool:
    """Regla dura: el modelo debe arrancar con la marca (no solo contenerla)."""
    re_brand = build_brand_regex(marca_slug)
    return bool(re_brand.match(strip_accents(norm_space(model))))

BAD_MODEL_SOLO = {
    "quattro", "front", "at", "mt", "cv", "tct", "stronic", "tiptronic",
    "multitronic", "sedan", "lt", "ltz", "awd", "4x4", "cvt"
}

def model_has_enough_info(model: str, marca_slug: str) -> bool:
    """
    Evita modelos tipo: 'Audi Quattro' o 'BAIC 105cv' o 'BAIC At6'
    """
    m = strip_accents(norm_space(model)).lower()
    brand = strip_accents(marca_slug.replace("-", " ")).lower()

    if not m.startswith(brand):
        return False

    rest = m[len(brand):].strip()
    if not rest:
        return False

    rest_tokens = [t for t in re.split(r"\s+", rest) if t]
    if not rest_tokens:
        return False

    if len(rest_tokens) == 1:
        t = rest_tokens[0]
        if t in BAD_MODEL_SOLO:
            return False
        if re.fullmatch(r"\d+(?:[\.,]\d+)?cv", t):
            return False
        if re.fullmatch(r"at\d+", t):
            return False
        if re.fullmatch(r"\d+(?:[\.,]\d+)?", t):
            return False

    return True

def find_model_brand_plus_nextline(content, price_idx, marca_slug):
    """
    Busca hacia atrás desde el precio:
    - Encuentra la línea que arranca con la marca
    - Agrega 1 línea siguiente como “continuación” si sirve
    - Si no encuentra marca => "" (descarta)
    """
    re_brand_start = build_brand_regex(marca_slug)

    for k in range(price_idx - 1, max(-1, price_idx - 30), -1):
        l0 = norm_space(content[k])
        if not l0 or is_noise(l0):
            continue

        low0 = strip_accents(l0).lower()
        if low0 in {"ad", "vehiculo validado", "vehículo validado"}:
            continue
        if is_price_line_anticipo(l0):
            continue
        if parse_price(l0)[0] is not None:
            continue
        if parse_year_km(l0)[0] is not None:
            continue
        if is_location_like(l0):
            continue
        if looks_like_vendor(l0):
            continue

        # ✅ debe arrancar con la marca
        if not re_brand_start.match(strip_accents(l0)):
            continue

        # candidate next line
        l1 = ""
        if k + 1 < len(content):
            cand = norm_space(content[k + 1])
            if cand and (not is_noise(cand)):
                low1 = strip_accents(cand).lower()
                if low1 not in {"ad", "vehiculo validado", "vehículo validado"} \
                   and (not is_price_line_anticipo(cand)) \
                   and parse_price(cand)[0] is None \
                   and parse_year_km(cand)[0] is None \
                   and (not is_location_like(cand)) \
                   and (not looks_like_vendor(cand)):
                    # si la siguiente también arranca con la marca, no la sumo
                    if not re_brand_start.match(strip_accents(cand)):
                        l1 = cand

        model = l0 if not l1 else f"{l0} {l1}"

        # ✅ filtro final: marca + info real
        if not model_has_enough_info(model, marca_slug):
            return ""

        return model

    return ""

# ========= PARSER =========
def extract_records_from_txt(txt_path: Path):
    records = []

    # metadata desde ruta
    otros = txt_path.parent.name
    direccion = txt_path.parent.parent.name
    transmision = txt_path.parent.parent.parent.name
    combustible = txt_path.parent.parent.parent.parent.name
    marca = txt_path.parent.parent.parent.parent.parent.name

    aire, cristales = parse_extras(otros)

    raw_lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    # Nos quedamos SOLO con RESULTS LEFT/RIGHT (evita META/SETTINGS/PAGE)
    in_results = False
    content = []
    for raw in raw_lines:
        s = raw.strip()
        if s.startswith("--- RESULTS LEFT") or s.startswith("--- RESULTS RIGHT"):
            in_results = True
            continue
        if s.startswith("--- PAGE") or s.startswith("--- SETTINGS") or s.startswith("--- META") or s.startswith("--- /META"):
            in_results = False
            continue
        if in_results:
            s = norm_space(s)
            if not s:
                continue
            # mantenemos anticipo como línea, pero filtramos ruido
            if not is_noise(s):
                content.append(s)

    # unir cortes y duplicados
    content = merge_page_cuts(content)
    content = dedupe_consecutive(content)

    i = 0
    while i < len(content):
        line = content[i]

        moneda, precio = parse_price(line)
        if moneda and precio:
            # year|km adelante
            year = kms = None
            for j in range(i + 1, min(i + 12, len(content))):
                y, k = parse_year_km(content[j])
                if y is not None and k is not None and k > 0:
                    year, kms = y, k
                    break

            # ubicación adelante (después del year|km, ideal)
            ubic = ""
            if year is not None:
                for j in range(i + 1, min(i + 20, len(content))):
                    if is_location_like(content[j]):
                        ubic = content[j]
                        break

            if year is None or kms is None or not ubic:
                i += 1
                continue

            # ✅ modelo: SOLO si arranca con la marca del folder
            model = find_model_brand_plus_nextline(content, i, marca)
            if not model:
                i += 1
                continue

            # ✅ validación extra: si por alguna razón no arranca con marca, descartamos (cero otras marcas)
            if not model_has_brand_prefix(model, marca):
                i += 1
                continue

            precio_usd = to_usd(moneda, precio)

            records.append({
                "marca": marca,
                "combustible": combustible,
                "transmision": transmision,
                "direccion": direccion,
                "aire": aire,
                "cristales": cristales,
                "modelo": model,
                "precio_usd": round(precio_usd, 2) if precio_usd is not None else "",
                "moneda_origen": moneda,
                "precio_origen": int(precio),
                "anio": int(year),
                "kms": int(kms),
                "ubicacion": ubic,
                "fuente_archivo": str(txt_path).replace("\\", "/"),
            })

        i += 1

    return records

# ========= MAIN =========
def main():
    all_rows = []
    txt_files = sorted(TEXT_ROOT.glob("*/*/*/*/*/*.txt"))
    print(f"📂 Archivos encontrados: {len(txt_files)}")

    for txt in txt_files:
        rows = extract_records_from_txt(txt)
        all_rows.extend(rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "marca", "combustible", "transmision", "direccion",
            "aire", "cristales",
            "modelo", "precio_usd", "moneda_origen", "precio_origen",
            "anio", "kms", "ubicacion", "fuente_archivo"
        ])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Dataset generado: {len(all_rows)} filas -> {OUT_CSV}")

if __name__ == "__main__":
    main()
