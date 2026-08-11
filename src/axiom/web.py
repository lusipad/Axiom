from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .adapters import list_artifact_adapters
from .domain import list_domain_packs
from .experiment import contour_ab_example, run_experiment
from .five_axis import MathStageManifest, f0_example_run_spec, load_f0_manifest
from .models import ExperimentReport, ExperimentSpec, RunBundle, RunSpec
from .run import evaluate_run
from .runtime import find_domain_runtime_binding
from .subjects import list_subjects


def _package_version() -> str:
    try:
        return version("axiom-evaluator")
    except PackageNotFoundError:
        return "0.0.0"


def create_app(*, serve_frontend: bool = True, frontend_dir: Path | None = None) -> FastAPI:
    package_version = _package_version()
    app = FastAPI(
        title="Axiom Experiment Workbench API",
        version=package_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": package_version}

    @app.get("/api/v1/catalog")
    def catalog() -> dict[str, Any]:
        return {
            "subjects": [
                subject.model_dump(mode="json", by_alias=True) for subject in list_subjects()
            ],
            "domainPacks": [
                {
                    **pack.model_dump(mode="json", by_alias=True),
                    "runtimeBound": find_domain_runtime_binding(pack.domain_pack_id) is not None,
                }
                for pack in list_domain_packs()
            ],
            "artifactAdapters": [
                {
                    "adapterId": adapter.adapter_id,
                    "sourceArtifactType": adapter.source_artifact_type,
                    "targetArtifactType": adapter.target_artifact_type,
                }
                for adapter in list_artifact_adapters()
            ],
        }

    @app.post(
        "/api/v1/runs/evaluate",
        response_model=RunBundle,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def execute_run(spec: RunSpec) -> RunBundle:
        return evaluate_run(spec)

    @app.get("/api/v1/examples/contour-ab", response_model=ExperimentSpec, response_model_by_alias=True)
    def contour_example() -> ExperimentSpec:
        return contour_ab_example()

    @app.get(
        "/api/v1/five-axis/f0/manifest",
        response_model=MathStageManifest,
        response_model_by_alias=True,
    )
    def five_axis_f0_manifest() -> MathStageManifest:
        return load_f0_manifest()

    @app.get(
        "/api/v1/examples/five-axis-f0",
        response_model=RunSpec,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f0_example() -> RunSpec:
        return RunSpec.model_validate(f0_example_run_spec())

    @app.post(
        "/api/v1/experiments/run",
        response_model=ExperimentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def execute_experiment(spec: ExperimentSpec) -> ExperimentReport:
        return run_experiment(spec)

    if serve_frontend:
        static_dir = frontend_dir or Path(__file__).with_name("web_dist")
        index_path = static_dir / "index.html"
        if not index_path.is_file():
            raise RuntimeError(
                f"Axiom web assets are missing at {static_dir}. Run the frontend build before starting the server."
            )
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app
