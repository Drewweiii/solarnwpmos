"""MLflow experiment tracking + Model Registry: log a training run's params/
metrics/model artifact, load back the latest (or a specific) registered
version, and compare all versions for a given (horizon, zone) - the
"versioning, A/B compare" the architecture doc asks for.

Models are logged via a generic `mlflow.pyfunc.PythonModel` wrapper that
cloudpickles whatever object is passed in (an HourAheadModel, MinuteAheadModel,
or DayAheadModel - all structurally different) rather than mapping each to
its own native MLflow flavor (mlflow.lightgbm, mlflow.pytorch, ...) - NeuralProphet
in particular has no native MLflow flavor at all. `load_model()` unwraps the
pyfunc wrapper and hands back the original object, ready for that horizon's
own `predict_*()` function - this is MLflow for tracking/versioning, not a
pyfunc-serving endpoint (nothing consumes one yet; see README "Known gaps").

Tracking URI defaults to a local sqlite file (MLflow's file-store backend is
deprecated as of MLflow 3.x - see README) - override with MLFLOW_TRACKING_URI
to point at the docker-compose mlflow service in production.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cloudpickle
import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.tracking import MlflowClient

DEFAULT_TRACKING_URI = "sqlite:///mlflow.db"


def get_tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def experiment_name_for(horizon: str, zone: str) -> str:
    return f"nongfab-forecast-{horizon}-{zone}"


def registered_model_name_for(horizon: str, zone: str) -> str:
    return f"nongfab-{horizon}-{zone}"


class _PickledModelWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context) -> None:
        with open(context.artifacts["model"], "rb") as f:
            self.model = cloudpickle.load(f)

    def predict(self, context, model_input, params=None):
        raise NotImplementedError(
            "this wrapper exists for MLflow Model Registry versioning, not pyfunc serving - "
            "use registry.load_model() to get the original object back, then call that "
            "horizon's own predict_*() function directly."
        )


def log_run(horizon: str, zone: str, model_obj, params: dict, metrics: dict) -> tuple[str, int]:
    """Logs one training run under experiment `nongfab-forecast-{horizon}-{zone}`
    and registers `model_obj` as a new version of `nongfab-{horizon}-{zone}`.
    Returns (run_id, registered_version).
    """
    mlflow.set_tracking_uri(get_tracking_uri())
    mlflow.set_experiment(experiment_name_for(horizon, zone))
    registered_name = registered_model_name_for(horizon, zone)

    with mlflow.start_run() as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.pkl"
            with open(model_path, "wb") as f:
                cloudpickle.dump(model_obj, f)
            mlflow.pyfunc.log_model(
                name="model", python_model=_PickledModelWrapper(), artifacts={"model": str(model_path)},
                registered_model_name=registered_name,
            )
        run_id = run.info.run_id

    client = MlflowClient()
    version = next(v.version for v in client.search_model_versions(f"name='{registered_name}'") if v.run_id == run_id)
    return run_id, int(version)


def load_model(horizon: str, zone: str, version: str | int = "latest"):
    """Loads back the original object logged by log_run() (e.g. an
    HourAheadModel) - ready to pass straight into that horizon's predict_*().
    """
    mlflow.set_tracking_uri(get_tracking_uri())
    registered_name = registered_model_name_for(horizon, zone)
    client = MlflowClient()
    versions = client.search_model_versions(f"name='{registered_name}'")
    if not versions:
        raise ValueError(f"no registered versions found for {registered_name!r}")

    resolved_version = max(int(v.version) for v in versions) if version == "latest" else int(version)

    pyfunc_model = mlflow.pyfunc.load_model(f"models:/{registered_name}/{resolved_version}")
    wrapper = pyfunc_model.unwrap_python_model()
    return wrapper.model


def compare_versions(horizon: str, zone: str) -> pd.DataFrame:
    """One row per registered version with its logged metrics, indexed by
    version - the "A/B compare" the architecture doc asks for for picking the
    best-performing version, not just always trusting the newest.
    """
    mlflow.set_tracking_uri(get_tracking_uri())
    registered_name = registered_model_name_for(horizon, zone)
    client = MlflowClient()
    versions = client.search_model_versions(f"name='{registered_name}'")
    if not versions:
        raise ValueError(f"no registered versions found for {registered_name!r}")

    rows = []
    for v in versions:
        run = client.get_run(v.run_id)
        row = dict(run.data.metrics)
        row["version"] = int(v.version)
        row["run_id"] = v.run_id
        rows.append(row)
    return pd.DataFrame(rows).set_index("version").sort_index()
