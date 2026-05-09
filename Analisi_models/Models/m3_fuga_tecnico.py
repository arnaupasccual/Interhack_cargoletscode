"""
m3_fuga_tecnico.py
Modelo M3 — Detección de fuga en producto técnico
Isolation Forest por familia técnica sobre patrón individual del cliente.

Columnas reales usadas:
  silence_streak, trend_slope_30d, trend_slope_90d,
  pct_families_active, inter_order_avg, inter_order_std,
  ratio_vs_potential, reactivation_signal,
  Bloque analítico, Familia_H, Id. Cliente,
  es_devolucion, evento_especial
  label_m0 (de M0)
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

# ── Configuración ─────────────────────────────────────────────────────────────

FEATURES_M3 = [
    "silence_streak",
    "trend_slope_30d",
    "trend_slope_90d",
    "pct_families_active",
    "ratio_vs_potential",
]

IF_CONTAMINATION  = 0.05   # ~5% esperado de anomalías reales
IF_N_ESTIMATORS   = 100
IF_RANDOM_STATE   = 42
ANOMALY_THRESHOLD = -0.05

TECNICO_BLOQUES = {"implantes", "ortodoncia", "protesica", "tecnico",
                   "cirugia", "endodoncia", "periodoncia"}

SILENCIO_INACTIVO_MULT = 3.0

# ── Helpers ───────────────────────────────────────────────────────────────────

def es_tecnico(bloque) -> bool:
    if pd.isna(bloque):
        return False
    return any(t in str(bloque).lower().strip() for t in TECNICO_BLOQUES)


def fit_isolation_forest(df_fam: pd.DataFrame):
    X = df_fam[FEATURES_M3].fillna(df_fam[FEATURES_M3].median())
    scaler  = StandardScaler()
    X_sc    = scaler.fit_transform(X)
    iforest = IsolationForest(
        n_estimators=IF_N_ESTIMATORS,
        contamination=IF_CONTAMINATION,
        random_state=IF_RANDOM_STATE,
        n_jobs=-1,
    )
    iforest.fit(X_sc)
    return iforest, scaler


def score_anomaly(df_fam, iforest, scaler) -> np.ndarray:
    X = df_fam[FEATURES_M3].fillna(df_fam[FEATURES_M3].median())
    return iforest.score_samples(scaler.transform(X))


def classify_anomaly_type(row: pd.Series) -> str:
    tipos = []
    if row["silence_streak"] > row["inter_order_avg"] * 2.0:
        tipos.append("silencio_excesivo")
    if row["trend_slope_30d"] < -0.05:
        tipos.append("caida_volumen_aguda")
    if row["trend_slope_90d"] < -0.03:
        tipos.append("tendencia_negativa_sostenida")
    if row["pct_families_active"] < 0.50:
        tipos.append("reduccion_familias_activas")
    return "|".join(tipos) if tipos else "patron_anomalo_general"


def build_motivo_a4(row: pd.Series) -> str:
    return (
        f"Anomalía en {row['Familia_H']} (score: {row['anomaly_score']:.3f}). "
        f"Tipo: {row['anomaly_type'].replace('|', ', ')}. "
        f"Lleva {row['silence_streak']:.0f} días sin pedir "
        f"(media: {row['inter_order_avg']:.0f} días). "
        f"Ratio: {row['ratio_vs_potential']*100:.0f}% del potencial."
    )


def build_motivo_a5(row: pd.Series) -> str:
    return (
        f"Cliente recuperable en {row['Familia_H']}. "
        f"Silencio de {row['silence_streak']:.0f} días "
        f"(media: {row['inter_order_avg']:.0f} días) "
        f"con señal de reactivación detectada."
    )

# ── Runner ────────────────────────────────────────────────────────────────────

def run(df: pd.DataFrame, label_m0: pd.DataFrame = None) -> pd.DataFrame:
    print("[M3] Iniciando detección de fuga en producto técnico...")
    df = df.copy()

    if label_m0 is not None:
        df = df.merge(
            label_m0[["clinic_id", "familia", "label_m0"]],
            left_on=["Id. Cliente", "Familia_H"],
            right_on=["clinic_id", "familia"],
            how="left"
        )
    else:
        df["label_m0"] = "desconocido"

    # Filtrar: técnicos, no devoluciones, no eventos especiales
    mask = (
        df["Bloque analítico"].apply(es_tecnico) &
        (df.get("es_devolucion",   pd.Series(0, index=df.index)) == 0) &
        (df.get("evento_especial", pd.Series(0, index=df.index)) == 0) &
        (df["inter_order_avg"] > 0)
    )
    df_t = df[mask].copy()

    if df_t.empty:
        print("  [M3] Sin filas técnicas válidas.")
        return pd.DataFrame(columns=["Id. Cliente", "Familia_H",
                                     "anomaly_score", "anomaly_type",
                                     "activa_a4", "activa_a5",
                                     "motivo_a4", "motivo_a5"])

    df_t["anomaly_score"] = np.nan

    for fam, grp in df_t.groupby("Familia_H"):
        if len(grp) < 10:
            df_t.loc[grp.index, "anomaly_score"] = 0.0
            continue
        iforest, scaler = fit_isolation_forest(grp)
        scores = score_anomaly(grp, iforest, scaler)
        df_t.loc[grp.index, "anomaly_score"] = scores
        n_anom = (scores < ANOMALY_THRESHOLD).sum()
        print(f"    '{fam}': {len(grp)} clientes, anómalos: {n_anom}")

    df_t["anomaly_type"] = df_t.apply(classify_anomaly_type, axis=1)

    # A4: anómalo con historial real (no marginal)
    df_t["activa_a4"] = (
        (df_t["anomaly_score"] < ANOMALY_THRESHOLD) &
        (df_t["label_m0"] != "marginal")
    )

    # A5: reactivation_signal disponible directamente en el CSV
    if "reactivation_signal" in df_t.columns:
        df_t["activa_a5"] = df_t["reactivation_signal"].astype(bool)
    else:
        # Fallback: silencio largo + ratio muy bajo pero > 0
        df_t["activa_a5"] = (
            (df_t["silence_streak"] > df_t["inter_order_avg"] * SILENCIO_INACTIVO_MULT) &
            (df_t["ratio_vs_potential"] > 0) &
            (df_t["ratio_vs_potential"] < 0.15)
        )

    df_t["motivo_a4"] = df_t.apply(
        lambda r: build_motivo_a4(r) if r["activa_a4"] else None, axis=1
    )
    df_t["motivo_a5"] = df_t.apply(
        lambda r: build_motivo_a5(r) if r["activa_a5"] else None, axis=1
    )

    print(f"  [M3] A4: {df_t['activa_a4'].sum()} | A5: {df_t['activa_a5'].sum()}")

    return df_t[["Id. Cliente", "Familia_H", "anomaly_score", "anomaly_type",
                 "activa_a4", "activa_a5", "motivo_a4", "motivo_a5"]]