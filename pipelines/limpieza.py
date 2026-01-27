import csv
import re
import unicodedata
from pathlib import Path

IN_CSV = Path("autos_dataset.csv")
OUT_CSV = Path("autos_dataset_limpio.csv")

USD_RATE = 1500  # no lo usás acá, pero lo dejo por si lo necesitás luego

# ========= MARCAS SOPORTADAS =========
BRANDS = ["volkswagen", "fiat", "renault", "ford", "chevrolet", "peugeot", "toyota", "citroen", "nissan", "honda"]

# ========= MODELOS CONOCIDOS POR MARCA =========
# (Renault completo, el resto base; sumá los que quieras)
BRAND_MODELS = {
    "renault": [
        "Sandero", "Logan", "Kangoo", "Duster", "Clio", "Fluence", "Megane",
        "Scenic", "Symbol", "Twingo", "Kwid", "Captur", "Koleos", "Alaskan",
        "Oroch", "Master", "Trafic", "Express", "Torino", "Laguna", "Latitude",
        "Modus", "R19", "R18", "R12", "R11", "R9",
        "12", "11", "9",
    ],
    "volkswagen": ["Gol", "Polo", "Golf", "Vento", "Bora", "Passat", "Fox", "Suran", "Up", "Tiguan", "Amarok", "Saveiro", "Virtus", "Taos", "T-Cross", "Voyage"],
    "fiat": ["Uno", "Palio", "Siena", "Cronos", "Argo", "Punto", "Idea", "Fiorino", "Strada", "Toro", "Ducato", "Mobi"],
    "ford": ["Ka", "Fiesta", "Focus", "Mondeo", "EcoSport", "Kuga", "Ranger", "Territory", "Bronco"],
    "chevrolet": ["Corsa", "Classic", "Onix", "Prisma", "Cruze", "S10", "Tracker", "Spin", "Agile"],
    "peugeot": ["206", "207", "208", "2008", "307", "308", "3008", "5008", "Partner", "Boxer"],
    "toyota": ["Etios", "Yaris", "Corolla", "Corolla Cross", "Hilux", "SW4", "RAV4", "Prius"],
    "citroen": ["C3", "C4", "C4 Cactus", "C-Elysee", "Berlingo", "Jumper", "DS3", "DS4"],
    "nissan": ["March", "Versa", "Sentra", "Kicks", "X-Trail", "Frontier", "Tiida"],
    "honda": ["Fit", "City", "Civic", "HR-V", "CR-V"],
}

# ========= TOKENS =========
BODY_TOKENS = {
    "Stepway", "Sedan", "Sedán", "Hatch", "Hatchback", "Furgon", "Furgón",
    "Minibus", "Pick-Up", "Pickup", "PickUp", "SUV", "Crossover",
}
TRANS_TOKENS = {"AT", "MT", "CVT", "AUT", "AUTOMATICA", "AUTOMÁTICA", "MANUAL"}

# ========= REGEX =========
RE_ENGINE = re.compile(r"\b(?P<motor>\d[.,]\d)\b")
RE_VALVES = re.compile(r"\b(?P<v>(?:8|16)\s*v)\b", re.IGNORECASE)
RE_VALVES_COMPACT = re.compile(r"\b(?P<v>(?:8v|16v))\b", re.IGNORECASE)

RE_CV = re.compile(r"\b(?P<cv>\d{2,3})\s*cv\b", re.IGNORECASE)
RE_CV_ALT = re.compile(r"\bcv\s*(?P<cv>\d{2,3})\b", re.IGNORECASE)
RE_HP = re.compile(r"\b(?P<hp>\d{2,3})\s*hp\b", re.IGNORECASE)

RE_TECH = re.compile(r"\b(dci|tce|sce|mpi|fsi|tsi|turbo)\b", re.IGNORECASE)

# ========= NORMALIZACIÓN =========
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

def tokenize(s: str):
    s = s.replace("-", " ")
    return [t for t in s.split() if t]

def remove_brand_prefix(marca: str, s: str) -> str:
    s = norm(s)
    m = (marca or "").strip().lower()
    if not m:
        return s

    # soporta "Renault", "RENAULT", etc
    if s.lower().startswith(m + " "):
        return s.split(" ", 1)[1].strip()
    return s

# ========= PARSERS =========
def find_known_model(tokens, known_models):
    if not tokens:
        return "", -1

    km = {model_key(m): m for m in known_models}

    # 1) match directo por token (normalizado)
    for i, t in enumerate(tokens):
        k = model_key(t)
        if k in km:
            return km[k], i

    # 2) match por 2 tokens juntos (ej: "T" + "cross" -> "tcross")
    for i in range(len(tokens) - 1):
        k2 = model_key(tokens[i] + tokens[i+1])
        if k2 in km:
            return km[k2], i

    # 3) match por 3 tokens juntos (por si aparece raro)
    for i in range(len(tokens) - 2):
        k3 = model_key(tokens[i] + tokens[i+1] + tokens[i+2])
        if k3 in km:
            return km[k3], i

    # Caso especial "R 19" para Renault (lo conservamos)
    tlow = [norm_key(t) for t in tokens]
    for i in range(len(tlow) - 1):
        if tlow[i] == "r" and tlow[i+1].isdigit():
            candidate = f"R{tlow[i+1]}"
            kc = model_key(candidate)
            if kc in km:
                return km[kc], i

    return "", -1


def model_key(s: str) -> str:
    # deja solo letras/números: "T-Cross" -> "tcross", "C ELYSEE" -> "celysee"
    return re.sub(r"[^a-z0-9]", "", norm_key(s))


def parse_engine_and_valves(text: str):
    t = norm(text)
    motor = ""
    valvulas = ""
    tech = ""

    m = RE_ENGINE.search(t)
    if m:
        motor = m.group("motor").replace(",", ".")

    mv = RE_VALVES.search(t)
    if mv:
        valvulas = mv.group("v").replace(" ", "").lower()

    if not valvulas:
        mv2 = RE_VALVES_COMPACT.search(t)
        if mv2:
            valvulas = mv2.group("v").lower()

    mt = RE_TECH.search(t)
    if mt:
        tech = mt.group(1).lower()

    motor_full = ""
    if motor:
        motor_full = motor
        if valvulas:
            motor_full += f" {valvulas}"
        if tech:
            motor_full += f" {tech}"

    return motor, valvulas, motor_full

def parse_cv(text: str):
    t = norm(text)

    m = RE_CV.search(t)
    if m:
        return int(m.group("cv"))

    m = RE_CV_ALT.search(t)
    if m:
        return int(m.group("cv"))

    m = RE_HP.search(t)
    if m:
        return int(m.group("hp"))

    return ""

def parse_transmission(tokens):
    for t in tokens:
        up = strip_accents(t).upper()
        if up in TRANS_TOKENS:
            if up in {"AUTOMATICA", "AUTOMÁTICA", "AUT"}:
                return "AT"
            if up == "MANUAL":
                return "MT"
            return up
    return ""

def parse_tipo(tokens, idx_model):
    tipo = ""
    if idx_model >= 0:
        for j in range(idx_model + 1, min(idx_model + 6, len(tokens))):
            if strip_accents(tokens[j]) in BODY_TOKENS:
                tipo = strip_accents(tokens[j])
                break
    if not tipo:
        for t in tokens:
            if strip_accents(t) in BODY_TOKENS:
                tipo = strip_accents(t)
                break

    tl = tipo.lower()
    if tl in {"sedan", "sedan"}:
        return "Sedan"
    if tl in {"hatch", "hatchback"}:
        return "Hatch"
    if tl in {"pick-up", "pickup", "pickup"}:
        return "Pickup"
    return tipo

def safe_int(s, default=""):
    if s is None:
        return default
    s = str(s).strip()
    if s == "":
        return default
    s = s.replace(".", "").replace(",", "")
    digits = re.sub(r"[^\d]", "", s)
    if digits == "":
        return default
    try:
        return int(digits)
    except:
        return default

def parse_model_fields(marca: str, model_str: str):
    """
    Entrada: "Renault Sandero Stepway 1.6 16v Privilege Nav 105cv"
    Salida:
      marca=<marca row>
      modelo_base (según known models de esa marca)
      tipo
      motor_full
      cv
      transmision
      version_trim
      modelo_sin_marca
    """
    marca_n = (marca or "").strip().lower()
    raw = norm(model_str)

    no_brand = remove_brand_prefix(marca_n, raw)
    tokens = tokenize(no_brand)

    known_models = BRAND_MODELS.get(marca_n, [])
    motor, valvulas, motor_full = parse_engine_and_valves(raw)
    cv = parse_cv(raw)
    transmision = parse_transmission(tokens)

    modelo_base, idx = find_known_model(tokens, known_models)
    if not modelo_base:
        modelo_base = tokens[0] if tokens else ""
        idx = 0 if tokens else -1

    tipo = parse_tipo(tokens, idx)

    drop = set()
    if modelo_base:
        drop.add(norm_key(modelo_base))
    if tipo:
        drop.add(norm_key(tipo))
    if motor:
        drop.add(norm_key(motor))
    if valvulas:
        drop.add(norm_key(valvulas))
    if transmision:
        drop.add(norm_key(transmision))

    version_parts = []
    for t in tokens:
        tl = norm_key(t)

        if RE_CV.search(t) or RE_CV_ALT.search(t) or RE_HP.search(t):
            continue

        if marca_n and tl == marca_n:
            continue

        if tl in drop:
            continue

        if motor and tl in {motor.lower(), motor.replace(".", ",").lower()}:
            continue

        version_parts.append(t)

    version_trim = norm(" ".join(version_parts))

    return {
        "marca": marca_n.capitalize() if marca_n else "",
        "modelo_base": modelo_base,
        "tipo": tipo,
        "motor_full": motor_full,
        "cv": cv,
        "transmision": transmision,
        "version_trim": version_trim,
        "modelo_sin_marca": no_brand,
    }

def main():
    with IN_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        out_fieldnames = [
            "marca", "modelo_base", "tipo", "motor_full", "cv", "transmision",
            "version_trim", "modelo_sin_marca",
            "combustible", "precio_usd", "moneda_origen", "precio_origen",
            "anio", "kms", "ubicacion",
        ]

        with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=out_fieldnames)
            writer.writeheader()

            for r in reader:
                marca_row = norm(r.get("marca", ""))  # <- AHORA SE USA LA MARCA DEL CSV
                parsed = parse_model_fields(marca_row, r.get("modelo", ""))

                out = {k: "" for k in out_fieldnames}
                out.update(parsed)

                out["combustible"] = norm(r.get("combustible", ""))
                out["moneda_origen"] = norm(r.get("moneda_origen", ""))
                out["ubicacion"] = norm(r.get("ubicacion", ""))

                out["precio_usd"] = safe_int(r.get("precio_usd", ""))
                out["precio_origen"] = safe_int(r.get("precio_origen", ""))

                out["anio"] = safe_int(r.get("anio", ""))
                out["kms"] = safe_int(r.get("kms", ""))

                writer.writerow(out)

    print(f"✅ Generado: {OUT_CSV.resolve()}")

if __name__ == "__main__":
    main()
