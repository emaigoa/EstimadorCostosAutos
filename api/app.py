import joblib
import pandas as pd
import numpy as np
import unicodedata
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Optional


# ===== PATH ROBUSTO =====
BASE_DIR = Path(__file__).resolve().parent

# probamos ambas (vos tenías "model", pero a veces es "models")
CANDIDATES = [
    BASE_DIR / "model" / "modelo_rango_autos.joblib",
    BASE_DIR / "models" / "modelo_rango_autos.joblib",
]

MODEL_PATH = next((p for p in CANDIDATES if p.exists()), CANDIDATES[0])

bundle = joblib.load(MODEL_PATH)
models = bundle["models"]          # {0.10:..., 0.50:..., 0.90:...}
preproc = bundle["preproc"]

FEATURES = preproc["features"]
FREQ_MAPS = preproc.get("freq_maps", {})
YEAR_REF = int(preproc.get("year_ref", 2026))

CV_GLOBAL_MEDIAN = float(preproc.get("cv_global_median", 0.0))
MEDIAN_CV_BY_MODEL = preproc.get("median_cv_by_model", {}) or {}


# ===== Normalización igual a entrenamiento =====
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


def _norm_str_or_none(x):
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def _to_bool(x) -> int:
    """Devuelve 1/0 para aire/vidrio (acepta true/1/si)."""
    if x is None:
        return 0
    if isinstance(x, bool):
        return int(x)
    s = str(x).strip().lower()
    return 1 if s in {"true", "1", "si", "sí", "yes", "y"} else 0


# ===== FastAPI =====
app = FastAPI(title="Estimador Autos (Rango)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AutoIn(BaseModel):
    # numéricos base
    anio: int
    kms: int

    # opcionales
    cv: Optional[int] = None

    # NUEVOS (tu CSV nuevo)
    marca: Optional[str] = None
    modelo: Optional[str] = None
    version: Optional[str] = None
    direccion: Optional[str] = None
    aire: Optional[bool] = None
    vidrio: Optional[bool] = None
    combustible: Optional[str] = None
    transmision: Optional[str] = None

    # VIEJOS (compatibilidad con bundle anterior)
    tipo: Optional[str] = None
    modelo_base: Optional[str] = None
    version_trim: Optional[str] = None
    ubicacion: Optional[str] = None


def build_features(payload: dict) -> pd.DataFrame:
    """
    Construye X asegurando columnas FEATURES exactas.
    - Normaliza strings para freq_maps y para one-hot.
    - Calcula edad/kms_por_anio si están en FEATURES.
    - Imputa cv si aplica.
    """

    # 1) Normalización de strings (solo si vienen)
    #    Hacemos norm_text para TODO lo categórico que podría entrar en freq_maps o onehot.
    cat_candidates = {
        "marca", "modelo", "version", "direccion",
        "combustible", "transmision", "tipo",
        "modelo_base", "version_trim", "ubicacion"
    }

    for k in list(payload.keys()):
        if k in cat_candidates:
            payload[k] = _norm_str_or_none(payload.get(k))
            if payload[k] is not None:
                payload[k] = norm_text(payload[k])

    # 2) Booleans -> int (por si tu entrenamiento los incluyó como features)
    #    Si el modelo no los usa, igual quedan y luego se descartan.
    payload["aire"] = _to_bool(payload.get("aire"))
    payload["vidrio"] = _to_bool(payload.get("vidrio"))

    df = pd.DataFrame([payload])

    # 3) Numéricos
    for c in ["anio", "kms", "cv", "aire", "vidrio"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 4) Derivadas (solo si el modelo las requiere)
    if "edad" in FEATURES:
        df["edad"] = YEAR_REF - df["anio"]
    if "kms_por_anio" in FEATURES:
        edad = (YEAR_REF - df["anio"]).clip(lower=1)
        df["kms_por_anio"] = df["kms"] / edad

    # 5) Imputación cv (si tu modelo la usa)
    if "cv" in df.columns:
        # Si cv viene NaN, intentamos por modelo (si hay mapa y hay alguna columna de modelo)
        if df["cv"].isna().all():
            # preferimos modelo_base si existe, sino modelo
            model_key_col = None
            if "modelo_base" in df.columns and df["modelo_base"].notna().any():
                model_key_col = "modelo_base"
            elif "modelo" in df.columns and df["modelo"].notna().any():
                model_key_col = "modelo"

            if model_key_col:
                mk = df.loc[0, model_key_col]
                df.loc[0, "cv"] = MEDIAN_CV_BY_MODEL.get(mk, np.nan)

        df["cv"] = df["cv"].fillna(CV_GLOBAL_MEDIAN).fillna(0)

    # 6) Freq encoding (para todas las claves que existan en preproc["freq_maps"])
    for col, fmap in FREQ_MAPS.items():
        freq_col = col + "_freq"
        if col in df.columns:
            df[freq_col] = df[col].map(fmap).fillna(0).astype(int)
        else:
            df[freq_col] = 0

    # 7) One-hot: detectamos bases mirando features (prefijos tipo "marca_", "combustible_", etc)
    onehot_bases = set()
    for f in FEATURES:
        if "_" in f:
            base = f.split("_", 1)[0]
            if base in {"marca", "combustible", "tipo", "transmision", "direccion", "modelo", "version"}:
                onehot_bases.add(base)

    onehot_cols = [c for c in onehot_bases if c in df.columns]
    df_ml = pd.get_dummies(df, columns=onehot_cols, drop_first=True)

    # 8) Forzar exactamente FEATURES
    for col in FEATURES:
        if col not in df_ml.columns:
            df_ml[col] = 0

    X = df_ml[FEATURES].copy()
    return X


@app.get("/")
def health():
    return {
        "ok": True,
        "model_loaded": True,
        "model_path": str(MODEL_PATH).replace("\\", "/"),
        "n_features": len(FEATURES),
        "year_ref": YEAR_REF,
    }


@app.post("/predict")
def predict(auto: AutoIn):
    X = build_features(auto.model_dump())

    p10 = float(models[0.10].predict(X)[0])
    p50 = float(models[0.50].predict(X)[0])
    p90 = float(models[0.90].predict(X)[0])

    # orden por si alguna vez se cruza (muy raro)
    lo = min(p10, p90)
    hi = max(p10, p90)

    return {
        "p10": round(p10, 2),
        "p50": round(p50, 2),
        "p90": round(p90, 2),
        "range": [round(lo, 2), round(hi, 2)],
    }
