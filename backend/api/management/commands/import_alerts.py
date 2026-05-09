"""
management/commands/import_alerts.py

Runs the ML pipeline against a features CSV and imports the resulting
alerts into the Django database.

Usage:
    python manage.py import_alerts --features-csv path/to/features_v2.csv

Options:
    --features-csv   Path to the pre-built features CSV (required)
    --clear          Delete all existing open alerts before importing (default: False)
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
    "A4": Alert.AlertType.A4_TECHNICAL_CHURN,
    "A5": Alert.AlertType.A5_ANOMALY,
    "A6": Alert.AlertType.A6_HIDDEN_FRICTION,
    "A7": Alert.AlertType.A7_EARLY_WARNING,
    "A8": Alert.AlertType.A8_RETURN_RISK,
    "A9": Alert.AlertType.A9_PRE_CHURN,
}

PRIORITY_MAP = {
    "A6": Alert.Priority.CRITICAL,
    "A3": Alert.Priority.HIGH,
    "A4": Alert.Priority.HIGH,
    "A8": Alert.Priority.HIGH,
    "A2": Alert.Priority.MEDIUM,
    "A9": Alert.Priority.MEDIUM,
    "A1": Alert.Priority.LOW,
    "A5": Alert.Priority.LOW,
    "A7": Alert.Priority.LOW,
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
    "A7": Alert.ModelSource.M1_REPLENISHMENT,
    "A8": Alert.ModelSource.M4_RETURN_RISK,
    "A9": Alert.ModelSource.M5_PRE_CHURN,
}

ALERT_TITLES = {
    "A1": "Replenishment window",
    "A2": "Capture window — promiscuous customer",
    "A3": "Commodity churn — loyal customer",
    "A4": "Technical product churn",
    "A5": "Recoverable customer",
    "A6": "Abrupt volume drop",
    "A7": "New customer without second purchase",
    "A8": "Hidden friction — returns / cancellations",
    "A9": "Early pre-churn signal",
}


class Command(BaseCommand):
    help = "Run the ML alert pipeline and import results into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--features-csv",
            required=True,
            help="Path to the features CSV produced by feature_engineering_v2.py",
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
        features_path = Path(options["features_csv"])
        if not features_path.exists():
            raise CommandError(f"Features CSV not found: {features_path}")

        # Locate the pipeline module relative to this file
        repo_root = Path(__file__).resolve().parents[4]  # backend/api/management/commands → repo root
        analisi_path = repo_root / "Analisi_models"
        if not analisi_path.exists():
            raise CommandError(f"Could not find Analisi_models at {analisi_path}")

        sys.path.insert(0, str(analisi_path))
        try:
            import pipeline as ml_pipeline
        except ImportError as exc:
            raise CommandError(f"Could not import pipeline: {exc}")

        # Run pipeline to a temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_path = os.path.join(tmpdir, "alertas.csv")
            self.stdout.write("[1/3] Running ML pipeline...")
            try:
                df_alerts, _df_m0 = ml_pipeline.main(str(features_path), alerts_path)
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
            self.style.SUCCESS(
                f"Done. Created: {created}  |  Skipped (unknown client): {skipped}"
            )
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

            familia = row.get("familia") or ""
            dias_restantes = row.get("dias_restantes")
            urgency = int(dias_restantes) if pd.notna(dias_restantes) else None

            impacto = row.get("impacto_estimado")
            economic_impact = float(impacto) if pd.notna(impacto) else None

            score = row.get("score_prioridad")
            confidence = float(score) if pd.notna(score) else None

            canal_raw = str(row.get("canal", "")).strip()
            channel = CHANNEL_MAP.get(canal_raw, Alert.RecommendedChannel.SALES_REP)

            label_m0 = str(row.get("label_m0", "")).strip()
            title_base = ALERT_TITLES.get(tipo, tipo)
            title = f"{title_base} — {familia}" if familia else title_base
            if label_m0 and label_m0 not in ("", "nan", "desconocido"):
                title = f"[{label_m0}] {title}"

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
            )
            created += 1

        return created, skipped
