"""
m2_fuga_commodity.py
Modelo M2 — Detección de fuga en commodity
CUSUM + z-score sobre ratio_vs_potential y tendencias.

Columnas reales usadas:
  ratio_vs_potential, trend_slope_90d, trend_slope_30d,
  inter_order_avg, inter_order_std, silence_streak,
  Bloque analítico, Familia_H, Id. Cliente,
  es_devolucion, is_promo_period, evento_especial
  label_m0 (de M0)
"""

import unicodedata
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Configuración ─────────────────────────────────────────────────────────────

CUSUM_THRESHOLD           = 2.5
CUSUM_SLACK               = 0.5
ZSCORE_AGUDO_THRESHOLD    = -2.0
SILENCIO_FUGA_MULTIPLIER  = 2.0
VENTANA_CAPTURA_MIN       = 1.0
VENTANA_CAPTURA_MAX       = 2.2

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ascii(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def es_commodity(bloque) -> bool:
    if pd.isna(bloque):
        return True
    return "commodit" in _ascii(str(bloque))


def cusum_score(row: pd.Series) -> float:
    """
    Score CUSUM aproximado sobre features estáticos.
    Negativo = deterioro acumulado.
    """
    dev_ratio       = row["ratio_vs_potential"] - 0.70
    trend_contrib   = row["trend_slope_90d"] * 10
    silence_ratio   = row["silence_streak"] / max(row["inter_order_avg"], 1)
    silence_contrib = -(silence_ratio - 1.0)
    return round(dev_ratio + trend_contrib + silence_contrib, 4)


def zscore_agudo(row: pd.Series) -> float:
    """Z-score de caída aguda usando trend_slope_30d vs. variabilidad histórica."""
    slope = row["trend_slope_30d"]
    if pd.isna(slope):
        return 0.0
    std_proxy = max(row["inter_order_std"] / max(row["inter_order_avg"], 1), 0.01)
    return round(float(slope / std_proxy), 4)


def classify_alert(row: pd.Series) -> dict:
    result = {
        "cusum_score": row["cusum_score"],
        "zscore_30d":  row["zscore_30d"],
        "activa_a2":   False, "motivo_a2": None,
        "activa_a3":   False, "motivo_a3": None,
        "activa_a6":   False, "motivo_a6": None,
    }

    label   = row.get("label_m0", "desconocido")
    familia = row["Familia_H"]
    ratio   = row["ratio_vs_potential"]
    silence = row["silence_streak"]
    ioa     = row["inter_order_avg"]

    # A6: caída aguda (cualquier perfil)
    if row["zscore_30d"] < ZSCORE_AGUDO_THRESHOLD:
        result["activa_a6"] = True
        result["motivo_a6"] = (
            f"Caída aguda en {familia}. Z-score 30d: {row['zscore_30d']:.2f}. "
            f"Slope 30d ({row['trend_slope_30d']:.3f}) muy negativo "
            f"respecto a variabilidad histórica."
        )

    # A2: ventana de captura en promiscuo
    if label in ("promiscuo", "promiscuo_deterioro"):
        silence_rel = silence / max(ioa, 1)
        if (VENTANA_CAPTURA_MIN <= silence_rel <= VENTANA_CAPTURA_MAX
                and ratio < 0.65):
            result["activa_a2"] = True
            result["motivo_a2"] = (
                f"Cliente promiscuo en ventana de captura para {familia}. "
                f"Lleva {silence:.0f} días sin pedir (media: {ioa:.0f} días). "
                f"Ratio captura actual: {ratio*100:.0f}% del potencial."
            )

    # A3: fuga sostenida en leal
    if label in ("leal", "leal_deterioro"):
        deterioro       = row["cusum_score"] < -CUSUM_THRESHOLD
        silencio_exc    = silence > ioa * SILENCIO_FUGA_MULTIPLIER
        tendencia_neg   = row["trend_slope_90d"] < -0.03
        n_señales = sum([deterioro, silencio_exc, tendencia_neg])
        if n_señales >= 2:
            señales_txt = []
            if deterioro:
                señales_txt.append(f"CUSUM ({row['cusum_score']:.2f})")
            if silencio_exc:
                señales_txt.append(
                    f"silencio {silence:.0f}d > {ioa*SILENCIO_FUGA_MULTIPLIER:.0f}d"
                )
            if tendencia_neg:
                señales_txt.append(f"slope 90d ({row['trend_slope_90d']:.3f})")
            result["activa_a3"] = True
            result["motivo_a3"] = (
                f"Fuga sostenida en {familia} (leal). "
                f"Señales: {'; '.join(señales_txt)}. "
                f"Ratio: {ratio*100:.0f}% del potencial."
            )

    return result

# ── Runner ────────────────────────────────────────────────────────────────────

def run(df: pd.DataFrame, label_m0: pd.DataFrame = None) -> pd.DataFrame:
    print("[M2] Iniciando detección de fuga en commodity...")
    df = df.copy()

    if label_m0 is not None:
        df = df.merge(
            label_m0[["Id. Cliente", "familia", "label_m0"]],
            left_on=["Id. Cliente", "Familia_H"],
            right_on=["Id. Cliente", "familia"],
            how="left"
        )
    else:
        df["label_m0"] = "desconocido"

    # Filtrar: commodity, no devoluciones, no eventos especiales, no promo
    mask = (
        df["Bloque analítico"].apply(es_commodity) &
        (df.get("es_devolucion",  pd.Series(0, index=df.index)) == 0) &
        (df.get("evento_especial", pd.Series(0, index=df.index)) == 0) &
        (df["inter_order_avg"] > 0)
    )
    df_c = df[mask].copy()

    if df_c.empty:
        print("  [M2] Sin filas commodity válidas.")
        return pd.DataFrame(columns=["Id. Cliente", "Familia_H",
                                     "cusum_score", "zscore_30d",
                                     "activa_a2", "activa_a3", "activa_a6",
                                     "motivo_a2", "motivo_a3", "motivo_a6"])

    df_c["cusum_score"] = df_c.apply(cusum_score, axis=1)
    df_c["zscore_30d"]  = df_c.apply(zscore_agudo, axis=1)

    alert_df = pd.DataFrame(list(df_c.apply(classify_alert, axis=1)))
    df_c = pd.concat([df_c.reset_index(drop=True),
                      alert_df.reset_index(drop=True)], axis=1)
    df_c = df_c.loc[:, ~df_c.columns.duplicated()]

    print(f"  [M2] A2: {df_c['activa_a2'].sum()} | "
          f"A3: {df_c['activa_a3'].sum()} | "
          f"A6: {df_c['activa_a6'].sum()}")

    return df_c[["Id. Cliente", "Familia_H", "cusum_score", "zscore_30d",
                 "activa_a2", "activa_a3", "activa_a6",
                 "motivo_a2", "motivo_a3", "motivo_a6"]]