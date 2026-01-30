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

# ---------- MARCA (1 o 2 palabras) ----------
def compile_brand_matcher(brands_raw):
    """
    Arma una lista de marcas normalizadas y ordenadas por longitud descendente
    para matchear primero Alfa Romeo antes que Alfa, etc.
    """
    brands_norm = []
    for b in brands_raw:
        b_n = norm(b)
        if not b_n:
            continue
        brands_norm.append(b_n)

    # orden por cantidad de caracteres (desc) -> matchea la más larga primero
    brands_norm.sort(key=lambda s: len(s), reverse=True)

    # guardamos también la key (lower) para comparar fácil
    brands_norm_key = [(b, norm_key(b)) for b in brands_norm]
    return brands_norm_key

BRANDS_MATCH = compile_brand_matcher(BRANDS_RAW)

def detect_brand_prefix(modelo_full: str):
    """
    Devuelve (brand_in_text, rest_text) si matchea alguna marca al inicio.
    Si no matchea, devuelve ("", modelo_full_norm).
    """
    full = norm(modelo_full)
    full_l = norm_key(full)

    for b_display, b_key in BRANDS_MATCH:
        # chequeo de prefijo con frontera de palabra
        # ej: "Alfa Romeo " o "Mercedes-Benz "
        if full_l.startswith(b_key + " "):
            rest = full[len(b_display):].strip()
            return b_display, rest
        if full_l == b_key:
            return b_display, ""

    return "", full

def split_model_version_from_full(modelo_full: str):
    """
    Usa marca detectada (1-2 palabras o más, ej mercedes-benz) y parte:
      marca_texto | modelo | version
    """
    brand_text, rest = detect_brand_prefix(modelo_full)
    if not brand_text:
        return "", "", ""  # no se pudo detectar marca en el texto

    parts = rest.split()
    if len(parts) < 1:
        return brand_text, "", ""

    modelo = parts[0]
    version = " ".join(parts[1:]).strip()
    return brand_text, modelo, version

def main():
    best_by_key = {}

    with IN_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for r in reader:
            # marca "real" (carpeta / csv)
            marca_csv = norm_key(r.get("marca", ""))
            combustible = norm_key(r.get("combustible", ""))

            modelo_full = norm(r.get("modelo", ""))

            transmision = norm_key(r.get("transmision", ""))
            direccion = norm_key(r.get("direccion", ""))

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

            # ✅ split con marca de 1 o 2 palabras (según listado)
            brand_text, modelo, version = split_model_version_from_full(modelo_full)
            if not brand_text or not modelo:
                continue

            # ✅ filtro: la marca detectada en el texto debe coincidir con la marca del csv
            # (esto elimina "baic ... chevrolet cruze ...")
            if norm_key(brand_text) != marca_csv:
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

            # ✅ mismo auto (incluye combustible + trans + direccion)
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

    print(f"✅ Limpio + dedupe + marca 2 palabras OK: {len(rows)} filas -> {OUT_CSV.resolve()}")

if __name__ == "__main__":
    main()
