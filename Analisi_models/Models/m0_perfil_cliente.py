"""
m0_perfil_cliente.py
Modelo M0 — Clasificación de perfil de cliente × familia
Leal / Promiscuo  (dos segmentos, reglas diferenciadas por bloque analítico)

Columnas reales del CSV:
  Id. Cliente, Familia_H, Bloque analítico,
  ratio_vs_potential, inter_order_avg, inter_order_std,
  trend_slope_90d, silence_streak, pct_families_active,
  reactivation_signal, es_devolucion, es_pedido

Features derivados que calcula este módulo:
  coef_variacion       = inter_order_std / inter_order_avg
  regularidad_pedidos  = 1 − clip(coef_variacion, 0, 1)
      Mide si las transacciones forman un patrón periódico:
      1.0 = pedidos a intervalos perfectamente fijos,
      0.0 = intervalos completamente aleatorios.
      Reemplaza n_pedidos_12m (que solo medía frecuencia).
  tendencia_ratio      = trend_slope_90d  (proxy directo)
  pct_periodos_activos = 1 − (silence_streak / (inter_order_avg × 12))
      Qué fracción del ciclo anual estimado del cliente NO está
      cubierta por el silencio actual. Alto = compró recientemente
      respecto a su ritmo; bajo = lleva demasiado tiempo sin pedir.
  n_pedidos_12m        = 365 / inter_order_avg  (solo para KMeans)
"""

import unicodedata
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import warnings
warnings.filterwarnings("ignore")


# ── Columnas de entrada esperadas (nombres reales del CSV) ────────────────────

COL_CLIENT  = "Id. Cliente"
COL_FAMILIA = "Familia_H"
COL_BLOQUE  = "Bloque analítico"

# ── Features usados por M0 (todos calculados en prepare_features) ─────────────

FEATURES_M0 = [
    "ratio_vs_potential",
    "coef_variacion",
    "regularidad_pedidos",
    "pct_periodos_activos",
    "tendencia_ratio",
    "n_pedidos_12m",
    "silence_streak",
]

# ── Reglas por bloque analítico ───────────────────────────────────────────────
#
# COMMODITY — consumibles (guantes, jeringuillas, materiales de uso frecuente):
#   ciclos de reposición cortos y predecibles → umbrales estrictos de
#   regularidad y actividad continua.
#
# TECNICO — productos de proyecto (implantes, ortodoncia, cirugía):
#   compras puntuales ligadas a carga de pacientes → se tolera mayor
#   variabilidad en los intervalos y más silencio entre pedidos.

RULES_COMMODITY = {
    "leal": {
        "ratio_vs_potential_min": 0.70,   # ≥70 % del potencial consumido
        "coef_variacion_max":     0.15,   # intervalos no demasiado irregulares
        "pct_periodos_min":       0.75,   # activo en ≥75 % de su ciclo anual
        "regularidad_min":        0.60,   # score de periodicidad ≥ 0.60
    }
}

RULES_TECNICO = {
    "leal": {
        "ratio_vs_potential_min": 0.50,   # umbral más bajo (compras bulto)
        "coef_variacion_max":     0.30,   # mayor variabilidad es normal
        "pct_periodos_min":       0.40,   # silencio entre proyectos es esperable
        "regularidad_min":        0.30,   # periodicidad menos exigida
    }
}

# ── Helper de bloque ──────────────────────────────────────────────────────────

def _ascii(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def _es_commodity(bloque) -> bool:
    if pd.isna(bloque):
        return True
    return "commodit" in _ascii(str(bloque))


def _rules_for(bloque) -> dict:
    return RULES_COMMODITY if _es_commodity(bloque) else RULES_TECNICO

# ── Preparación de features derivados ────────────────────────────────────────

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["coef_variacion"] = (
        df["inter_order_std"] / df["inter_order_avg"].replace(0, np.nan)
    ).fillna(1.0).clip(upper=3.0)

    # Periodicidad: 1.0 = intervalos perfectamente fijos, 0.0 = completamente aleatorios
    df["regularidad_pedidos"] = (1.0 - df["coef_variacion"].clip(0, 1)).round(4)

    df["tendencia_ratio"] = df["trend_slope_90d"].fillna(0.0)

    df["pct_periodos_activos"] = (
        1.0 - (df["silence_streak"] / (df["inter_order_avg"].replace(0, np.nan) * 12))
    ).clip(lower=0.0, upper=1.0).fillna(0.5)

    df["n_pedidos_12m"] = (
        365.0 / df["inter_order_avg"].replace(0, np.nan)
    ).fillna(1.0).clip(lower=0, upper=120).round().astype(int)

    return df


# ── Reglas de negocio ─────────────────────────────────────────────────────────

def apply_rules(row: pd.Series, rules: dict) -> str:
    r = row
    leal = rules["leal"]
    if (r["ratio_vs_potential"]   >= leal["ratio_vs_potential_min"] or
            r["regularidad_pedidos"]  >= leal["regularidad_min"]):
        return "leal"
    return "promiscuo"


# ── KMeans complementario ─────────────────────────────────────────────────────

def run_kmeans(df: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    X = df[FEATURES_M0].fillna(df[FEATURES_M0].median())
    scaler   = StandardScaler()
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
        ("leal", "promiscuo"),
        ("promiscuo", "leal"),
    }
    df["en_transicion"] = df.apply(
        lambda r: (r["label_previo"], r["label_m0"]) in transiciones, axis=1
    )
    return df


# ── Runner principal ──────────────────────────────────────────────────────────

def run(df: pd.DataFrame) -> pd.DataFrame:
    """
    Entrada:  DataFrame con columnas reales del CSV.
    Salida:   DataFrame con Id. Cliente, familia, label_m0,
              cluster_id, en_transicion.
    """
    print("[M0] Iniciando clasificación de perfil de cliente...")

    df = prepare_features(df)

    # Apply commodity vs. technical rules per row
    df["label_m0"] = df.apply(
        lambda r: apply_rules(r, _rules_for(r.get(COL_BLOQUE))), axis=1
    )

    df = run_kmeans(df)
    df = detect_transitions(df)

    dist = df["label_m0"].value_counts()
    print("[M0] Distribución de perfiles:")
    for label, count in dist.items():
        print(f"      {label:<25} {count:>5} ({count/len(df)*100:.1f}%)")

    # Print split by bloque for visibility
    if COL_BLOQUE in df.columns:
        print("[M0] Distribución por bloque:")
        for bloque, grp in df.groupby(COL_BLOQUE):
            for label, cnt in grp["label_m0"].value_counts().items():
                print(f"      {str(bloque):<30} {label:<12} {cnt:>5}")

    return df[[COL_CLIENT, COL_FAMILIA,
               "label_m0", "cluster_id", "en_transicion"
               ]].rename(columns={COL_CLIENT: "Id. Cliente",
                                   COL_FAMILIA: "familia"})
