"""
m1_reposicion.py
Modelo M1 — Predicción de reposición
Estima días hasta el próximo pedido. Solo commodities.

Columnas reales usadas:
  inter_order_avg, inter_order_std, seasonal_index,
  days_since_last_order, trend_slope_90d, Bloque analítico,
  Familia_H, Id. Cliente, label_m0 (de M0)
"""

import unicodedata
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

try:
    from lifelines import KaplanMeierFitter
    LIFELINES_OK = True
except ImportError:
    LIFELINES_OK = False

# ── Configuración ─────────────────────────────────────────────────────────────

VENTANA_ALERTA_DIAS = 4
PROB_UMBRAL_A1      = 0.60

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ascii(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def es_commodity(bloque) -> bool:
    if pd.isna(bloque):
        return True
    return "commodit" in _ascii(str(bloque))


def estimate_days_to_reorder(row: pd.Series) -> float:
    si = row["seasonal_index"]
    if pd.isna(si) or si <= 0:
        si = 1.0
    base  = row["inter_order_avg"] / max(si, 0.5)
    slope = row.get("trend_slope_90d", 0.0)
    if pd.isna(slope):
        slope = 0.0
    if slope > 0.02:
        base *= 0.90
    elif slope < -0.03:
        base *= 1.10
    return round(base, 1)


def prob_pedido_nd(row: pd.Series, n: int = 7) -> float:
    from scipy.stats import norm
    mu  = row["inter_order_avg"]
    std = row["inter_order_std"]
    if pd.isna(std) or std <= 0:
        std = max(mu * 0.3, 1.0)
    std = max(std, 1.0)
    t0  = row["days_since_last_order"]
    if pd.isna(t0):
        return 0.0
    p   = norm.cdf(t0 + n, loc=mu, scale=std) - norm.cdf(t0, loc=mu, scale=std)
    return round(float(np.clip(p, 0, 1)), 4)


def kaplan_meier_by_segment(df: pd.DataFrame) -> pd.DataFrame:
    if not LIFELINES_OK:
        return df
    print("  [M1] Ajustando Kaplan-Meier por segmento...")
    df = df.copy()
    df["km_median"] = np.nan
    seg_cols = [c for c in ["Provincia", "Familia_H"] if c in df.columns]
    if not seg_cols:
        return df
    for seg, grp in df.groupby(seg_cols):
        if len(grp) < 5:
            continue
        kmf = KaplanMeierFitter()
        durations = grp["inter_order_avg"].clip(lower=1)
        event_obs = (grp["inter_order_avg"] < grp["inter_order_avg"].quantile(0.95)).astype(int)
        try:
            kmf.fit(durations, event_observed=event_obs)
            median = kmf.median_survival_time_
            df.loc[grp.index, "km_median"] = median
        except Exception:
            pass
    mask = df["km_median"].notna() & (df["km_median"] > 0)
    df.loc[mask, "dias_hasta_reposicion"] = (
        df.loc[mask, "km_median"] / df.loc[mask, "seasonal_index"].clip(lower=0.5)
    ).round(1)
    return df


def build_motivo_a1(row: pd.Series) -> str:
    return (
        f"Cliente {row.get('label_m0', '')}. "
        f"Pide {row['Familia_H']} cada {row['inter_order_avg']:.0f} días de media. "
        f"Último pedido hace {row['days_since_last_order']:.0f} días. "
        f"Próximo pedido estimado en {max(0, row['dias_restantes']):.0f} días. "
        f"Prob. pedido 7d: {row['prob_pedido_7d']*100:.0f}%."
    )

# ── Runner ────────────────────────────────────────────────────────────────────

def run(df: pd.DataFrame, label_m0: pd.DataFrame = None) -> pd.DataFrame:
    print("[M1] Iniciando predicción de reposición...")
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

    mask = (
        df["Bloque analítico"].apply(es_commodity) &
        (df.get("es_devolucion", pd.Series(0, index=df.index)) == 0) &
        (df["inter_order_avg"] > 0)
    )
    df_c = df[mask].copy()

    if df_c.empty:
        print("  [M1] Sin filas commodity válidas.")
        return pd.DataFrame(columns=["Id. Cliente", "Familia_H",
                                     "dias_hasta_reposicion", "dias_restantes",
                                     "prob_pedido_7d", "activa_a1", "motivo_a1"])

    df_c["dias_hasta_reposicion"] = df_c.apply(estimate_days_to_reorder, axis=1)
    df_c = kaplan_meier_by_segment(df_c)
    df_c["dias_restantes"] = (
        df_c["dias_hasta_reposicion"] - df_c["days_since_last_order"]
    ).round(1)
    df_c["prob_pedido_7d"] = df_c.apply(prob_pedido_nd, axis=1)

    df_c["activa_a1"] = (
        (df_c["label_m0"].isin(["leal", "promiscuo"])) &
        (df_c["dias_restantes"] <= VENTANA_ALERTA_DIAS) &
        (df_c["dias_restantes"] >= -5) &
        (df_c["prob_pedido_7d"] >= PROB_UMBRAL_A1)
    )
    df_c["motivo_a1"] = df_c.apply(
        lambda r: build_motivo_a1(r) if r["activa_a1"] else None, axis=1
    )

    print(f"  [M1] Alertas A1 generadas: {df_c['activa_a1'].sum()}")
    return df_c[["Id. Cliente", "Familia_H", "dias_hasta_reposicion",
                 "dias_restantes", "prob_pedido_7d", "activa_a1", "motivo_a1"]]