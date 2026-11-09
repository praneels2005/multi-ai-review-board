"""Reject ambiguous evidence IDs before panel generation or review dispatch."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.review_board_schema import StartupIdeaInput
from app.services.panel_service import PanelService
from app.services.review_runs import ReviewRuns


def idea(ids):
    return dict(title='Test idea', idea='A sufficiently detailed startup description',
                target_customer='Platform teams', problem='Slow investigations',
                proposed_solution='Better diagnostic tools',
                evidence=[dict(id=id, source=f'Source {i}', summary=f'Report {i}')
                          for i, id in enumerate(ids)])


@pytest.mark.parametrize('ids', [('E1', 'E1'), ('E1', 'e1'), (' E1 ', 'e1'), ('Lab-99', 'LAB-99')])
def test_duplicate_evidence_ids_rejected(ids):
    with pytest.raises(ValidationError, match='Evidence IDs must be unique'):
        StartupIdeaInput.model_validate(idea(ids))


@pytest.mark.parametrize('ids', [[], ['E1'], ['E1', 'E10'], ['lab-99', 'Customer-A']])
def test_distinct_ids_remain_unchanged(ids):
    result = StartupIdeaInput.model_validate(idea(ids))
    assert [item.id for item in result.evidence] == ids


@pytest.mark.parametrize('endpoint', ['generate-panel', 'runs'])
def test_duplicate_ids_return_422_before_execution(monkeypatch, endpoint):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid evidence reached execution')
    monkeypatch.setattr(PanelService, 'generate_panel', unexpected)
    monkeypatch.setattr(ReviewRuns, 'start', unexpected)
    payload = {'idea': idea(['E1', ' e1 '])}
    if endpoint == 'runs':
        payload['panel'] = [dict(id=f'spec_{i}', role=f'Role {i}', expertise='Expertise',
                                 mandate='Mandate', rationale='Rationale', provider='mock')
                            for i in range(3)]
    with TestClient(app) as client:
        response = client.post(f'/api/review-board/{endpoint}', json=payload)
    assert response.status_code == 422
    assert any(error['loc'] == ['body', 'idea', 'evidence'] and
               'Evidence IDs must be unique' in error['msg']
               for error in response.json()['detail'])
