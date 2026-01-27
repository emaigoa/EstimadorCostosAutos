import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from pathlib import Path
import joblib

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import GradientBoostingRegressor


# ===== CONFIG =====
CSV_PATH = Path("autos_dataset_limpio.csv")
OUT_PATH = Path("modelo_rango_autos.joblib")

YEAR_REF = 2026
MIN_YEAR = 1970
MAX_YEAR = 2026
MAX_KMS = 600_000
# ==================


def safe_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def prepare_ml_table(df: pd.DataFrame):
    """
    Devuelve:
      X (features ya numéricas, listas para sklearn),
      y (precio_usd),
      preproc (metadata para usar lo mismo en predict)
    """
    # --- numéricos ---
    safe_numeric(df, ["precio_usd", "anio", "kms", "precio_origen", "cv"])

    # --- filtros mínimos ---
    df = df[df["precio_usd"].notna() & (df["precio_usd"] > 0)].copy()
    df = df[df["anio"].between(MIN_YEAR, MAX_YEAR)].copy()
    df = df[df["kms"].between(0, MAX_KMS)].copy()

    # --- features derivadas ---
    df["edad"] = YEAR_REF - df["anio"]
    df["kms_por_anio"] = df["kms"] / df["edad"].clip(lower=1)

    # --- cv (imputación) ---
    if "cv" in df.columns:
        if "motor_full" in df.columns:
            df["cv"] = df.groupby("motor_full")["cv"].transform(lambda x: x.fillna(x.median()))
        df["cv"] = df["cv"].fillna(df["cv"].median())

    # --- frecuencia (guardar mapas para predict) ---
    freq_maps = {}
    for col in ["modelo_base", "version_trim", "ubicacion"]:
        if col in df.columns:
            vc = df[col].value_counts()
            freq_maps[col] = vc.to_dict()
            df[col + "_freq"] = df[col].map(vc).fillna(0).astype(int)

    # --- one-hot (guardar lista de columnas para predict) ---
    onehot_cols = [c for c in ["combustible", "tipo", "transmision"] if c in df.columns]
    df_ml = pd.get_dummies(df, columns=onehot_cols, drop_first=True)

    onehot_feature_cols = [
        c for c in df_ml.columns
        if c.startswith("combustible_") or c.startswith("tipo_") or c.startswith("transmision_")
    ]

    # --- features finales ---
    base_features = [
        "anio", "edad", "kms", "kms_por_anio", "cv",
        "modelo_base_freq", "version_trim_freq", "ubicacion_freq",
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
        "onehot_feature_cols": onehot_feature_cols
    }

    return X, y, preproc


def main():
    df = pd.read_csv(CSV_PATH)

    X, y, preproc = prepare_ml_table(df)

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    # Entrenar 3 modelos cuantílicos
    quantiles = [0.10, 0.50, 0.90]
    models = {}

    print("Entrenando modelos cuantílicos (P10, P50, P90)...\n")

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

        # Métrica rápida (solo referencia): MAE contra P50 (el central) o contra el propio q
        pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, pred)
        print(f"Quantile P{int(q*100):02d} | MAE (referencia): USD {mae:.2f}")

    # Métricas del central (P50) como “modelo principal”
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

    # Guardar bundle
    bundle = {
        "models": models,     # {0.10: model, 0.50: model, 0.90: model}
        "preproc": preproc
    }
    joblib.dump(bundle, OUT_PATH)
    print("\n✅ Guardado en:", OUT_PATH.resolve())


if __name__ == "__main__":
    main()
