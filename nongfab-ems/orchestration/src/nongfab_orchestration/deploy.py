"""Entrypoint: `nongfab-orchestration-serve` (see pyproject.toml) runs all
flows as long-lived Prefect deployments, each on its own schedule - an
alternative scheduling path to each ingestion module's internal
AsyncIOScheduler (himawari_ingestion/main.py, nwp_ingestion/main.py) for
whoever deploys this; those modules' own standalone daemons still work
unchanged for local/ad-hoc dev use (see README).
"""

from __future__ import annotations

from himawari_ingestion.config import get_settings as himawari_settings
from nwp_ingestion.config import get_settings as nwp_settings
from prefect import serve

from .ingestion_flows import himawari_ingestion_flow, nwp_ingestion_flow
from .retrain_flows import retrain_all_flow

# No equivalent "how often" setting exists yet for retraining - once daily,
# off-peak, is a reasonable default until real accumulated history (and thus
# a real reason to retrain more/less often) exists.
DEFAULT_RETRAIN_CRON = "0 3 * * *"


def _himawari_cron() -> str:
    return f"*/{himawari_settings().poll_interval_minutes} * * * *"


def _nwp_cron() -> str:
    """Mirrors nwp_ingestion.scheduler.build_scheduler()'s own hour/minute
    computation: trigger at each GFS cycle hour plus publish latency, not
    the raw cycle hour, since the data doesn't exist yet at the raw cycle
    time (see that module's README "Data source & ToS").
    """
    settings = nwp_settings()
    trigger_hours = sorted((h + settings.publish_latency_minutes // 60) % 24 for h in settings.gfs_cycles)
    trigger_minute = settings.publish_latency_minutes % 60
    return f"{trigger_minute} {','.join(str(h) for h in trigger_hours)} * * *"


def main() -> None:
    himawari_deployment = himawari_ingestion_flow.to_deployment(name="himawari-ingestion-schedule", cron=_himawari_cron())
    nwp_deployment = nwp_ingestion_flow.to_deployment(name="nwp-ingestion-schedule", cron=_nwp_cron())
    retrain_deployment = retrain_all_flow.to_deployment(name="retrain-all-schedule", cron=DEFAULT_RETRAIN_CRON)
    serve(himawari_deployment, nwp_deployment, retrain_deployment)


if __name__ == "__main__":
    main()
