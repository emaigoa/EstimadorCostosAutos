from __future__ import annotations

from pathlib import Path
import joblib
import pandas as pd
import numpy as np
import unicodedata


# =========================
# Load
# =========================
def load_bundle(model_path: str | Path):
    model_path = Path(model_path)
    bundle = joblib.load(model_path)
    if "models" not in bundle or "preproc" not in bundle:
        raise ValueError("El .joblib no tiene la estructura esperada: {'models', 'preproc'}")
    return bundle


# =========================
# Text + bool normalization (igual que entrenamiento)
# =========================
def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def norm_text(s: str) -> str:
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


def _safe_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


# =========================
# Core: build feature row(s)
# =========================
def build_features(bundle: dict, rows: dict | list[dict] | pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve X listo para .predict() con exactamente las columnas esperadas (preproc['features']).
    Acepta:
      - dict (un auto)
      - list[dict] (muchos autos)
      - DataFrame
    """
    pre = bundle["preproc"]
    features = list(pre["features"])
    year_ref = int(pre["year_ref"])

    # DataFrame input
    if isinstance(rows, pd.DataFrame):
        df = rows.copy()
    elif isinstance(rows, dict):
        df = pd.DataFrame([rows])
    elif isinstance(rows, list):
        df = pd.DataFrame(rows)
    else:
        raise TypeError("rows debe ser dict, list[dict] o pandas.DataFrame")

    # Asegurar columnas mínimas
    # (si faltan, las creamos vacías / 0)
    expected = pre.get("schema", {}).get("expected_cols", [])
    for c in expected:
        if c not in df.columns:
            df[c] = "" if c not in {"anio", "kms", "aire", "vidrio"} else 0

    # Numericos
    _safe_numeric(df, ["anio", "kms"])

    # Bools
    # Aire
    if "aire" in df.columns:
        df["aire"] = df["aire"].apply(to_bool01).astype(int)
    else:
        df["aire"] = 0

    # Vidrio (o cristales)
    if "vidrio" in df.columns:
        df["vidrio"] = df["vidrio"].apply(to_bool01).astype(int)
    elif "cristales" in df.columns:
        df["vidrio"] = df["cristales"].apply(to_bool01).astype(int)
    else:
        df["vidrio"] = 0

    # Normalizar categóricas
    cat_cols = ["marca", "modelo", "version", "combustible", "transmision", "direccion"]
    for c in cat_cols:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].map(norm_text)

    # Derivadas
    # edad: si anio es NaN -> edad NaN (luego lo tratamos)
    df["edad"] = year_ref - df["anio"]
    df["kms_por_anio"] = df["kms"] / df["edad"].clip(lower=1)

    # Frecuencias (mapas guardados del entrenamiento)
    freq_maps = pre.get("freq_maps", {})
    for col in ["marca", "modelo", "version"]:
        m = freq_maps.get(col, {})
        df[col + "_freq"] = df[col].map(m).fillna(0).astype(int)

    # One-hot sobre las mismas columnas que en entrenamiento
    onehot_cols = ["marca", "combustible", "transmision", "direccion"]
    df_oh = pd.get_dummies(df, columns=[c for c in onehot_cols if c in df.columns], drop_first=True)

    # Alinear columnas: crear faltantes en 0 y ordenar
    for f in features:
        if f not in df_oh.columns:
            df_oh[f] = 0

    X = df_oh[features].copy()

    # Limpieza final de NaNs / inf (por si anio/kms vino vacío)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    return X


# =========================
# Predict quantiles
# =========================
def predict_price_range(bundle: dict, row: dict) -> dict:
    """
    Devuelve dict con P10/P50/P90 y un rango recomendado.
    """
    X = build_features(bundle, row)
    models = bundle["models"]

    # Claves esperadas: 0.1, 0.5, 0.9 (floats)
    p10 = float(models[0.10].predict(X)[0]) if 0.10 in models else None
    p50 = float(models[0.50].predict(X)[0]) if 0.50 in models else None
    p90 = float(models[0.90].predict(X)[0]) if 0.90 in models else None

    # Armar rango recomendado (si tenemos los 3)
    # - si algo falta, igual devolvemos lo que haya
    out = {
        "p10": None if p10 is None else round(p10, 2),
        "p50": None if p50 is None else round(p50, 2),
        "p90": None if p90 is None else round(p90, 2),
        "currency": "USD",
    }

    if p10 is not None and p50 is not None and p90 is not None:
        # Rango “realista” típico (podés cambiarlo a p10-p90 o p20-p80 si entrenás otros cuantiles)
        out["recommended_min"] = round(p10, 2)
        out["recommended_max"] = round(p90, 2)
        out["recommended_mid"] = round(p50, 2)

    return out


def predict_batch(bundle: dict, rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    """
    Predicción en lote. Devuelve DataFrame con columnas p10/p50/p90.
    """
    X = build_features(bundle, rows)
    models = bundle["models"]

    pred = pd.DataFrame(index=X.index)
    if 0.10 in models:
        pred["p10"] = models[0.10].predict(X)
    if 0.50 in models:
        pred["p50"] = models[0.50].predict(X)
    if 0.90 in models:
        pred["p90"] = models[0.90].predict(X)

    return pred.round(2)


# =========================
# Mini test manual
# =========================
if __name__ == "__main__":
    # Ajustá este path a tu proyecto
    bundle = load_bundle("api/model/modelo_rango_autos.joblib")

    sample = {
        "marca": "Renault",
        "modelo": "Sandero",
        "version": "Stepway Privilege",
        "combustible": "nafta",
        "transmision": "mt",
        "direccion": "hidraulica",
        "anio": 2017,
        "kms": 120000,
        "aire": "si",
        "vidrio": "si"
    }

    print(predict_price_range(bundle, sample))