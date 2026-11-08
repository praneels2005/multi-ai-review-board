"""Operation payload validation using projections of the existing response contracts.

Execution metadata belongs to the application, not to the provider payload. Required
content is validated before those metadata fields are added by the orchestrator.
"""
from copy import deepcopy

from pydantic import ConfigDict, ValidationError, create_model
from pydantic_core import PydanticUndefined

from app.schemas.review_board_schema import (
    ChallengeResponseItem, CoordinatorCombinedReview, ReviewBoardSession,
    SpecialistAgentConfig, SpecialistFeedback, ValidationExperiment,
)


class ResponseFailure(ValueError):
    def __init__(self, kind, detail):
        self.kind = kind
        super().__init__(detail if detail.startswith(kind + ":") else f"{kind}: {detail}")


def _projection(name, source, fields, required, annotations=None):
    definitions = {}
    for key in fields:
        field = deepcopy(source.model_fields[key])
        if key in required:
            field.default = PydanticUndefined
            field.default_factory = None
        definitions[key] = ((annotations or {}).get(key, field.annotation), field)
    return create_model(name, __config__=ConfigDict(strict=True), **definitions)


SPECIALIST_FIELDS = (
    "strengths", "risks", "missing_assumptions", "questions", "validation_experiment",
    "evidence_citations", "assumptions_and_unknowns",
)
COORDINATOR_FIELDS = (
    "summary", "priorities", "disagreements", "next_experiments",
    "evidence_sufficiency", "failure_impact_analysis", "disclaimer",
)
RESULT_MODELS = {
    "panel_generation": create_model("PanelResult", __config__=ConfigDict(strict=True),
                                     specialists=(list[SpecialistAgentConfig], ...)),
    # Failed persisted reviews may omit experiments; successful provider output may not.
    "specialist_review": _projection("SpecialistResult", SpecialistFeedback, SPECIALIST_FIELDS,
                                      {"strengths", "risks", "missing_assumptions", "questions", "validation_experiment"},
                                      {"validation_experiment": ValidationExperiment}),
    "challenge_generation": _projection("ChallengeResult", ChallengeResponseItem, ["challenge_point"], {"challenge_point"}),
    "challenge_response": _projection("TargetResult", ChallengeResponseItem,
                                      ["response", "reasoning_adjustment"], {"response", "reasoning_adjustment"}),
    "coordinator_synthesis": _projection("CoordinatorResult", CoordinatorCombinedReview, COORDINATOR_FIELDS,
                                         set(COORDINATOR_FIELDS) - {"failure_impact_analysis"}),
}


def _nonblank(value):
    if isinstance(value, str) and not value.strip():
        raise ResponseFailure("schema_validation", "Supplied text fields must not be blank")
    if isinstance(value, dict):
        for item in value.values():
            _nonblank(item)
    if isinstance(value, list):
        for item in value:
            _nonblank(item)


def validate_result(task, response):
    if response.error:
        kind = "provider_error"
        for category in ("malformed_json", "schema_validation", "timeout"):
            if response.error.startswith(category + ":"):
                kind = category
        raise ResponseFailure(kind, response.error)
    return validate_payload(task, response.parsed_json)


def validate_payload(task, data):
    if not isinstance(data, dict):
        raise ResponseFailure("schema_validation", "Expected a JSON object")
    try:
        if data.get("is_fallback") is True or data.get("status", "success") != "success":
            raise ResponseFailure("schema_validation", "Provider output is not a successful assessment")
        result = RESULT_MODELS[task].model_validate(data, strict=True)
        clean = result.model_dump()
        _nonblank(clean)
        if task == "panel_generation":
            ReviewBoardSession.validate_panel_uniqueness(result.specialists)
        if task == "specialist_review":
            for key in ("strengths", "risks", "missing_assumptions", "questions"):
                if not clean[key]:
                    raise ResponseFailure("schema_validation", f"Missing non-empty {key}")
        return clean
    except ValidationError as exc:
        # Locations and error types are useful; input values can contain credentials.
        details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors())
        raise ResponseFailure("schema_validation", details) from None
    except ResponseFailure:
        raise
    except ValueError as exc:
        raise ResponseFailure("schema_validation", str(exc)) from None
