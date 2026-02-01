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

# ===== PATHS =====
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "pipelines" / "autos_dataset_limpio.csv"
OUT_PATH = BASE_DIR / "api" / "model" / "modelo_rango_autos.joblib"

# ===== LIMITES =====
YEAR_REF = 2026
MIN_YEAR = 1970
MAX_YEAR = 2026
MAX_KMS = 600_000

# ✅ filtro de precios para evitar outliers que te rompen el MAE
# ajustalo si querés incluir superdeportivos
MIN_PRICE_USD = 1_000
MAX_PRICE_USD = 700_000


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
    Normalización consistente:
    - quita acentos
    - lower
    - guiones -> espacio
    - colapsa espacios
    """
    if s is None:
        return ""
    s = str(s).replace("–", "-").replace("—", "-")
    s = strip_accents(s)
    s = s.lower().strip()
    s = s.replace("-", " ")
    s = " ".join(s.split())
    return s


def to_bool01(x) -> int:
    s = norm_text(x)
    if s in {"true", "verdadero", "1", "si", "sí", "yes", "y"}:
        return 1
    if s in {"false", "falso", "0", "no", "n"}:
        return 0
    return 0


def prepare_ml_table(df: pd.DataFrame):
    # --- numéricos ---
    safe_numeric(df, ["precio_usd", "anio", "kms"])

    # --- bools a 0/1 ---
    if "aire" in df.columns:
        df["aire"] = df["aire"].apply(to_bool01).astype(int)
    else:
        df["aire"] = 0

    if "vidrio" in df.columns:
        df["vidrio"] = df["vidrio"].apply(to_bool01).astype(int)
    elif "cristales" in df.columns:
        df["vidrio"] = df["cristales"].apply(to_bool01).astype(int)
    else:
        df["vidrio"] = 0

    # --- filtros mínimos ---
    df = df[df["precio_usd"].notna()].copy()
    df = df[df["precio_usd"].between(MIN_PRICE_USD, MAX_PRICE_USD)].copy()
    df = df[df["anio"].between(MIN_YEAR, MAX_YEAR)].copy()
    df = df[df["kms"].between(0, MAX_KMS)].copy()

    # --- normalizar categóricas reales del CSV ---
    cat_cols = ["marca", "modelo", "version", "combustible", "transmision", "direccion"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].map(norm_text)
        else:
            df[c] = ""

    # --- features derivadas ---
    df["edad"] = YEAR_REF - df["anio"]
    df["edad"] = df["edad"].clip(lower=0)  # por si aparece anio==YEAR_REF
    df["kms_por_anio"] = df["kms"] / df["edad"].replace(0, 1)

    # --- frecuencia (guardar mapas para predict) ---
    freq_maps = {}
    for col in ["marca", "modelo", "version"]:
        vc = df[col].value_counts()
        freq_maps[col] = vc.to_dict()
        df[col + "_freq"] = df[col].map(vc).fillna(0).astype(int)

    # --- one-hot (más estable) ---
    onehot_cols = ["marca", "combustible", "transmision", "direccion"]
    onehot_cols = [c for c in onehot_cols if c in df.columns]

    # ✅ drop_first=False para estabilidad y para que sea más fácil alinear columnas en la API
    df_ml = pd.get_dummies(df, columns=onehot_cols, drop_first=False)

    onehot_feature_cols = [
        c for c in df_ml.columns
        if c.startswith("marca_")
        or c.startswith("combustible_")
        or c.startswith("transmision_")
        or c.startswith("direccion_")
    ]

    # --- features finales ---
    base_features = [
        "anio", "edad", "kms", "kms_por_anio",
        "aire", "vidrio",
        "marca_freq", "modelo_freq", "version_freq",
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
        "min_price_usd": MIN_PRICE_USD,
        "max_price_usd": MAX_PRICE_USD,
        "features": features,
        "x_columns": X.columns.tolist(),  # ✅ clave para reindex en predict
        "freq_maps": freq_maps,
        "onehot_cols": onehot_cols,
        "onehot_feature_cols": onehot_feature_cols,
        "text_norm": "lower+no_accents+hyphen_to_space+collapse_spaces",
        "bool_norm": "true/verdadero/1/si => 1 else 0",
        "schema": {
            "expected_cols": [
                "marca", "modelo", "version", "anio", "kms", "precio_usd",
                "combustible", "transmision", "direccion", "aire", "vidrio"
            ]
        }
    }

    return X, y, preproc


def main():
    df = pd.read_csv(CSV_PATH)

    X, y, preproc = prepare_ml_table(df)

    # mini sanity check
    print("\n===== CHECK PRECIOS (USD) =====")
    s = y.describe(percentiles=[0.5, 0.9, 0.95, 0.99])
    print(s.to_string())
    print("\nRegistros usados:", len(X))
    print("Features:", len(preproc["features"]))

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    quantiles = [0.10, 0.50, 0.90]
    models = {}

    print("\nEntrenando modelos cuantílicos (P10, P50, P90)...\n")

    for q in quantiles:
        model = GradientBoostingRegressor(
            loss="quantile",
            alpha=q,
            random_state=42,
            n_estimators=1200,
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

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUT_PATH)
    print("\n✅ Guardado en:", OUT_PATH.resolve())


if __name__ == "__main__":
    main()
