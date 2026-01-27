import joblib
import pandas as pd

BUNDLE_PATH = "modelo_rango_autos.joblib"

bundle = joblib.load(BUNDLE_PATH)
models = bundle["models"]
preproc = bundle["preproc"]

features = preproc["features"]
freq_maps = preproc["freq_maps"]
onehot_feature_cols = preproc["onehot_feature_cols"]
year_ref = preproc["year_ref"]

# EJEMPLO
nuevo = {
    "modelo_base": "Sandero",
    "version_trim": "",
    "ubicacion": "Mar Del Plata - Bs.As. Costa Atlantica",
    "combustible": "nafta",
    "tipo": "",
    "transmision": "MT",
    "anio": 2017,
    "kms": 120000,
    "cv": 105
}

df = pd.DataFrame([nuevo])

# features derivadas
df["edad"] = year_ref - df["anio"]
df["kms_por_anio"] = df["kms"] / df["edad"].clip(lower=1)

# freq
df["modelo_base_freq"] = df["modelo_base"].map(freq_maps.get("modelo_base", {})).fillna(0).astype(int)
df["version_trim_freq"] = df["version_trim"].map(freq_maps.get("version_trim", {})).fillna(0).astype(int)
df["ubicacion_freq"] = df["ubicacion"].map(freq_maps.get("ubicacion", {})).fillna(0).astype(int)

# one-hot esperado
for col in onehot_feature_cols:
    df[col] = 0

def set_onehot(prefix, value):
    if isinstance(value, str):
        col = f"{prefix}_{value}"
        if col in df.columns:
            df[col] = 1

set_onehot("combustible", df.loc[0, "combustible"])
set_onehot("tipo", df.loc[0, "tipo"])
set_onehot("transmision", df.loc[0, "transmision"])

# armar X final
X_one = df.reindex(columns=features, fill_value=0)

p10 = float(models[0.10].predict(X_one)[0])
p50 = float(models[0.50].predict(X_one)[0])
p90 = float(models[0.90].predict(X_one)[0])

print(f"Rango estimado (P10–P90): USD {p10:,.0f} – {p90:,.0f}")
print(f"Estimación central (P50): USD {p50:,.0f}")
