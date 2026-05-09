"""
m0_perfil_cliente.py
Modelo M0 — Clasificación de perfil de cliente × familia
Leal / Promiscuo / Esporádico / Marginal

Columnas reales del CSV:
  Id. Cliente, Familia_H, ratio_vs_potential, inter_order_avg,
  inter_order_std, trend_slope_90d, silence_streak, pct_families_active,
  reactivation_signal, es_devolucion, es_pedido

Features derivados que calcula este módulo:
  coef_variacion     = inter_order_std / inter_order_avg
  tendencia_ratio    = trend_slope_90d  (proxy directo)
  pct_periodos_activos = derivado de silence_streak e inter_order_avg
  n_pedidos_12m      = estimado desde inter_order_avg
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import warnings
warnings.filterwarnings("ignore")


# ── Columnas de entrada esperadas (nombres reales del CSV) ────────────────────

COL_CLIENT   = "Id. Cliente"
COL_FAMILIA  = "Familia_H"
COL_BLOQUE   = "Bloque analítico"

# ── Features usados por M0 (todos calculados en prepare_features) ─────────────

FEATURES_M0 = [
    "ratio_vs_potential",
    "coef_variacion",
    "pct_periodos_activos",
    "tendencia_ratio",
    "n_pedidos_12m",
    "silence_streak",
]

# ── Umbrales (configurables) ──────────────────────────────────────────────────

RULES = {
    "marginal": {
        "ratio_vs_potential_max": 0.20,
        "n_pedidos_min":          2,
        "pct_periodos_max":       0.20,
    },
    "esporadico": {
        "coef_variacion_min": 0.80,
        "pct_periodos_max":   0.55,
        "n_pedidos_min":      2,
    },
    "leal": {
        "ratio_vs_potential_min": 0.70,
        "coef_variacion_max":     0.40,
        "pct_periodos_min":       0.75,
        "n_pedidos_min":          6,
    },
    "promiscuo": {
        "ratio_min":        0.20,
        "pct_periodos_min": 0.50,
        "n_pedidos_min":    4,
    },
}


# ── Preparación de features derivados ────────────────────────────────────────

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    A partir de las columnas reales del CSV calcula los features
    que necesita M0. No modifica las columnas originales.
    """
    df = df.copy()

    # coef_variacion: irregularidad normalizada
    df["coef_variacion"] = (
        df["inter_order_std"] / df["inter_order_avg"].replace(0, np.nan)
    ).fillna(1.0).clip(upper=3.0)

    # tendencia_ratio: usamos trend_slope_90d como proxy directo
    df["tendencia_ratio"] = df["trend_slope_90d"].fillna(0.0)

    # pct_periodos_activos: proporción de tiempo activo estimada
    # Si silence_streak es pequeño relativo a inter_order_avg × 12 meses
    # el cliente ha estado activo la mayor parte del año
    df["pct_periodos_activos"] = (
        1.0 - (df["silence_streak"] / (df["inter_order_avg"].replace(0, np.nan) * 12))
    ).clip(lower=0.0, upper=1.0).fillna(0.5)

    # n_pedidos_12m: estimado desde inter_order_avg (días entre pedidos)
    df["n_pedidos_12m"] = (
        365.0 / df["inter_order_avg"].replace(0, np.nan)
    ).fillna(1.0).clip(lower=0, upper=120).round().astype(int)

    return df


# ── Reglas de negocio ─────────────────────────────────────────────────────────

def apply_rules(row: pd.Series) -> str:
    r = row

    # 1. Marginal
    if (r["ratio_vs_potential"] < RULES["marginal"]["ratio_vs_potential_max"] or
            r["n_pedidos_12m"]      < RULES["marginal"]["n_pedidos_min"]          or
            r["pct_periodos_activos"] < RULES["marginal"]["pct_periodos_max"]):
        return "marginal"

    # 2. Esporádico
    if (r["coef_variacion"]       > RULES["esporadico"]["coef_variacion_min"] and
            r["pct_periodos_activos"] < RULES["esporadico"]["pct_periodos_max"]   and
            r["n_pedidos_12m"]       >= RULES["esporadico"]["n_pedidos_min"]):
        return "esporadico"

    # 3. Leal
    if (r["ratio_vs_potential"]   >= RULES["leal"]["ratio_vs_potential_min"] and
            r["coef_variacion"]       <= RULES["leal"]["coef_variacion_max"]     and
            r["pct_periodos_activos"] >= RULES["leal"]["pct_periodos_min"]       and
            r["n_pedidos_12m"]        >= RULES["leal"]["n_pedidos_min"]):
        if r["tendencia_ratio"] < -0.04:
            return "leal_deterioro"
        return "leal"

    # 4. Promiscuo
    if (r["ratio_vs_potential"]   >= RULES["promiscuo"]["ratio_min"]        and
            r["pct_periodos_activos"] >= RULES["promiscuo"]["pct_periodos_min"] and
            r["n_pedidos_12m"]        >= RULES["promiscuo"]["n_pedidos_min"]):
        if r["tendencia_ratio"] < -0.05:
            return "promiscuo_deterioro"
        return "promiscuo"

    return "marginal"


# ── KMeans complementario ─────────────────────────────────────────────────────

def run_kmeans(df: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    X = df[FEATURES_M0].fillna(df[FEATURES_M0].median())
    scaler  = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df = df.copy()
    df["cluster_id"] = km.fit_predict(X_scaled)
    sil = silhouette_score(X_scaled, df["cluster_id"])
    print(f"  [M0] Silhouette score (k={n_clusters}): {sil:.3f}")
    return df


# ── Detección de transiciones ─────────────────────────────────────────────────

def detect_transitions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "label_previo" not in df.columns:
        df["label_previo"]  = None
        df["en_transicion"] = False
        return df
    transiciones = {
        ("leal", "promiscuo"), ("leal", "promiscuo_deterioro"),
        ("promiscuo", "marginal"), ("leal", "leal_deterioro"),
    }
    df["en_transicion"] = df.apply(
        lambda r: (r["label_previo"], r["label_m0"]) in transiciones, axis=1
    )
    return df


# ── Runner principal ──────────────────────────────────────────────────────────

def run(df: pd.DataFrame) -> pd.DataFrame:
    """
    Entrada:  DataFrame con columnas reales del CSV.
    Salida:   DataFrame con clinic_id, familia, label_m0,
              cluster_id, en_transicion.
    """
    print("[M0] Iniciando clasificación de perfil de cliente...")

    df = prepare_features(df)
    df["label_m0"] = df.apply(apply_rules, axis=1)
    df = run_kmeans(df)
    df = detect_transitions(df)

    dist = df["label_m0"].value_counts()
    print("[M0] Distribución de perfiles:")
    for label, count in dist.items():
        print(f"      {label:<25} {count:>5} ({count/len(df)*100:.1f}%)")

    return df[[COL_CLIENT, COL_FAMILIA,
               "label_m0", "cluster_id", "en_transicion"
               ]].rename(columns={COL_CLIENT: "clinic_id",
                                   COL_FAMILIA: "familia"})