"""
filter_alerts.py — Keep only alerts backed by order data from the last year,
                   then push them straight to the Django backend.

Reads alertas.csv produced by pipeline.py, drops rows whose last_order_date
falls outside the trailing 365-day window, writes the filtered CSV, and
imports it into the database automatically.

Usage:
  python filter_alerts.py --input output/alertas.csv --output output/alertas_filtered.csv
  python filter_alerts.py --input output/alertas.csv --output output/alertas_filtered.csv --days 180
  python filter_alerts.py --input output/alertas.csv --output output/alertas_filtered.csv --ref-date 2025-12-31
"""

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


DATE_COL   = "last_order_date"
SCORE_COL  = "score_prioridad"
TYPE_COL   = "tipo_alerta"
IMPACT_COL = "impacto_estimado"

# Path to the Django backend relative to this file
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def parse_args():
    p = argparse.ArgumentParser(
        description="Filter alert CSV to the last N days of order data and push to the backend.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input",  "-i", required=True,
                   help="Path to alertas.csv produced by pipeline.py")
    p.add_argument("--output", "-o", required=True,
                   help="Destination path for the filtered CSV")
    p.add_argument("--days", type=int, default=365, metavar="N",
                   help="Trailing window in days (default: 365)")
    p.add_argument("--ref-date", metavar="YYYY-MM-DD", default=None,
                   help="Anchor date for the window (default: today)")
    p.add_argument("--no-push", action="store_true",
                   help="Write the filtered CSV but skip the backend import")
    return p.parse_args()


def load(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        sys.exit(f"[filter] ERROR: file not found: {path}")
    except Exception as exc:
        sys.exit(f"[filter] ERROR reading CSV: {exc}")

    if TYPE_COL not in df.columns:
        sys.exit(f"[filter] ERROR: '{TYPE_COL}' column not found — is this a pipeline alertas.csv?")
    if DATE_COL not in df.columns:
        sys.exit(f"[filter] ERROR: '{DATE_COL}' column not found — re-run the pipeline to regenerate the CSV.")

    print(f"[filter] Loaded {len(df):,} alerts from {path}")
    return df


def apply_date_filter(df: pd.DataFrame, days: int, ref_date_str: str | None) -> pd.DataFrame:
    df = df.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")

    n_missing = df[DATE_COL].isna().sum()
    if n_missing:
        print(f"[filter] WARNING: {n_missing} rows have no last_order_date and will be excluded.")

    df = df[df[DATE_COL].notna()]

    if ref_date_str:
        try:
            ref = pd.Timestamp(ref_date_str)
        except Exception:
            sys.exit(f"[filter] ERROR: invalid --ref-date '{ref_date_str}'. Use YYYY-MM-DD.")
    else:
        ref = pd.Timestamp(date.today())

    cutoff = ref - timedelta(days=days)

    print(f"[filter] Reference date : {ref.date()}")
    print(f"[filter] Cutoff date    : {cutoff.date()}  (last {days} days)")

    before = len(df)
    df = df[df[DATE_COL] >= cutoff]
    print(f"[filter] Date filter    : {before:,} -> {len(df):,} alerts kept")

    return df


def print_summary(df: pd.DataFrame):
    if df.empty:
        print("[filter] WARNING: filtered output is empty.")
        return

    print(f"\n[filter] Result - {len(df):,} alerts:")
    for tipo, grp in df.groupby(TYPE_COL, sort=True):
        impact = grp[IMPACT_COL].sum() if IMPACT_COL in df.columns else 0
        print(f"  {tipo}  {len(grp):>5}  impact {impact:>12,.0f} EUR")

    total_impact = df[IMPACT_COL].sum() if IMPACT_COL in df.columns else 0
    print(f"  TOTAL  {len(df):>5}  impact {total_impact:>12,.0f} EUR")


def push_to_backend(alerts_csv_path: str):
    if not BACKEND_DIR.exists():
        sys.exit(f"[filter] ERROR: backend directory not found at {BACKEND_DIR}")

    abs_csv = str(Path(alerts_csv_path).resolve())

    print(f"\n[filter] Pushing to backend ({BACKEND_DIR})...")
    result = subprocess.run(
        ["uv", "run", "python", "manage.py", "import_alerts",
         "--alerts-csv", abs_csv, "--clear"],
        cwd=str(BACKEND_DIR),
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"[filter] ERROR: backend import failed (exit code {result.returncode})")


def main():
    args = parse_args()
    df = load(args.input)
    df = apply_date_filter(df, args.days, args.ref_date)
    print_summary(df)

    df = df.sort_values(SCORE_COL, ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    df.to_csv(args.output, index=False)
    print(f"\n[filter] Written {len(df):,} alerts -> {args.output}")

    if args.no_push:
        print("[filter] Skipping backend import (--no-push).")
        print(f"[filter] Import manually with:")
        print(f"  cd backend && uv run python manage.py import_alerts --alerts-csv ../{args.output} --clear")
    else:
        push_to_backend(args.output)


if __name__ == "__main__":
    main()
