import joblib
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path


# ===== PATH ROBUSTO (Render) =====
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "model" / "modelo_rango_autos.joblib"

bundle = joblib.load(MODEL_PATH)
models = bundle["models"]          # {0.10:..., 0.50:..., 0.90:...}
preproc = bundle["preproc"]

FEATURES = preproc["features"]
FREQ_MAPS = preproc["freq_maps"]
YEAR_REF = preproc["year_ref"]


app = FastAPI(title="Estimador Autos (Rango)")

# ===== CORS (para HTML/Netlify/etc) =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en producción poné tu dominio, ej: ["https://tuweb.netlify.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AutoIn(BaseModel):
    anio: int
    kms: int
    cv: int | None = None
    combustible: str | None = None
    tipo: str | None = None
    transmision: str | None = None
    modelo_base: str | None = None
    version_trim: str | None = None
    ubicacion: str | None = None


def _norm_str(x):
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def build_features(payload: dict) -> pd.DataFrame:
    # normalizar strings para que freq maps matcheen mejor
    for k in ["combustible", "tipo", "transmision", "modelo_base", "version_trim", "ubicacion"]:
        if k in payload:
            payload[k] = _norm_str(payload[k])

    df = pd.DataFrame([payload])

    # numéricos
    for c in ["anio", "kms", "cv"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # derivadas
    df["edad"] = YEAR_REF - df["anio"]
    df["kms_por_anio"] = df["kms"] / df["edad"].clip(lower=1)

    # cv fallback
    if "cv" not in df.columns or df["cv"].isna().all():
        df["cv"] = 0
    df["cv"] = df["cv"].fillna(0)

    # freq encoding (si el texto no existe en el mapa -> 0)
    for col in ["modelo_base", "version_trim", "ubicacion"]:
        fmap = FREQ_MAPS.get(col, {})
        if col in df.columns:
            df[col + "_freq"] = df[col].map(fmap).fillna(0).astype(int)
        else:
            df[col + "_freq"] = 0

    # one-hot
    onehot_cols = [c for c in ["combustible", "tipo", "transmision"] if c in df.columns]
    df_ml = pd.get_dummies(df, columns=onehot_cols, drop_first=True)

    # asegurar columnas features exactas
    for col in FEATURES:
        if col not in df_ml.columns:
            df_ml[col] = 0

    X = df_ml[FEATURES].copy()
    return X


@app.get("/")
def health():
    return {"ok": True, "model_loaded": True}


@app.post("/predict")
def predict(auto: AutoIn):
    X = build_features(auto.model_dump())

    p10 = float(models[0.10].predict(X)[0])
    p50 = float(models[0.50].predict(X)[0])
    p90 = float(models[0.90].predict(X)[0])

    return {
        "p10": round(p10, 2),
        "p50": round(p50, 2),
        "p90": round(p90, 2),
        "range": [round(p10, 2), round(p90, 2)]
    }
