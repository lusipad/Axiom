from __future__ import annotations

from .models import FeatureEnvelope, IntelligenceSample, ModelBundle


def target_feature_vector(
    sample: IntelligenceSample,
) -> tuple[float, float, float, float, float, float]:
    t = float(sample.t)
    return (
        1.0,
        t,
        t * t,
        t * t * t,
        t * t * t * t,
        float(sample.command - sample.simulation),
    )


def pure_python_predict_residual(weights: tuple[float, ...], features: tuple[float, ...]) -> float:
    total = 0.0
    for weight, feature in zip(weights, features, strict=True):
        total += float(weight) * float(feature)
    return total


def target_is_ood(envelope: FeatureEnvelope, features: tuple[float, ...]) -> bool:
    for value, lower, upper in zip(features, envelope.minimums, envelope.maximums, strict=True):
        margin = envelope.margin_fraction * abs(upper - lower)
        if value < lower - margin or value > upper + margin:
            return True
    return False


def pure_python_predict_observation(
    bundle: ModelBundle,
    sample: IntelligenceSample,
) -> tuple[bool, float | None]:
    features = target_feature_vector(sample)
    if target_is_ood(bundle.x_axis_head.feature_envelope, features):
        return True, None
    residual = pure_python_predict_residual(bundle.x_axis_head.weights, features)
    return False, float(sample.simulation + residual)


__all__ = [
    "pure_python_predict_observation",
    "pure_python_predict_residual",
    "target_feature_vector",
    "target_is_ood",
]
