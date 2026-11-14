"""Verify founder-facing prompt contracts reach every review-board operation."""
import asyncio
import json

from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.schemas.provider_results import RESULT_MODELS
from app.services.panel_service import PanelService
from app.services.review_orchestrator import ReviewBoardOrchestrator


def test_review_prompts_deliver_style_and_unchanged_json_contracts(monkeypatch):
    calls = []
    original = DeterministicMockAdapter.call

    async def capture(self, *args, **kwargs):
        response = await original(self, *args, **kwargs)
        if kwargs['task'] != 'panel_generation':
            calls.append((kwargs, response))
        return response

    monkeypatch.setattr(DeterministicMockAdapter, 'call', capture)

    async def run():
        idea = PanelService.get_presets()['devtool_ebpf']['idea']
        panel = await PanelService.generate_panel(idea)
        return await ReviewBoardOrchestrator().execute_board(idea, panel)

    session = asyncio.run(run())
    assert session.status == 'completed'
    assert {call['task'] for call, _ in calls} == {
        'specialist_review', 'challenge_generation', 'challenge_response', 'coordinator_synthesis',
    }
    for call, response in calls:
        system = call['system_prompt']
        context = json.loads(call['user_prompt'])
        assert context['request']
        assert context['idea'] == session.idea.model_dump()
        assert 'not truncation rules' in system
        assert 'no extra keys' in system
        assert 'never invent' in system
        # Every provider content field remains documented in the system schema.
        for field in RESULT_MODELS[call['task']].model_fields:
            assert f'"{field}"' in system
        RESULT_MODELS[call['task']].model_validate(response.parsed_json, strict=True)

    specialist = next(call for call, _ in calls if call['task'] == 'specialist_review')
    assert 'target' not in json.loads(specialist['user_prompt'])
    assert 'reviews' not in json.loads(specialist['user_prompt'])
    coordinator = next(call for call, _ in calls if call['task'] == 'coordinator_synthesis')
    assert 'Without evidence mark' in coordinator['system_prompt']
    assert 'retain every' in coordinator['system_prompt']
    from app.prompts.evidence_rubric import LIVE_EVIDENCE_RUBRIC
    assert LIVE_EVIDENCE_RUBRIC in coordinator['system_prompt']
    assert 'Apply every evidence sufficiency gate' in json.loads(coordinator['user_prompt'])['request']
