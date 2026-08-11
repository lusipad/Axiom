from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .domain import list_domain_packs
from .experiment import contour_ab_example, run_experiment
from .models import ExperimentReport, ExperimentSpec
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
                pack.model_dump(mode="json", by_alias=True) for pack in list_domain_packs()
            ],
        }

    @app.get("/api/v1/examples/contour-ab", response_model=ExperimentSpec, response_model_by_alias=True)
    def contour_example() -> ExperimentSpec:
        return contour_ab_example()

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
