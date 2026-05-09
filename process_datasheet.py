#!/usr/bin/env python3
"""
xlsx_to_csv.py — Convertimos un .xlsx a ficheros CSV.

Uso:
    python xlsx_to_csv.py <archivo.xlsx> [directorio_salida]
                         [-s SEPARADOR] [-e ENCODING] [-n]
"""

import argparse
import os
import re
import subprocess
import sys


def check_dependencies():
    missing = []
    for lib in ("pandas", "openpyxl"):
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)

    if not missing:
        return

    print(f"[AVISO] Faltan dependencias: {', '.join(missing)}")
    answer = input("¿Instalarlas ahora con pip? [s/N] ").strip().lower()
    if answer == "s":
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)
        print("[OK] Dependencias instaladas.\n")
    else:
        print(f"[ERROR] Instálalas manualmente: pip install {' '.join(missing)}")
        sys.exit(1)


def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[^\w\s-]", "_", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]


def convert(xlsx_path: str, output_dir: str, separator: str, encoding: str, skip_empty: bool):
    import pandas as pd

    try:
        sheets = pd.read_excel(xlsx_path, sheet_name=None, header=0, dtype=str)
    except Exception as e:
        print(f"[ERROR] No se pudo leer el archivo: {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    total = len(sheets)
    saved = skipped = 0

    print(f"\n{'─' * 55}")
    print(f"  Archivo : {xlsx_path}")
    print(f"  Hojas   : {total}")
    print(f"  Salida  : {output_dir}/")
    print(f"  Sep.    : '{separator}'   Encoding: {encoding}")
    print(f"{'─' * 55}\n")

    for sheet_name, df in sheets.items():
        rows, cols = df.shape

        if skip_empty and df.dropna(how="all").empty:
            print(f"  [OMITIDA]  '{sheet_name}'  ({rows} filas, {cols} cols) — vacía")
            skipped += 1
            continue

        df = df.dropna(how="all").reset_index(drop=True)
        csv_name = safe_filename(sheet_name) + ".csv"
        csv_path = os.path.join(output_dir, csv_name)

        df.to_csv(csv_path, sep=separator, index=False, encoding=encoding, errors="replace")
        saved += 1
        print(f"  [OK]  '{sheet_name}'  →  {csv_name}  ({len(df)} filas, {cols} cols)")

    print(f"\n{'─' * 55}")
    print(f"  Guardados : {saved}   Omitidos : {skipped}   Total : {total}")
    print(f"  Carpeta   : {os.path.abspath(output_dir)}/")
    print(f"{'─' * 55}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte un .xlsx con múltiples hojas a ficheros CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("xlsx", help="Ruta al fichero Excel de origen")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Carpeta de salida (por defecto: nombre del xlsx sin extensión)",
    )
    parser.add_argument("-s", "--separator", default=",", help="Separador CSV (por defecto: ',')")
    parser.add_argument("-e", "--encoding", default="utf-8", help="Encoding de salida (por defecto: utf-8)")
    parser.add_argument("-n", "--skip-empty", action="store_true", help="Omitir hojas vacías")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.xlsx):
        print(f"[ERROR] Archivo no encontrado: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or os.path.splitext(os.path.basename(args.xlsx))[0]

    check_dependencies()
    convert(args.xlsx, output_dir, args.separator, args.encoding, args.skip_empty)


if __name__ == "__main__":
    main()
