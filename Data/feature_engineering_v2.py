"""
feature_engineering.py
=======================
Calcula features de Capa 3 por (cliente × familia de producto) a partir
de un CSV con el siguiente esquema mínimo esperado:

    Fecha               | fecha del pedido (ISO 8601)
    Id. Cliente         | identificador numérico del cliente
    Familia_H           | familia de producto
    Valores_H           | volumen/importe del pedido
    ratio_vs_potential  | volumen comprado / potencial estimado (puede venir en el CSV
                          o calcularse externamente; si no existe se deja NaN)
    is_promo_period     | flag binario (opcional)
    evento_especial     | flag binario (opcional)
    historico_incompleto| flag binario (opcional)

Columnas adicionales (Provincia, Bloque analítico, …) se ignoran pero
se conservan en la salida si el usuario lo desea.

Uso:
    python feature_engineering.py --input datos.csv --output features.csv
    python feature_engineering.py --input datos.csv --output features.csv --ref-date 2024-06-01

Dependencias: pandas, numpy, scikit-learn (solo para regresión lineal)
"""

import argparse
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _linreg_slope(series: pd.Series) -> float:
    """Pendiente de una regresión lineal (y = volumen, x = días ordinales)."""
    s = series.dropna()
    if len(s) < 2:
        return np.nan
    x = np.arange(len(s)).reshape(-1, 1)
    y = s.values
    return LinearRegression().fit(x, y).coef_[0]


def _inter_order_stats(dates: pd.Series):
    """Devuelve (media, std) de los intervalos entre pedidos, en días."""
    sorted_dates = dates.sort_values()
    deltas = sorted_dates.diff().dt.days.dropna()
    if len(deltas) == 0:
        return np.nan, np.nan
    return deltas.mean(), deltas.std()


# ---------------------------------------------------------------------------
# Core feature calculation
# ---------------------------------------------------------------------------

def compute_features(df: pd.DataFrame, ref_date: pd.Timestamp) -> pd.DataFrame:
    """
    Dado el DataFrame de pedidos históricos y una fecha de referencia,
    devuelve un DataFrame con una fila por (Id. Cliente, Familia_H) y todas
    las features calculadas.
    """

    df = df.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"])

    results = []

    for (cliente, familia), grp in df.groupby(["Id. Cliente", "Familia_H"]):
        grp = grp.sort_values("Fecha")

        # Pedidos válidos (Valores_H > 0)
        pedidos = grp[grp["Valores_H"] > 0]

        # ── days_since_last_order ────────────────────────────────────────────
        if len(pedidos) > 0:
            last_order_date = pedidos["Fecha"].max()
            days_since_last_order = (ref_date - last_order_date).days
        else:
            last_order_date = pd.NaT
            days_since_last_order = np.nan

        # ── inter_order_avg / inter_order_std (últimos 12 meses) ────────────
        cutoff_12m = ref_date - pd.DateOffset(months=12)
        pedidos_12m = pedidos[pedidos["Fecha"] >= cutoff_12m]
        inter_avg, inter_std = _inter_order_stats(pedidos_12m["Fecha"])

        # ── ratio_vs_potential ───────────────────────────────────────────────
        if "ratio_vs_potential" in grp.columns:
            ratio_vs_potential = (
                pedidos.sort_values("Fecha")["ratio_vs_potential"].iloc[-1]
                if len(pedidos) > 0 else np.nan
            )
        else:
            ratio_vs_potential = np.nan

        # ── trend_slope_90d ──────────────────────────────────────────────────
        cutoff_90d = ref_date - pd.Timedelta(days=90)
        pedidos_90d = pedidos[pedidos["Fecha"] >= cutoff_90d]["Valores_H"]
        trend_slope_90d = _linreg_slope(pedidos_90d)

        # ── trend_slope_30d ──────────────────────────────────────────────────
        cutoff_30d = ref_date - pd.Timedelta(days=30)
        pedidos_30d = pedidos[pedidos["Fecha"] >= cutoff_30d]["Valores_H"]
        trend_slope_30d = _linreg_slope(pedidos_30d)

        # ── seasonal_index ───────────────────────────────────────────────────
        current_month = ref_date.month
        pedidos["_month"] = pedidos["Fecha"].dt.month
        monthly_means = pedidos.groupby("_month")["Valores_H"].mean()
        global_mean = pedidos["Valores_H"].mean()
        if current_month in monthly_means.index and not np.isnan(global_mean) and global_mean != 0:
            seasonal_index = monthly_means[current_month] / global_mean
        else:
            seasonal_index = np.nan

        # ── pct_families_active ──────────────────────────────────────────────
        cliente_grp = df[(df["Id. Cliente"] == cliente) & (df["Valores_H"] > 0)]
        total_familias = cliente_grp["Familia_H"].nunique()
        familias_activas = (
            cliente_grp[cliente_grp["Fecha"] >= cutoff_90d]["Familia_H"].nunique()
        )
        pct_families_active = (
            familias_activas / total_familias if total_familias > 0 else np.nan
        )

        # ── silence_streak ───────────────────────────────────────────────────
        silence_streak = days_since_last_order if not np.isnan(days_since_last_order) else np.nan

        # ── reactivation_signal ──────────────────────────────────────────────
        reactivation_signal = 0
        if len(pedidos) >= 3 and not np.isnan(inter_avg) and inter_avg > 0:
            p25 = pedidos["Valores_H"].quantile(0.25)
            last_pedido = pedidos.sort_values("Fecha").iloc[-1]
            prev_pedidos = pedidos[pedidos["Fecha"] < last_pedido["Fecha"]]
            if len(prev_pedidos) > 0:
                prev_last = prev_pedidos["Fecha"].max()
                gap_before = (last_pedido["Fecha"] - prev_last).days
                if gap_before > 2 * inter_avg and last_pedido["Valores_H"] < p25:
                    reactivation_signal = 1

        # ── Assemblar fila ───────────────────────────────────────────────────
        results.append({
            "Id. Cliente": cliente,
            "Familia_H": familia,
            "ref_date": ref_date.date(),
            "days_since_last_order": days_since_last_order,
            "inter_order_avg": round(inter_avg, 2) if not np.isnan(inter_avg) else np.nan,
            "inter_order_std": round(inter_std, 2) if not np.isnan(inter_std) else np.nan,
            "ratio_vs_potential": ratio_vs_potential,
            "trend_slope_90d": round(trend_slope_90d, 4) if not np.isnan(trend_slope_90d) else np.nan,
            "trend_slope_30d": round(trend_slope_30d, 4) if not np.isnan(trend_slope_30d) else np.nan,
            "seasonal_index": round(seasonal_index, 4) if not np.isnan(seasonal_index) else np.nan,
            "pct_families_active": round(pct_families_active, 4) if not np.isnan(pct_families_active) else np.nan,
            "silence_streak": silence_streak,
            "reactivation_signal": reactivation_signal,
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Feature engineering Capa 3 — genera features por cliente × familia."
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Ruta al CSV de entrada (pedidos históricos).")
    parser.add_argument("--output", "-o", default="features_output.csv",
                        help="Ruta del CSV de salida (por defecto: features_output.csv).")
    parser.add_argument("--ref-date", default=None,
                        help="Fecha de referencia YYYY-MM-DD. Por defecto: última fecha del CSV.")
    parser.add_argument("--sep", default=",",
                        help="Separador de columnas del CSV (por defecto: coma).")
    return parser.parse_args()


def main():
    args = parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"No se encuentra el fichero: {input_path}")

    print(f"[INFO] Leyendo {input_path} …")
    df = pd.read_csv(input_path, sep=args.sep)

    required_cols = {"Fecha", "Id. Cliente", "Familia_H", "Valores_H"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"El CSV no tiene las columnas requeridas: {missing}\n"
            f"Columnas detectadas: {list(df.columns)}"
        )

    if args.ref_date:
        ref_date = pd.Timestamp(args.ref_date)
        date_source = "(--ref-date)"
    else:
        ref_date = pd.to_datetime(df["Fecha"]).max()
        date_source = "(latest date in CSV)"
    print(f"[INFO] Fecha de referencia: {ref_date.date()} {date_source}")

    print(f"[INFO] Procesando {len(df)} filas, "
          f"{df['Id. Cliente'].nunique()} clientes, "
          f"{df['Familia_H'].nunique()} familias …")

    features_df = compute_features(df, ref_date)

    feature_cols = [c for c in features_df.columns if c not in ("Id. Cliente", "Familia_H")]
    df = df.drop(columns=[c for c in feature_cols if c in df.columns], errors="ignore")
    output_df = df.merge(features_df, on=["Id. Cliente", "Familia_H"], how="left")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False)
    print(f"[OK] CSV enriquecido guardado en: {output_path}  ({len(output_df)} filas, {len(output_df.columns)} columnas)")
    print()
    print(output_df.to_string(index=False))


if __name__ == "__main__":
    main()
