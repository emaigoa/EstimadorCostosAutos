import json
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "autos_dataset_limpio.csv"
OUT_JSON = BASE_DIR / "front" / "catalog.json"

TOP_MODELS_PER_BRAND = 30     # para evitar “basura” en modelos raros
TOP_TYPES_PER_MODEL = 12
TOP_VERSIONS_PER_MODEL = 30

def clean_str(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    return s

def main():
    df = pd.read_csv(CSV_PATH)

    # Limpieza mínima
    for c in ["marca", "modelo_base", "tipo", "version_trim", "combustible", "transmision"]:
        if c in df.columns:
            df[c] = df[c].map(clean_str)

    df = df[df["marca"].ne("") & df["modelo_base"].ne("")].copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df = df[df["anio"].notna()].copy()
    df["anio"] = df["anio"].astype(int)

    catalog = {}

    for brand, sub in df.groupby("marca"):
        model_counts = sub["modelo_base"].value_counts()
        top_models = list(model_counts.head(TOP_MODELS_PER_BRAND).index)

        brand_entry = {}
        for model in top_models:
            sm = sub[sub["modelo_base"] == model]
            years = sm["anio"]
            if years.empty:
                continue

            year_min = int(years.min())
            year_max = int(years.max())

            tipos = (
                sm["tipo"]
                .loc[sm["tipo"].ne("")]
                .value_counts()
                .head(TOP_TYPES_PER_MODEL)
                .index
                .tolist()
            )

            versiones = (
                sm["version_trim"]
                .loc[sm["version_trim"].ne("")]
                .value_counts()
                .head(TOP_VERSIONS_PER_MODEL)
                .index
                .tolist()
            )

            combustibles = (
                sm["combustible"]
                .loc[sm["combustible"].ne("")]
                .value_counts()
                .head(10)
                .index
                .tolist()
            )

            transmisiones = (
                sm["transmision"]
                .loc[sm["transmision"].ne("")]
                .value_counts()
                .head(10)
                .index
                .tolist()
            )

            brand_entry[model] = {
                "year_min": year_min,
                "year_max": year_max,
                "tipos": tipos,
                "versiones": versiones,
                "combustibles": combustibles,
                "transmisiones": transmisiones,
            }

        catalog[brand] = brand_entry

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    print("✅ Generado:", OUT_JSON)

if __name__ == "__main__":
    main()
