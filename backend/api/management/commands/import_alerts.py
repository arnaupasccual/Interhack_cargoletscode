"""
management/commands/import_alerts.py

Two modes of operation:

  Mode A — run pipeline then import (end-to-end):
    python manage.py import_alerts --features-csv path/to/features_v2.csv [--clear]

  Mode B — import from a pre-filtered alerts CSV (pipeline already ran):
    python manage.py import_alerts --alerts-csv path/to/alertas_filtered.csv [--clear]

  Typical three-step workflow:
    python ../Analisi_models/pipeline.py --input features_v2.csv --output alertas.csv
    python ../Analisi_models/filter_alerts.py --input alertas.csv --output alertas_filtered.csv --tipo A1 A2
    python manage.py import_alerts --alerts-csv ../Analisi_models/output/alertas_filtered.csv --clear

Options:
    --features-csv   Path to the features CSV (triggers pipeline run)
    --alerts-csv     Path to an alertas CSV already produced by pipeline.py / filter_alerts.py
    --clear          Delete all existing OPEN alerts before importing (default: False)
    --dry-run        Print what would be imported without touching the DB
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Alert, Client


# ── Mappings from pipeline output to Django model choices ────────────────────

ALERT_TYPE_MAP = {
    "A1": Alert.AlertType.A1_REPLENISHMENT,
    "A2": Alert.AlertType.A2_CAPTURE,
    "A3": Alert.AlertType.A3_COMMODITY_CHURN,
    "A4": Alert.AlertType.A4_TECHNICAL_RISK,
    "A5": Alert.AlertType.A5_REACTIVATION,
    "A6": Alert.AlertType.A6_SUDDEN_DROP,
}

PRIORITY_MAP = {
    "A6": Alert.Priority.CRITICAL,
    "A3": Alert.Priority.HIGH,
    "A2": Alert.Priority.MEDIUM,
    "A4": Alert.Priority.MEDIUM,
    "A1": Alert.Priority.LOW,
    "A5": Alert.Priority.LOW,
}

CHANNEL_MAP = {
    "Delegado":          Alert.RecommendedChannel.SALES_REP,
    "Delegado_Urgente":  Alert.RecommendedChannel.SALES_REP,
    "Televendedor":      Alert.RecommendedChannel.TELEMARKETER,
    "Marketing_Auto":    Alert.RecommendedChannel.MARKETING_AUTO,
}

MODEL_SOURCE_MAP = {
    "A1": Alert.ModelSource.M1_REPLENISHMENT,
    "A2": Alert.ModelSource.M2_COMMODITY_CHURN,
    "A3": Alert.ModelSource.M2_COMMODITY_CHURN,
    "A4": Alert.ModelSource.M3_TECHNICAL_CHURN,
    "A5": Alert.ModelSource.M3_TECHNICAL_CHURN,
    "A6": Alert.ModelSource.M2_COMMODITY_CHURN,
}

ALERT_TITLES = {
    "A1": "Ventana de reposición abierta — el stock está probablemente bajo",
    "A2": "Ventana de captación — cliente con pedido pendiente",
    "A3": "Caída sostenida — cliente fiel comprando por debajo de lo esperado",
    "A4": "Cliente técnico en riesgo — rompiendo su propio patrón histórico",
    "A5": "Oportunidad de reactivación — cliente inactivo muestra interés de compra",
    "A6": "Caída brusca de ventas — sin tendencia previa, actuar de inmediato",
}


class Command(BaseCommand):
    help = "Run the ML alert pipeline and import results into the database."

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--features-csv",
            help="Path to the features CSV — runs the full ML pipeline before importing",
        )
        source.add_argument(
            "--alerts-csv",
            help="Path to an alertas CSV already produced by pipeline.py or filter_alerts.py",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Delete all OPEN alerts before importing new ones",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and validate without writing to the database",
        )

    def handle(self, *args, **options):
        # ── Mode B: import from pre-built alerts CSV ──────────────────────────
        if options.get("alerts_csv"):
            alerts_path = Path(options["alerts_csv"])
            if not alerts_path.exists():
                raise CommandError(f"Alerts CSV not found: {alerts_path}")
            self.stdout.write(f"[1/2] Reading alerts from {alerts_path}...")
            try:
                df_alerts = pd.read_csv(alerts_path)
            except Exception as exc:
                raise CommandError(f"Could not read alerts CSV: {exc}")

            if df_alerts.empty:
                self.stdout.write(self.style.WARNING("Alerts CSV is empty. Nothing imported."))
                return

            self.stdout.write(f"[1/2] Loaded {len(df_alerts)} alerts.")

            if options["dry_run"]:
                self.stdout.write(self.style.SUCCESS("[DRY RUN] Would import:"))
                for tipo, grp in df_alerts.groupby("tipo_alerta"):
                    self.stdout.write(f"  {tipo}: {len(grp)} alerts")
                return

            self.stdout.write("[2/2] Importing into database...")
            created, skipped = self._import_alerts(df_alerts, clear=options["clear"])
            self.stdout.write(
                self.style.SUCCESS(f"Done. Created: {created}  |  Skipped: {skipped}")
            )
            return

        # ── Mode A: run pipeline then import ─────────────────────────────────
        features_path = Path(options["features_csv"])
        if not features_path.exists():
            raise CommandError(f"Features CSV not found: {features_path}")

        repo_root = Path(__file__).resolve().parents[4]
        analisi_path = repo_root / "Analisi_models"
        if not analisi_path.exists():
            raise CommandError(f"Could not find Analisi_models at {analisi_path}")

        sys.path.insert(0, str(analisi_path))
        try:
            import pipeline as ml_pipeline
        except ImportError as exc:
            raise CommandError(f"Could not import pipeline: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_alerts = os.path.join(tmpdir, "alertas.csv")
            self.stdout.write("[1/3] Running ML pipeline...")
            try:
                df_alerts, _df_m0 = ml_pipeline.main(str(features_path), tmp_alerts)
            except Exception as exc:
                raise CommandError(f"Pipeline failed: {exc}")

        if df_alerts.empty:
            self.stdout.write(self.style.WARNING("Pipeline produced no alerts. Nothing imported."))
            return

        self.stdout.write(f"[2/3] Pipeline generated {len(df_alerts)} alerts.")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] Would import:"))
            for tipo, grp in df_alerts.groupby("tipo_alerta"):
                self.stdout.write(f"  {tipo}: {len(grp)} alerts")
            return

        self.stdout.write("[3/3] Importing into database...")
        created, skipped = self._import_alerts(df_alerts, clear=options["clear"])
        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}  |  Skipped: {skipped}")
        )

    @transaction.atomic
    def _import_alerts(self, df: pd.DataFrame, clear: bool) -> tuple[int, int]:
        if clear:
            deleted, _ = Alert.objects.filter(status=Alert.Status.OPEN).delete()
            self.stdout.write(f"  Cleared {deleted} existing OPEN alerts.")

        created = 0
        skipped = 0

        for _, row in df.iterrows():
            raw_client_id = row.get("client_id")
            tipo = str(row.get("tipo_alerta", "")).strip()

            if pd.isna(raw_client_id) or tipo not in ALERT_TYPE_MAP:
                skipped += 1
                continue

            try:
                client_id_int = int(raw_client_id)
            except (ValueError, TypeError):
                skipped += 1
                continue

            client, _ = Client.objects.get_or_create(client_id=client_id_int)

            # Populate province from pipeline data if not already set
            provincia_raw = row.get("provincia")
            if provincia_raw and pd.notna(provincia_raw) and not client.province:
                client.province = str(provincia_raw).strip()
                client.save(update_fields=["province"])

            familia = row.get("familia") or ""
            dias_restantes = row.get("dias_restantes")
            urgency = int(dias_restantes) if pd.notna(dias_restantes) else None

            impacto = row.get("impacto_estimado")
            economic_impact = float(impacto) if pd.notna(impacto) else None

            score = row.get("score_prioridad")
            confidence = float(score) if pd.notna(score) else None

            canal_raw = str(row.get("canal", "")).strip()
            channel = CHANNEL_MAP.get(canal_raw, Alert.RecommendedChannel.SALES_REP)

            title_base = ALERT_TITLES.get(tipo, tipo)
            title = f"{title_base} — {familia}" if familia else title_base

            lod_raw = row.get("last_order_date")
            last_order_date = lod_raw if pd.notna(lod_raw) and lod_raw else None

            Alert.objects.create(
                client=client,
                alert_type=ALERT_TYPE_MAP[tipo],
                priority=PRIORITY_MAP.get(tipo, Alert.Priority.MEDIUM),
                status=Alert.Status.OPEN,
                model_source=MODEL_SOURCE_MAP.get(tipo),
                title=title[:300],
                reason=str(row.get("motivo") or ""),
                affected_family=str(familia)[:100] if familia else None,
                recommended_channel=channel,
                economic_impact=economic_impact,
                urgency_days=urgency,
                confidence_score=confidence,
                last_order_date=last_order_date,
            )
            created += 1

        return created, skipped
