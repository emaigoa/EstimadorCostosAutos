import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from pathlib import Path
import joblib
import unicodedata

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import GradientBoostingRegressor
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "autos_dataset_limpio.csv"
OUT_PATH = BASE_DIR / "models" / "modelo_rango_autos.joblib"
# ==================

YEAR_REF = 2026
MIN_YEAR = 1970
MAX_YEAR = 2026
MAX_KMS = 600_000
# ==================


def safe_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def norm_text(s: str) -> str:
    """
    Normalización consistente para que:
    - 'T-cross', 'T-Cross', 't cross' => 't cross'
    - quita acentos, lower, trim, colapsa espacios, guiones -> espacio
    """
    if s is None:
        return ""
    s = str(s).replace("–", "-").replace("—", "-")
    s = strip_accents(s)
    s = s.lower().strip()
    s = s.replace("-", " ")
    s = " ".join(s.split())
    return s


def prepare_ml_table(df: pd.DataFrame):
    # --- numéricos ---
    safe_numeric(df, ["precio_usd", "anio", "kms", "precio_origen", "cv"])

    # --- filtros mínimos ---
    df = df[df["precio_usd"].notna() & (df["precio_usd"] > 0)].copy()
    df = df[df["anio"].between(MIN_YEAR, MAX_YEAR)].copy()
    df = df[df["kms"].between(0, MAX_KMS)].copy()

    # --- normalizar categóricas IMPORTANTES ---
    # (esto es CLAVE para que los freq_maps no den 0 por diferencias de escritura)
    cat_cols = ["marca", "modelo_base", "version_trim", "ubicacion", "combustible", "tipo", "transmision"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].map(norm_text)

    # --- features derivadas ---
    df["edad"] = YEAR_REF - df["anio"]
    df["kms_por_anio"] = df["kms"] / df["edad"].clip(lower=1)

    # --- cv imputación (mejor: por modelo_base primero, luego global) ---
    cv_global_median = df["cv"].median() if "cv" in df.columns else np.nan

    median_cv_by_model = {}
    if "cv" in df.columns and "modelo_base" in df.columns:
        median_cv_by_model = df.groupby("modelo_base")["cv"].median().dropna().to_dict()
        df["cv"] = df.apply(
            lambda r: median_cv_by_model.get(r["modelo_base"], np.nan) if pd.isna(r["cv"]) else r["cv"],
            axis=1
        )

    if "cv" in df.columns:
        df["cv"] = df["cv"].fillna(cv_global_median).fillna(0)

    # --- frecuencia (guardar mapas para predict) ---
    freq_maps = {}
    for col in ["marca", "modelo_base", "version_trim", "ubicacion"]:
        if col in df.columns:
            vc = df[col].value_counts()
            freq_maps[col] = vc.to_dict()
            df[col + "_freq"] = df[col].map(vc).fillna(0).astype(int)

    # --- one-hot (incluimos marca) ---
    onehot_cols = [c for c in ["marca", "combustible", "tipo", "transmision"] if c in df.columns]
    df_ml = pd.get_dummies(df, columns=onehot_cols, drop_first=True)

    onehot_feature_cols = [
        c for c in df_ml.columns
        if c.startswith("marca_")
        or c.startswith("combustible_")
        or c.startswith("tipo_")
        or c.startswith("transmision_")
    ]

    # --- features finales ---
    base_features = [
        "anio", "edad", "kms", "kms_por_anio", "cv",
        "marca_freq", "modelo_base_freq", "version_trim_freq", "ubicacion_freq",
    ]
    base_features = [c for c in base_features if c in df_ml.columns]

    features = base_features + onehot_feature_cols

    X = df_ml[features].copy()
    y = df_ml["precio_usd"].copy()

    preproc = {
        "year_ref": YEAR_REF,
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "max_kms": MAX_KMS,
        "features": features,
        "freq_maps": freq_maps,
        "onehot_feature_cols": onehot_feature_cols,
        "cv_global_median": float(cv_global_median) if pd.notna(cv_global_median) else 0.0,
        "median_cv_by_model": median_cv_by_model,
        # para que en la API uses la misma normalización:
        "text_norm": "lower+no_accents+hyphen_to_space+collapse_spaces"
    }

    return X, y, preproc


def main():
    df = pd.read_csv(CSV_PATH)

    X, y, preproc = prepare_ml_table(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    quantiles = [0.10, 0.50, 0.90]
    models = {}

    print("Entrenando modelos cuantílicos (P10, P50, P90)...\n")

    for q in quantiles:
        model = GradientBoostingRegressor(
            loss="quantile",
            alpha=q,
            random_state=42,
            n_estimators=1400,
            learning_rate=0.03,
            max_depth=4,
            subsample=0.9
        )
        model.fit(X_train, y_train)
        models[q] = model

        pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, pred)
        print(f"Quantile P{int(q*100):02d} | MAE (ref): USD {mae:.2f}")

    pred50 = models[0.50].predict(X_test)
    mae50 = mean_absolute_error(y_test, pred50)
    rmse50 = float(np.sqrt(mean_squared_error(y_test, pred50)))
    r250 = r2_score(y_test, pred50)

    print("\n===== METRICAS (P50 en TEST) =====")
    print("Registros usados:", len(X))
    print("Features:", len(preproc["features"]))
    print(f"MAE : USD {mae50:.2f}")
    print(f"RMSE: USD {rmse50:.2f}")
    print(f"R2  : {r250:.4f}")

    bundle = {
        "models": models,
        "preproc": preproc
    }
    joblib.dump(bundle, OUT_PATH)
    print("\n✅ Guardado en:", OUT_PATH.resolve())


if __name__ == "__main__":
    main()
