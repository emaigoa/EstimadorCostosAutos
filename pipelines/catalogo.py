import json
import pandas as pd
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "pipelines" /"autos_dataset_limpio.csv"
OUT_JSON = BASE_DIR / "front" / "catalog.json"


def clean_str(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def norm_brand(s: str) -> str:
    """
    Si querés evitar que 'Citroën' y 'Citroen' queden como marcas distintas,
    usá esta normalización.
    Si preferís conservar acentos, no la uses.
    """
    s = clean_str(s)
    s = strip_accents(s)
    s = " ".join(s.split())
    return s


def to_bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "si", "sí", "yes", "y"])


def top_unique(series: pd.Series):
    """Devuelve TODOS los valores únicos no vacíos (sin limitar)."""
    s = series.loc[series.ne("")].dropna().astype(str)
    # podés ordenarlo por frecuencia si querés: value_counts().index.tolist()
    return sorted(s.unique().tolist())


def main():
    df = pd.read_csv(CSV_PATH)

    # columnas esperadas (si falta alguna, la creamos vacía)
    cols = ["marca", "modelo", "version", "combustible", "transmision", "direccion", "anio", "aire", "vidrio"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    # limpiar strings
    for c in ["marca", "modelo", "version", "combustible", "transmision", "direccion"]:
        df[c] = df[c].map(clean_str)

    # 🔧 OPCIONAL (recomendado): normalizar marca para evitar duplicados por acento/caso
    # df["marca"] = df["marca"].map(norm_brand)

    # booleans
    df["aire"] = to_bool_series(df["aire"]) if "aire" in df.columns else False
    df["vidrio"] = to_bool_series(df["vidrio"]) if "vidrio" in df.columns else False

    # años válidos
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df = df[df["anio"].notna()].copy()
    df["anio"] = df["anio"].astype(int)

    # filtrar basura mínima
    df = df[df["marca"].ne("") & df["modelo"].ne("")].copy()

    catalog = {}

    # ✅ IMPORTANTE: iteramos TODAS las marcas presentes
    for brand in sorted(df["marca"].unique().tolist()):
        df_brand = df[df["marca"] == brand]
        brand_entry = {}

        # ✅ SIN LÍMITE: todos los modelos de esa marca
        for model in sorted(df_brand["modelo"].unique().tolist()):
            if not model:
                continue

            sm = df_brand[df_brand["modelo"] == model].copy()
            if sm.empty:
                continue

            year_min = int(sm["anio"].min())
            year_max = int(sm["anio"].max())

            brand_entry[model] = {
                "year_min": year_min,
                "year_max": year_max,
                "versiones": top_unique(sm["version"]),
                "combustibles": top_unique(sm["combustible"]),
                "transmisiones": top_unique(sm["transmision"]),
                "direcciones": top_unique(sm["direccion"]),
                "tiene_aire": bool(sm["aire"].any()),
                "tiene_vidrio": bool(sm["vidrio"].any()),
            }

        # ✅ aunque no tenga modelos, igual queda la marca (vacía)
        catalog[brand] = brand_entry

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ Generado:", OUT_JSON.resolve())
    print("Marcas en catálogo:", len(catalog))


if __name__ == "__main__":
    main()
