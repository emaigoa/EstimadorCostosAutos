import json
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "autos_dataset_limpio.csv"
OUT_JSON = BASE_DIR / "front" / "catalog.json"

TOP_MODELS_PER_BRAND = 30       # evita modelos raros/basura
TOP_TYPES_PER_MODEL = 12
TOP_VERSIONS_PER_MODEL = 30
TOP_CV_PER_MODEL = 8            # sugerencias por modelo
TOP_CV_PER_TRIM = 8             # sugerencias por trim

def clean_str(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def top_list(series: pd.Series, top_n: int):
    return (
        series.loc[series.ne("")]
        .value_counts()
        .head(top_n)
        .index
        .tolist()
    )

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

    # CV numérico
    if "cv" in df.columns:
        df["cv"] = pd.to_numeric(df["cv"], errors="coerce")
    else:
        df["cv"] = pd.NA

    catalog = {}

    for brand, sub in df.groupby("marca"):
        model_counts = sub["modelo_base"].value_counts()
        top_models = list(model_counts.head(TOP_MODELS_PER_BRAND).index)

        brand_entry = {}
        for model in top_models:
            sm = sub[sub["modelo_base"] == model].copy()

            years = sm["anio"]
            if years.empty:
                continue

            year_min = int(years.min())
            year_max = int(years.max())

            tipos = top_list(sm["tipo"], TOP_TYPES_PER_MODEL)
            versiones = top_list(sm["version_trim"], TOP_VERSIONS_PER_MODEL)
            combustibles = top_list(sm["combustible"], 10)
            transmisiones = top_list(sm["transmision"], 10)

            # ===== CV SUGERIDOS =====
            tmp = sm.copy()
            tmp = tmp[tmp["cv"].notna() & (tmp["cv"] > 0)]
            tmp["cv"] = tmp["cv"].astype(int)

            # por modelo (top N)
            cv_by_model = []
            cv_median_model = ""
            if not tmp.empty:
                cv_by_model = (
                    tmp["cv"].value_counts()
                    .head(TOP_CV_PER_MODEL)
                    .index.tolist()
                )
                cv_median_model = int(tmp["cv"].median())

            # por trim (top N por cada trim)
            cv_by_trim = {}
            if not tmp.empty and "version_trim" in tmp.columns:
                for trim, st in tmp.groupby("version_trim"):
                    trim = (trim or "").strip()
                    if not trim:
                        continue
                    top_cv = (
                        st["cv"].value_counts()
                        .head(TOP_CV_PER_TRIM)
                        .index.tolist()
                    )
                    if top_cv:
                        cv_by_trim[trim] = top_cv

            brand_entry[model] = {
                "year_min": year_min,
                "year_max": year_max,
                "tipos": tipos,
                "versiones": versiones,
                "combustibles": combustibles,
                "transmisiones": transmisiones,

                # NUEVO: CV sugeridos (por modelo / por trim)
                "cv_by_model": cv_by_model,
                "cv_by_trim": cv_by_trim,
                "cv_median_model": cv_median_model,
            }

        catalog[brand] = brand_entry

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    print("✅ Generado:", OUT_JSON)

if __name__ == "__main__":
    main()
