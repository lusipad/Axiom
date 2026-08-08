"""Axiom ordered-point evaluator public API."""

from .comparison import compare, compare_runs
from .domain import (
    ORDERED_POINT_DOMAIN_PACK,
    DomainPack,
    MetricDefinition,
    get_domain_pack,
    list_domain_packs,
    register_domain_pack,
)
from .evaluator import evaluate
from .models import (
    CaseOutcome,
    Claim,
    ClaimStatus,
    ComparisonOperand,
    ComparisonReport,
    ComparisonSpec,
    CompatibilityIssue,
    CompatibilityReport,
    EvaluationReport,
    EvaluationRequest,
    ExecutionStatus,
    MetricComparison,
    MetricStatus,
    Observation,
    Run,
    RunBundle,
    RunSpec,
)
from .run import evaluate_run

__all__ = [
    "Claim",
    "ClaimStatus",
    "CaseOutcome",
    "ComparisonOperand",
    "ComparisonReport",
    "ComparisonSpec",
    "CompatibilityIssue",
    "CompatibilityReport",
    "compare",
    "compare_runs",
    "DomainPack",
    "EvaluationReport",
    "EvaluationRequest",
    "ExecutionStatus",
    "evaluate_run",
    "MetricStatus",
    "MetricComparison",
    "MetricDefinition",
    "Observation",
    "ORDERED_POINT_DOMAIN_PACK",
    "get_domain_pack",
    "list_domain_packs",
    "register_domain_pack",
    "Run",
    "RunBundle",
    "RunSpec",
    "evaluate",
]
