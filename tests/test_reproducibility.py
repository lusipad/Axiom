from axiom import evaluate


def test_identical_request_replays_to_identical_report(make_request):
    request = make_request(
        [[0, 0], [3, 4]],
        ["point.count", "path.length.open", "closure.gap"],
        case_id="determinism@1",
    )

    first = evaluate(request)
    second = evaluate(request)

    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(mode="json", by_alias=True)
    assert first.content_hash == second.content_hash
    assert first.provenance.request_hash == first.content_hash
    assert first.provenance.artifact_hash
    assert first.provenance.case_hash
    assert first.provenance.runner_id == "artifact-import@1"
    assert first.provenance.execution_outcome_policy == "axiom.core.execution-outcome.default@1"


def test_metric_results_publish_machine_readable_capability_requirements(make_request):
    report = evaluate(make_request([[0, 0], [1, 0]], ["path.length.open"]))

    assert report.metric_result("path.length.open").requires == [
        "ordered-point.artifact.valid@1",
        "ordered-point.sequence.ordered@1",
        "ordered-point.coordinate.euclidean@1",
    ]


def test_omitted_and_explicitly_unknown_semantics_have_distinct_content_ids(make_request):
    omitted = make_request([[0, 0]], ["point.count"], semantics={})
    explicit_unknown = make_request([[0, 0]], ["point.count"], semantics={"unit": None})

    assert evaluate(omitted).content_hash != evaluate(explicit_unknown).content_hash
