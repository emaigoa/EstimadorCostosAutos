import csv
import re
import unicodedata
from pathlib import Path

IN_CSV = Path("autos_dataset.csv")
OUT_CSV = Path("autos_dataset_limpio.csv")

# ✅ listado de marcas tal cual lo pasaste
BRANDS_RAW = [
    "Alfa Romeo","Audi","BAIC","BMW","BYD","Changan","Chery","Chevrolet","Chrysler","Citroën",
    "D.S.","Daihatsu","Dodge","Ferrari","Fiat","Ford","GMC","GWM","Honda","Hyundai","Isuzu","Iveco",
    "JAC","Jaguar","Jeep","Kia","Lancia","Land Rover","Lexus","Mazda","Mercedes-Benz","MG","Mini",
    "Mitsubishi","Nissan","Opel","Peugeot","Porsche","RAM","Range Rover","Renault","Seat","SsangYong",
    "Subaru","Suzuki","SWM","Toyota","Volkswagen","Volvo",
]

def strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )

def norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("–", "-").replace("—", "-")
    s = strip_accents(s)
    s = " ".join(s.split()).strip()
    return s

def norm_key(s: str) -> str:
    return norm(s).lower()

def brand_simplify(s: str) -> str:
    """
    Para comparar marcas ignorando guiones/espacios/puntos:
    "Alfa Romeo" == "alfa-romeo"
    """
    s = norm_key(s)
    return re.sub(r"[^a-z0-9]+", "", s)

def safe_int(x, default=None):
    if x is None:
        return default
    s = str(x).strip()
    if not s:
        return default
    s = s.replace(".", "").replace(",", "")
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return default
    try:
        return int(digits)
    except:
        return default

def parse_bool(x) -> bool:
    s = norm_key(str(x))
    if s in {"true", "verdadero", "1", "si", "sí", "yes", "y"}:
        return True
    if s in {"false", "falso", "0", "no", "n"}:
        return False
    return False

def extras_score(aire: bool, vidrio: bool) -> int:
    return (1 if aire else 0) + (1 if vidrio else 0)

# ======================================================
# ✅ FIX de valores con letras rotas por "-"
# ======================================================

COMBUSTIBLE_FIX = {
    "di-sel": "diesel",
    "el-ctrico": "eléctrico",
    "h-brido": "híbrido",
    "h-brido-nafta": "híbrido-nafta",
    # mild-hybrid queda igual
}

TRANSMISION_FIX = {
    "autom-tica": "automática",
    "autom-tica-secuencial": "automática secuencial",
    "semiautom-tica": "semiautomática",
}

DIRECCION_FIX = {
    "hidr-ulica": "hidráulica",
    "el-ctrica": "eléctrica",
    "mec-nica": "mecánica",
}

def normalize_combustible(raw: str) -> str:
    c = norm_key(raw)
    if not c:
        return ""
    # regla pedida: todo lo que contenga gnc -> nafta-gnc
    if "gnc" in c:
        return "nafta-gnc"
    return COMBUSTIBLE_FIX.get(c, c)

def normalize_transmision(raw: str) -> str:
    t = norm_key(raw)
    if not t:
        return ""
    t = TRANSMISION_FIX.get(t, t)
    # fallback por siglas
    if t == "mt":
        return "manual"
    if t == "at":
        return "automática"
    return t

def normalize_direccion(raw: str) -> str:
    d = norm_key(raw)
    if not d:
        return ""
    return DIRECCION_FIX.get(d, d)

# ======================================================
# ✅ MATCH de marca al inicio (acepta espacio o guion)
# ======================================================

def compile_brand_patterns(brands_raw):
    patterns = []
    for b in brands_raw:
        b_disp = norm(b)
        if not b_disp:
            continue
        b_key = norm_key(b_disp)
        tokens = re.split(r"[\s\-\.]+", b_key)
        tokens = [t for t in tokens if t]
        if not tokens:
            continue
        # permite separadores: espacios o guiones entre tokens
        pat = r"^" + r"[\s\-]+".join(map(re.escape, tokens)) + r"(?:[\s\-]+|$)"
        patterns.append((b_disp, re.compile(pat, flags=re.IGNORECASE)))

    # más largas primero (ej: "Alfa Romeo" antes que "Alfa")
    patterns.sort(key=lambda x: len(x[0]), reverse=True)
    return patterns

BRAND_PATTERNS = compile_brand_patterns(BRANDS_RAW)

def detect_brand_prefix(modelo_full: str):
    full = norm(modelo_full)
    if not full:
        return "", ""
    for b_display, pat in BRAND_PATTERNS:
        m = pat.match(full)
        if m:
            rest = full[m.end():].strip()
            return b_display, rest
    return "", full

def split_model_version_from_full(modelo_full: str):
    brand_text, rest = detect_brand_prefix(modelo_full)
    if not brand_text:
        return "", "", ""

    parts = rest.split()
    if len(parts) < 1:
        return brand_text, "", ""

    modelo = parts[0]
    version = " ".join(parts[1:]).strip()
    return brand_text, modelo, version

# ======================================================
# ✅ NUEVO: filtro de versiones inválidas
# ======================================================

INVALID_VERSION_VALUES = {"", "nan", "none", "null", "na", "n/a", "-"}

def is_invalid_version(version: str) -> bool:
    v = norm_key(version)
    return v in INVALID_VERSION_VALUES

def main():
    best_by_key = {}

    with IN_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for r in reader:
            marca_csv = norm_key(r.get("marca", ""))  # ej: alfa-romeo
            modelo_full = norm(r.get("modelo", ""))   # ej: "Alfa Romeo 156 2.4 ..."

            combustible = normalize_combustible(r.get("combustible", ""))
            transmision = normalize_transmision(r.get("transmision", ""))
            direccion = normalize_direccion(r.get("direccion", ""))

            aire = parse_bool(r.get("aire", False))
            vidrio = parse_bool(r.get("cristales", r.get("vidrio", False)))

            anio = safe_int(r.get("anio", ""))
            kms = safe_int(r.get("kms", ""))
            precio_usd = safe_int(r.get("precio_usd", ""))

            # mínimos
            if not marca_csv or not combustible or not modelo_full:
                continue
            if anio is None or kms is None or precio_usd is None:
                continue

            # split
            brand_text, modelo, version = split_model_version_from_full(modelo_full)
            if not brand_text or not modelo:
                continue

            # ✅ ELIMINAR si version es "nan"/vacía/etc
            if is_invalid_version(version):
                continue

            # ✅ comparación flexible: "Alfa Romeo" == "alfa-romeo"
            if brand_simplify(brand_text) != brand_simplify(marca_csv):
                continue

            row_out = {
                "marca": marca_csv,
                "modelo": norm(modelo),
                "version": norm(version),
                "anio": anio,
                "kms": kms,
                "precio_usd": precio_usd,
                "combustible": combustible,
                "transmision": transmision,
                "direccion": direccion,
                "aire": aire,
                "vidrio": vidrio,
            }

            key = (
                marca_csv,
                norm_key(modelo),
                norm_key(version),
                anio,
                kms,
                precio_usd,
                combustible,
                transmision,
                direccion,
            )

            score = extras_score(aire, vidrio)

            if key not in best_by_key:
                best_by_key[key] = (score, row_out)
            else:
                prev_score, _ = best_by_key[key]
                if score > prev_score:
                    best_by_key[key] = (score, row_out)

    rows = [v[1] for v in best_by_key.values()]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as out_f:
        fieldnames = [
            "marca", "modelo", "version",
            "anio", "kms", "precio_usd",
            "combustible", "transmision", "direccion",
            "aire", "vidrio"
        ]
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Limpio + dedupe + fixes '-' + gnc->nafta-gnc + sin version NaN: {len(rows)} filas -> {OUT_CSV.resolve()}")

if __name__ == "__main__":
    main()
