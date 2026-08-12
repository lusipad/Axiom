from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .adapters import list_artifact_adapters
from .control import (
    R7BAssessmentRequest,
    R7BExamplePayload,
    R7BManifest,
    R7BScenarioSummary,
    R7CAssessmentRequest,
    R7CExamplePayload,
    R7CManifest,
    R7CScenarioSummary,
    R7DAssessmentRequest,
    R7DExamplePayload,
    R7DManifest,
    R7DScenarioSummary,
    R7EAssessmentRequest,
    R7EExamplePayload,
    R7EManifest,
    R7EScenarioSummary,
    R7ExamplePayload,
    R7Manifest,
    R7ReplayRequest,
    R7ScenarioSummary,
)
from .domain import list_domain_packs
from .experiment import contour_ab_example, run_experiment
from .field_evidence import (
    FieldEvidenceAssessmentReport,
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from .five_axis import (
    F1ExamplePayload,
    F1MathStageManifest,
    F2ExamplePayload,
    F2MathStageManifest,
    F3ExamplePayload,
    F3MathStageManifest,
    F4ExamplePayload,
    F4MathStageManifest,
    MathStageManifest,
    build_f1_manifest,
    build_f2_manifest,
    build_f3_manifest,
    build_f4_manifest,
    f0_example_run_spec,
    f1_example_payload,
    f2_example_payload,
    f3_example_payload,
    f4_example_payload,
    list_f1_scenarios,
    list_f2_scenarios,
    list_f3_scenarios,
    list_f4_scenarios,
    load_f0_manifest,
)
from .intelligence import (
    R5BExamplePayload,
    R5BManifest,
    R5BScenarioSummary,
    R5ExamplePayload,
    R5Manifest,
    R5ScenarioSummary,
)
from .machine import (
    list_machine_r3_scenarios,
    load_machine_r3_manifest,
    machine_r3_example_payload,
)
from .models import ExperimentReport, ExperimentSpec, RunBundle, RunSpec
from .optimization import (
    OptimizationSearchRequest,
    R6ExamplePayload,
    R6Manifest,
    R6ScenarioSummary,
)
from .physical import (
    PhysicalR4ExamplePayload,
    PhysicalR4Manifest,
    PhysicalR4ScenarioSummaryPayload,
    R41AssessmentRequest,
    R41ExamplePayload,
    R41Manifest,
    R41ScenarioSummary,
)
from .run import evaluate_run
from .runtime import find_domain_runtime_binding
from .subjects import list_subjects


def _package_version() -> str:
    try:
        return version("axiom-evaluator")
    except PackageNotFoundError:
        return "0.0.0"


def _load_physical_r4_api() -> Any:
    try:
        return import_module("axiom.physical")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.physical":
            raise
        raise HTTPException(
            status_code=503,
            detail="Physical R4 API is unavailable.",
        ) from exc


def _load_intelligence_r5_api() -> Any:
    try:
        return import_module("axiom.intelligence")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.intelligence":
            raise
        raise HTTPException(
            status_code=503,
            detail="Intelligence R5 API is unavailable.",
        ) from exc


def _load_optimization_r6_api() -> Any:
    try:
        return import_module("axiom.optimization")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.optimization":
            raise
        raise HTTPException(
            status_code=503,
            detail="Optimization R6 API is unavailable.",
        ) from exc


def _load_control_r7_api() -> Any:
    try:
        return import_module("axiom.control")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.control":
            raise
        raise HTTPException(
            status_code=503, detail="Control R7 API is unavailable."
        ) from exc


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

    @app.get(
        "/api/v1/five-axis/f1/manifest",
        response_model=F1MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f1_manifest(scenarioId: str = "nominal-certified") -> F1MathStageManifest:
        try:
            return build_f1_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f1/scenarios")
    def five_axis_f1_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f1_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f1",
        response_model=F1ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f1_example(scenarioId: str = "nominal-certified") -> dict[str, Any]:
        try:
            return f1_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f2/manifest",
        response_model=F2MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f2_manifest(scenarioId: str = "canonical-table-table") -> F2MathStageManifest:
        try:
            return build_f2_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f2/scenarios")
    def five_axis_f2_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f2_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f2",
        response_model=F2ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f2_example(scenarioId: str = "canonical-table-table") -> dict[str, Any]:
        try:
            return f2_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f3/manifest",
        response_model=F3MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f3_manifest(
        scenarioId: str = "canonical-table-table-jerk",
    ) -> F3MathStageManifest:
        try:
            return build_f3_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f3/scenarios")
    def five_axis_f3_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f3_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f3",
        response_model=F3ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f3_example(
        scenarioId: str = "canonical-table-table-jerk",
    ) -> dict[str, Any]:
        try:
            return f3_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f4/manifest",
        response_model=F4MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f4_manifest(
        scenarioId: str = "canonical-dual-table-solver",
    ) -> F4MathStageManifest:
        try:
            return build_f4_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f4/scenarios")
    def five_axis_f4_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f4_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f4",
        response_model=F4ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f4_example(
        scenarioId: str = "canonical-dual-table-solver",
    ) -> dict[str, Any]:
        try:
            return f4_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/machine/r3/manifest")
    def machine_r3_manifest() -> dict[str, Any]:
        return load_machine_r3_manifest()

    @app.get("/api/v1/machine/r3/scenarios")
    def machine_r3_scenarios() -> Any:
        return list_machine_r3_scenarios()

    @app.get("/api/v1/examples/machine-r3")
    def machine_r3_example(
        scenarioId: str = "read-only-paired-pass",
    ) -> dict[str, Any]:
        try:
            return machine_r3_example_payload(scenarioId)
        except (FileNotFoundError, KeyError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/physical/r4/manifest",
        response_model=PhysicalR4Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def physical_r4_manifest() -> PhysicalR4Manifest:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.load_r4_manifest()
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/physical/r4/scenarios",
        response_model=list[PhysicalR4ScenarioSummaryPayload],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def physical_r4_scenarios() -> list[PhysicalR4ScenarioSummaryPayload]:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.list_r4_scenarios()
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/physical-r4",
        response_model=PhysicalR4ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def physical_r4_example(
        scenarioId: str = "in-domain-synthetic-sil",
    ) -> PhysicalR4ExamplePayload:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.r4_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 example payload loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/physical/r41/manifest",
        response_model=R41Manifest,
        response_model_by_alias=True,
    )
    def physical_r41_manifest() -> R41Manifest:
        return _load_physical_r4_api().build_r41_manifest()

    @app.get(
        "/api/v1/physical/r41/scenarios",
        response_model=list[R41ScenarioSummary],
        response_model_by_alias=True,
    )
    def physical_r41_scenarios() -> list[R41ScenarioSummary]:
        return list(_load_physical_r4_api().list_r41_scenarios())

    @app.get(
        "/api/v1/examples/physical-r41",
        response_model=R41ExamplePayload,
        response_model_by_alias=True,
    )
    def physical_r41_example(
        scenarioId: str = "physical-reality-evidence-open",
    ) -> R41ExamplePayload:
        try:
            return _load_physical_r4_api().r41_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/physical/r41/assess",
        response_model=R41ExamplePayload,
        response_model_by_alias=True,
    )
    def physical_r41_assess(request: R41AssessmentRequest) -> R41ExamplePayload:
        return _load_physical_r4_api().assess_r41_payload(request)

    @app.get(
        "/api/v1/intelligence/r5/manifest",
        response_model=R5Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5_manifest() -> R5Manifest:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5Manifest.model_validate(intelligence_api.build_r5_manifest())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5/scenarios",
        response_model=list[R5ScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5_scenarios() -> list[R5ScenarioSummary]:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return list(intelligence_api.list_r5_scenarios())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/intelligence-r5",
        response_model=R5ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def intelligence_r5_example(
        scenarioId: str = "synthetic-residual-contract",
    ) -> R5ExamplePayload:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5ExamplePayload.model_validate(intelligence_api.r5_example_payload(scenarioId))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 example payload loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5b/manifest",
        response_model=R5BManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5b_manifest() -> R5BManifest:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5BManifest.model_validate(intelligence_api.build_r5b_manifest())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5b/scenarios",
        response_model=list[R5BScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5b_scenarios() -> list[R5BScenarioSummary]:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return list(intelligence_api.list_r5b_scenarios())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/intelligence-r5b",
        response_model=R5BExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def intelligence_r5b_example(
        scenarioId: str = "real-holdout-readiness-open",
    ) -> R5BExamplePayload:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5BExamplePayload.model_validate(intelligence_api.r5b_example_payload(scenarioId))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B example payload loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/optimization/r6/manifest",
        response_model=R6Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_manifest() -> R6Manifest:
        optimization_api = _load_optimization_r6_api()
        return optimization_api.build_r6_manifest()

    @app.get(
        "/api/v1/optimization/r6/scenarios",
        response_model=list[R6ScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_scenarios() -> list[R6ScenarioSummary]:
        optimization_api = _load_optimization_r6_api()
        return list(optimization_api.list_r6_scenarios())

    @app.get(
        "/api/v1/examples/optimization-r6",
        response_model=R6ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def optimization_r6_example(
        scenarioId: str = "canonical-head-table-offline-pareto",
    ) -> R6ExamplePayload:
        optimization_api = _load_optimization_r6_api()
        try:
            return optimization_api.r6_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/optimization/r6/search",
        response_model=R6ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def optimization_r6_search(search_request: OptimizationSearchRequest) -> R6ExamplePayload:
        optimization_api = _load_optimization_r6_api()
        recommendations = optimization_api.search_recommendations(search_request)
        scenario = optimization_api.list_r6_scenarios()[0]
        run_spec = optimization_api.build_r6_run_spec(search_request)
        return R6ExamplePayload(
            manifest=optimization_api.build_r6_manifest(),
            scenario=scenario,
            searchRequest=search_request,
            recommendationSet=recommendations,
            runSpec=run_spec.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    @app.get(
        "/api/v1/control/r7/manifest",
        response_model=R7Manifest,
        response_model_by_alias=True,
    )
    def control_r7_manifest() -> R7Manifest:
        return _load_control_r7_api().build_r7_manifest()

    @app.get(
        "/api/v1/control/r7/scenarios",
        response_model=list[R7ScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7_scenarios() -> list[R7ScenarioSummary]:
        return list(_load_control_r7_api().list_r7_scenarios())

    @app.get(
        "/api/v1/examples/control-r7",
        response_model=R7ExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7_example(
        scenarioId: str = "synthetic-shadow-nominal",
    ) -> R7ExamplePayload:
        try:
            return _load_control_r7_api().r7_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7/replay",
        response_model=R7ExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7_replay(request: R7ReplayRequest) -> R7ExamplePayload:
        try:
            return _load_control_r7_api().r7_example_payload(request.scenario_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/control/r7b/manifest",
        response_model=R7BManifest,
        response_model_by_alias=True,
    )
    def control_r7b_manifest() -> R7BManifest:
        return _load_control_r7_api().build_r7b_manifest()

    @app.get(
        "/api/v1/control/r7b/scenarios",
        response_model=list[R7BScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7b_scenarios() -> list[R7BScenarioSummary]:
        return list(_load_control_r7_api().list_r7b_scenarios())

    @app.get(
        "/api/v1/examples/control-r7b",
        response_model=R7BExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7b_example(
        scenarioId: str = "deployment-shadow-readiness-open",
    ) -> R7BExamplePayload:
        try:
            return _load_control_r7_api().r7b_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7b/assess",
        response_model=R7BExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7b_assess(request: R7BAssessmentRequest) -> R7BExamplePayload:
        return _load_control_r7_api().assess_r7b_payload(request)

    @app.get(
        "/api/v1/control/r7c/manifest",
        response_model=R7CManifest,
        response_model_by_alias=True,
    )
    def control_r7c_manifest() -> R7CManifest:
        return _load_control_r7_api().build_r7c_manifest()

    @app.get(
        "/api/v1/control/r7c/scenarios",
        response_model=list[R7CScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7c_scenarios() -> list[R7CScenarioSummary]:
        return list(_load_control_r7_api().list_r7c_scenarios())

    @app.get(
        "/api/v1/examples/control-r7c",
        response_model=R7CExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7c_example(
        scenarioId: str = "opcua-transport-evidence-open",
    ) -> R7CExamplePayload:
        try:
            return _load_control_r7_api().r7c_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7c/assess",
        response_model=R7CExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7c_assess(request: R7CAssessmentRequest) -> R7CExamplePayload:
        return _load_control_r7_api().assess_r7c_payload(request)

    @app.get(
        "/api/v1/control/r7d/manifest",
        response_model=R7DManifest,
        response_model_by_alias=True,
    )
    def control_r7d_manifest() -> R7DManifest:
        return _load_control_r7_api().build_r7d_manifest()

    @app.get(
        "/api/v1/control/r7d/scenarios",
        response_model=list[R7DScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7d_scenarios() -> list[R7DScenarioSummary]:
        return list(_load_control_r7_api().list_r7d_scenarios())

    @app.get(
        "/api/v1/examples/control-r7d",
        response_model=R7DExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7d_example(
        scenarioId: str = "beckhoff-twincat-runtime-open",
    ) -> R7DExamplePayload:
        try:
            return _load_control_r7_api().r7d_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7d/assess",
        response_model=R7DExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7d_assess(request: R7DAssessmentRequest) -> R7DExamplePayload:
        return _load_control_r7_api().assess_r7d_payload(request)

    @app.get(
        "/api/v1/control/r7e/manifest",
        response_model=R7EManifest,
        response_model_by_alias=True,
    )
    def control_r7e_manifest() -> R7EManifest:
        return _load_control_r7_api().build_r7e_manifest()

    @app.get(
        "/api/v1/control/r7e/scenarios",
        response_model=list[R7EScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7e_scenarios() -> list[R7EScenarioSummary]:
        return list(_load_control_r7_api().list_r7e_scenarios())

    @app.get(
        "/api/v1/examples/control-r7e",
        response_model=R7EExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7e_example(
        scenarioId: str = "beckhoff-shadow-witness-open",
    ) -> R7EExamplePayload:
        try:
            return _load_control_r7_api().r7e_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7e/assess",
        response_model=R7EExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7e_assess(request: R7EAssessmentRequest) -> R7EExamplePayload:
        return _load_control_r7_api().assess_r7e_payload(request)

    @app.post(
        "/api/v1/field-evidence/assess",
        response_model=FieldEvidenceAssessmentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def field_evidence_assess(
        request: FieldEvidenceAssessmentRequest,
    ) -> FieldEvidenceAssessmentReport:
        return assess_field_evidence(request)

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
