from __future__ import annotations

from typing import Any

from .models import canonical_hash
from .r5c_models import (
    ConditionalEffectDomain,
    ConditionalEffectHead,
    ConditionalEffectPrediction,
    ConditionalEffectPredictionRequest,
    R5C_FEATURE_ORDER,
)


def conditional_effect_feature_vector(
    domain: ConditionalEffectDomain,
    *,
    feed_override: float,
    sample_period: float,
) -> tuple[float, float, float, float, float, float]:
    inverse_feed_minimum = 1.0 / domain.feed_override_maximum
    inverse_feed_maximum = 1.0 / domain.feed_override_minimum
    inverse_feed_center = (inverse_feed_minimum + inverse_feed_maximum) / 2.0
    inverse_feed_half_range = (
        inverse_feed_maximum - inverse_feed_minimum
    ) / 2.0
    sample_period_center = (
        domain.sample_period_minimum + domain.sample_period_maximum
    ) / 2.0
    sample_period_half_range = (
        domain.sample_period_maximum - domain.sample_period_minimum
    ) / 2.0
    normalized_inverse_feed = (
        (1.0 / feed_override) - inverse_feed_center
    ) / inverse_feed_half_range
    normalized_sample_period = (
        sample_period - sample_period_center
    ) / sample_period_half_range
    features = (
        1.0,
        normalized_inverse_feed,
        normalized_sample_period,
        normalized_inverse_feed * normalized_sample_period,
        normalized_sample_period * normalized_sample_period,
        normalized_inverse_feed * normalized_inverse_feed,
    )
    if len(features) != len(R5C_FEATURE_ORDER):
        raise AssertionError("R5-C feature vector does not match frozen feature order")
    return features


def pure_python_conditional_effect_value(
    head: ConditionalEffectHead,
    features: tuple[float, float, float, float, float, float],
) -> float:
    return float(sum(weight * feature for weight, feature in zip(head.weights, features, strict=True)))


def _sealed_prediction(payload: dict[str, Any]) -> ConditionalEffectPrediction:
    payload["contentHash"] = canonical_hash(payload)
    return ConditionalEffectPrediction.model_validate(payload)


def predict_conditional_effect(
    request: ConditionalEffectPredictionRequest,
) -> ConditionalEffectPrediction:
    bundle = request.model_bundle
    common: dict[str, Any] = {
        "schemaId": "axiom.intelligence.conditional-effect-prediction@1",
        "modelBundleHash": bundle.content_hash,
        "feedOverride": request.feed_override,
        "samplePeriod": request.sample_period,
        "realWorldGeneralizationStatus": "Open",
        "permissionLevel": "Offline",
        "deviceWriteAllowed": False,
    }
    if not bundle.domain.contains(request.feed_override, request.sample_period):
        return _sealed_prediction(
            {
                **common,
                "status": "Abstained",
                "predictions": [],
                "reasonCode": "OutsideDeclaredDomain",
            }
        )

    features = conditional_effect_feature_vector(
        bundle.domain,
        feed_override=request.feed_override,
        sample_period=request.sample_period,
    )
    predictions = []
    for head in bundle.heads:
        value = pure_python_conditional_effect_value(head, features)
        predictions.append(
            {
                "targetId": head.target_id,
                "unit": head.unit,
                "value": value,
                "lower": value - head.conformal_radius,
                "upper": value + head.conformal_radius,
            }
        )
    return _sealed_prediction(
        {**common, "status": "Predicted", "predictions": predictions}
    )


__all__ = [
    "conditional_effect_feature_vector",
    "predict_conditional_effect",
    "pure_python_conditional_effect_value",
]
