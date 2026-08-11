from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .domain import ORDERED_POINT_DOMAIN_PACK_ID
from .evaluator import evaluate as evaluate_ordered_point
from .models import CoreEvaluationRequest, EvaluationReport, EvaluationRequest


@dataclass(frozen=True)
class DomainRuntimeBinding:
    domain_pack_id: str
    parse_request: Callable[[CoreEvaluationRequest], Any]
    evaluate: Callable[[Any], EvaluationReport]


_DOMAIN_RUNTIME_BINDINGS: dict[str, DomainRuntimeBinding] = {}


def register_domain_runtime_binding(binding: DomainRuntimeBinding) -> DomainRuntimeBinding:
    existing = _DOMAIN_RUNTIME_BINDINGS.get(binding.domain_pack_id)
    if existing is not None:
        if existing != binding:
            raise ValueError(f"domain runtime binding is already registered: {binding.domain_pack_id}")
        return existing
    _DOMAIN_RUNTIME_BINDINGS[binding.domain_pack_id] = binding
    return binding


def get_domain_runtime_binding(domain_pack_id: str) -> DomainRuntimeBinding:
    try:
        return _DOMAIN_RUNTIME_BINDINGS[domain_pack_id]
    except KeyError as exc:
        raise LookupError(f"unknown domain runtime binding: {domain_pack_id}") from exc


def find_domain_runtime_binding(domain_pack_id: str) -> DomainRuntimeBinding | None:
    return _DOMAIN_RUNTIME_BINDINGS.get(domain_pack_id)


def _coerce_request_payload(request: CoreEvaluationRequest | Mapping[str, Any]) -> CoreEvaluationRequest:
    if isinstance(request, CoreEvaluationRequest):
        return request
    return CoreEvaluationRequest.model_validate(request)


def _parse_ordered_point_request(request: CoreEvaluationRequest | Mapping[str, Any]) -> EvaluationRequest:
    core_request = _coerce_request_payload(request)
    payload = core_request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return EvaluationRequest.model_validate(payload)


register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=ORDERED_POINT_DOMAIN_PACK_ID,
        parse_request=_parse_ordered_point_request,
        evaluate=evaluate_ordered_point,
    )
)
