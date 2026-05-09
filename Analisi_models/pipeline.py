"""
pipeline.py — Smart Demand Signals
Orquesta M0 → M1 → M2 → M3 con las columnas reales del CSV.

Columnas esperadas en el CSV de entrada:
  Fecha, Id. Cliente, Provincia, Familia_H, Bloque analítico,
  Valores_H, es_devolucion, es_pedido, is_promo_period,
  evento_especial, historico_incompleto, ref_date,
  days_since_last_order, inter_order_avg, inter_order_std,
  ratio_vs_potential, trend_slope_90d, trend_slope_30d,
  seasonal_index, pct_families_active, silence_streak,
  reactivation_signal

Uso:
  python pipeline.py --input data/features.csv --output output/alertas.csv
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Models import m0_perfil_cliente, m1_reposicion, m2_fuga_commodity, m3_fuga_tecnico

# ── Canal y urgencia por tipo de alerta ──────────────────────────────────────

CANAL_MAP = {
    "A1": "Televendedor",
    "A2": "Delegado",
    "A3": "Delegado",
    "A4": "Delegado",
    "A5": "Marketing_Auto",
    "A6": "Delegado_Urgente",
    "A7": "Televendedor",
    "A8": "Delegado",
    "A9": "Delegado",
}

URGENCIA_MAP = {
    "A1": 1.0,
    "A2": 1.2,
    "A3": 1.5,
    "A4": 1.5,
    "A5": 0.7,
    "A6": 2.0,
    "A7": 0.9,
    "A8": 1.3,
    "A9": 1.4,
}

# ── Columnas obligatorias ─────────────────────────────────────────────────────

REQUIRED_COLS = [
    "Id. Cliente", "Familia_H", "Bloque analítico",
    "days_since_last_order", "inter_order_avg", "inter_order_std",
    "ratio_vs_potential", "trend_slope_90d", "trend_slope_30d",
    "seasonal_index", "pct_families_active", "silence_streak",
]

# ── Carga y validación ────────────────────────────────────────────────────────

def load_features(path: str) -> pd.DataFrame:
    print(f"[Pipeline] Cargando: {path}")

    # Leer solo columnas necesarias para ahorrar memoria
    all_cols = REQUIRED_COLS + [
        "Fecha", "Provincia", "Valores_H",
        "es_devolucion", "es_pedido", "is_promo_period",
        "evento_especial", "historico_incompleto",
        "ref_date", "reactivation_signal",
    ]

    # Detectar qué columnas existen realmente
    header = pd.read_csv(path, nrows=0).columns.tolist()
    cols_to_read = [c for c in all_cols if c in header]
    missing_req  = [c for c in REQUIRED_COLS if c not in header]
    if missing_req:
        raise ValueError(f"Columnas obligatorias ausentes: {missing_req}")

    df = pd.read_csv(path, usecols=cols_to_read, low_memory=False)
    print(f"  Filas: {len(df):,} | Columnas leídas: {len(df.columns)}")

    # Validaciones básicas — clip outliers extremos (>2 = compra 200% del potencial estimado)
    if df["ratio_vs_potential"].max() > 2.0:
        n_outliers = (df["ratio_vs_potential"] > 2.0).sum()
        print(f"  AVISO: {n_outliers} filas con ratio_vs_potential > 2.0, recortando a 2.0")
        df["ratio_vs_potential"] = df["ratio_vs_potential"].clip(upper=2.0)

    if "Valores_H" in df.columns:
        df["fam_potential"] = df["Valores_H"].clip(lower=0)
    else:
        df["fam_potential"] = 1000.0   # fallback neutro

    # Nulos en columnas críticas
    antes = len(df)
    df = df.dropna(subset=["Id. Cliente", "Familia_H",
                            "inter_order_avg", "ratio_vs_potential"])
    if len(df) < antes:
        print(f"  Filas eliminadas por nulos críticos: {antes - len(df)}")

    # inter_order_avg nunca puede ser 0
    df = df[df["inter_order_avg"] > 0].copy()

    # Deduplicate: one current-state snapshot per (client × familia).
    # The features CSV has one row per original transaction with aggregated
    # features broadcast across rows. Models need exactly one row per pair.
    # Sort by Fecha so we keep the most-recent transaction's flags.
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.sort_values("Fecha")
    antes_dedup = len(df)
    df = df.drop_duplicates(subset=["Id. Cliente", "Familia_H"], keep="last").copy()
    print(f"  Pares unicos (cliente x familia): {len(df):,}  "
          f"(eliminadas {antes_dedup - len(df):,} filas duplicadas)")

    print(f"  Filas validas para modelado: {len(df):,}")
    return df


# ── Construcción de alertas unificadas ───────────────────────────────────────

def build_alert_row(client_id, familia, tipo_alerta, motivo,
                    fam_potential, ratio_vs_potential,
                    dias_restantes=None, label_m0=None, extra=None) -> dict:
    impacto = round(fam_potential * ratio_vs_potential * 0.25, 2)
    urgencia_factor = URGENCIA_MAP.get(tipo_alerta, 1.0)
    urgencia_temporal = 1.0 / max(dias_restantes, 1) if dias_restantes and dias_restantes > 0 else 1.5
    score = round(impacto * urgencia_temporal * urgencia_factor, 4)

    row = {
        "fecha_alerta":     str(date.today()),
        "client_id":        client_id,
        "familia":          familia,
        "tipo_alerta":      tipo_alerta,
        "label_m0":         label_m0,
        "canal":            CANAL_MAP.get(tipo_alerta, "Delegado"),
        "motivo":           motivo,
        "impacto_estimado": impacto,
        "score_prioridad":  score,
        "dias_restantes":   dias_restantes,
        "estado":           "pendiente",
    }
    if extra:
        row.update(extra)
    return row


def collect_alerts(df, out_m0, out_m1, out_m2, out_m3) -> pd.DataFrame:
    alerts = []

    # Lookups
    base = df[["Id. Cliente", "Familia_H", "fam_potential",
                "ratio_vs_potential"]].drop_duplicates(
                    subset=["Id. Cliente", "Familia_H"])
    label_lkp  = out_m0.set_index(["clinic_id", "familia"])["label_m0"].to_dict()
    pot_lkp    = base.set_index(["Id. Cliente", "Familia_H"])["fam_potential"].to_dict()
    ratio_lkp  = base.set_index(["Id. Cliente", "Familia_H"])["ratio_vs_potential"].to_dict()

    def glabel(cid, fam):  return label_lkp.get((cid, fam), "desconocido")
    def gpot(cid, fam):    return pot_lkp.get((cid, fam), 1000.0)
    def gratio(cid, fam):  return ratio_lkp.get((cid, fam), 0.5)

    # A1
    for _, r in out_m1[out_m1["activa_a1"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A1", r["motivo_a1"],
            gpot(cid, fam), gratio(cid, fam),
            dias_restantes=r["dias_restantes"],
            label_m0=glabel(cid, fam),
            extra={"prob_pedido_7d": r["prob_pedido_7d"]},
        ))

    # A2
    for _, r in out_m2[out_m2["activa_a2"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A2", r["motivo_a2"],
            gpot(cid, fam), gratio(cid, fam),
            label_m0=glabel(cid, fam),
            extra={"cusum_score": r["cusum_score"]},
        ))

    # A3
    for _, r in out_m2[out_m2["activa_a3"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A3", r["motivo_a3"],
            gpot(cid, fam), gratio(cid, fam),
            label_m0=glabel(cid, fam),
            extra={"cusum_score": r["cusum_score"]},
        ))

    # A4
    for _, r in out_m3[out_m3["activa_a4"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A4", r["motivo_a4"],
            gpot(cid, fam), gratio(cid, fam),
            label_m0=glabel(cid, fam),
            extra={"anomaly_score": r["anomaly_score"],
                   "anomaly_type":  r["anomaly_type"]},
        ))

    # A5
    for _, r in out_m3[out_m3["activa_a5"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A5", r["motivo_a5"],
            gpot(cid, fam), gratio(cid, fam),
            label_m0=glabel(cid, fam),
        ))

    # A6
    for _, r in out_m2[out_m2["activa_a6"]].iterrows():
        cid, fam = r["Id. Cliente"], r["Familia_H"]
        alerts.append(build_alert_row(
            cid, fam, "A6", r["motivo_a6"],
            gpot(cid, fam), gratio(cid, fam),
            label_m0=glabel(cid, fam),
            extra={"zscore_30d": r["zscore_30d"]},
        ))

    if not alerts:
        return pd.DataFrame()

    df_a = pd.DataFrame(alerts).sort_values("score_prioridad", ascending=False)
    df_a.insert(0, "rank", range(1, len(df_a) + 1))
    return df_a


# ── Resumen ejecutivo ─────────────────────────────────────────────────────────

def print_summary(df_alerts, out_m0):
    sep = "=" * 55
    print("\n" + sep)
    print("  RESUMEN -- Smart Demand Signals")
    print(sep)
    print("\nPerfiles M0:")
    for label, cnt in out_m0["label_m0"].value_counts().items():
        print(f"   {label:<25} {cnt:>6}")

    if df_alerts.empty:
        print("\n  Sin alertas generadas.")
        return

    print(f"\nAlertas generadas: {len(df_alerts)}")
    for tipo, grp in df_alerts.groupby("tipo_alerta"):
        print(f"   {tipo}  {len(grp):>5} alertas  -> {grp['canal'].iloc[0]}")

    print(f"\nImpacto estimado total: "
          f"{df_alerts['impacto_estimado'].sum():,.0f} EUR")

    print(f"\nTop 5 por prioridad:")
    cols = ["rank", "client_id", "familia", "tipo_alerta",
            "canal", "impacto_estimado", "score_prioridad"]
    print(df_alerts[cols].head(5).to_string(index=False))
    print("\n" + sep)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(input_path: str, output_path: str):
    df = load_features(input_path)

    out_m0 = m0_perfil_cliente.run(df)
    out_m1 = m1_reposicion.run(df, label_m0=out_m0)
    out_m2 = m2_fuga_commodity.run(df, label_m0=out_m0)
    out_m3 = m3_fuga_tecnico.run(df, label_m0=out_m0)

    print("\n[Pipeline] Construyendo alertas...")
    df_alerts = collect_alerts(df, out_m0, out_m1, out_m2, out_m3)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_alerts.to_csv(output_path, index=False)
    print(f"[Pipeline] Alertas -> {output_path}")

    m0_path = output_path.replace("alertas", "perfiles_m0")
    out_m0.to_csv(m0_path, index=False)
    print(f"[Pipeline] Perfiles M0 -> {m0_path}")

    print_summary(df_alerts, out_m0)
    return df_alerts, out_m0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default="../Data/finalCSV/features_v2.csv")
    parser.add_argument("--output", default="output/alertas.csv")
    args = parser.parse_args()
    main(args.input, args.output)