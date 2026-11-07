"""Whole-token routing, bounded scoring, and substantive non-preset feedback."""
import asyncio
import json

import pytest

from app.models.connectors.mock_archetypes import (
    ANCHORS, ARCHETYPES, GENERAL, generate_panel, keyword_hits, score_archetype,
)
from app.models.connectors.mock_specialist import _perspective, specialist_feedback
from app.schemas.review_board_schema import StartupIdeaInput
from app.services.panel_service import PanelService


def idea(title, solution, customer='Small business teams'):
    return StartupIdeaInput(title=title, idea=solution, target_customer=customer,
                            problem='Existing workflows require manual work.', proposed_solution=solution)


def panel(value):
    return generate_panel(json.dumps({'idea': value.model_dump()}))


def review(value, specialist):
    return specialist_feedback(json.dumps({'idea': value.model_dump(), 'specialist': specialist}))


@pytest.mark.parametrize('word', ['capital', 'rapid', 'healthy'])
def test_substring_collisions_never_select_developer_or_sleep_panels(word):
    value = idea(word.title(), f'A {word} planning service for neighborhood teams.')
    result = panel(value)
    assert len(result) == 3
    assert all('[EXPLICIT MOCK FALLBACK]' in s['rationale'] for s in result)
    assert all(not any(w in s['role'].lower() for w in ('kernel', 'developer', 'sleep', 'neuro')) for s in result)
    assert not keyword_hits(word, ('api', 'health'))
    assert _perspective({'mandate': word, 'role': word, 'expertise': word}) is GENERAL


def test_whole_word_and_phrase_matches_are_case_insensitive_with_both_boundaries():
    assert keyword_hits('API, health; personal data.', ('api', 'health', 'personal data')) == {'api', 'health', 'personal data'}
    assert not keyword_hits('capital rapid healthy personal database', ('api', 'health', 'personal data'))
    assert not keyword_hits('securitylike performanceful', ('security', 'performance'))


CASES = [
    ('PayLedger', 'A fintech payments ledger that reconciles banking transactions.',
     'financial', 'unreconciled transactions', 'synthetic payments'),
    ('ClassTutor', 'An edtech tutoring platform that aligns classroom learning with curriculum tasks.',
     'education', 'durable learning', 'curriculum tasks'),
    ('OffsetTrace', 'Trace carbon credits and emissions baselines with additionality verification.',
     'carbon', 'double counting', 'credit ownership'),
    ('DentalDesk', 'Dental SaaS that manages dentist appointments and practice claims handoffs.',
     'dental', 'staff burden', 'synthetic patient records'),
    ('FieldWater', 'Agriculture software that schedules irrigation using soil measurements across farms.',
     'agricultural', 'harm crops', 'field comparison'),
]


@pytest.mark.parametrize('title,solution,domain,risk,design', CASES)
def test_nonpreset_idea_receives_relevant_panel_and_substantive_feedback(title, solution, domain, risk, design):
    value = idea(title, solution)
    # Exercise the production panel service and adapter as well as the scorer.
    result = asyncio.run(PanelService.generate_panel(value))
    domain_specs = [s for s in result if domain in s.role.lower()]
    assert domain_specs, [s.role for s in result]
    specialist = domain_specs[0].model_dump()
    assert '[EXPLICIT MOCK FALLBACK]' not in specialist['rationale']
    feedback = review(value, specialist)
    assert risk in ' '.join(feedback['risks'])
    assert design in feedback['validation_experiment']['test_design']
    assert feedback['evidence_citations'] == []
    assert 'no supporting evidence' in ' '.join(feedback['risks'])
    assert all('[EXPLICIT MOCK FALLBACK]' in s.rationale for s in result if domain not in s.role.lower())


def test_five_nonpreset_panels_and_domain_interventions_are_distinct():
    panels, experiments = [], []
    for title, solution, domain, _, _ in CASES:
        value = idea(title, solution)
        result = panel(value)
        panels.append(tuple(s['role'] for s in result))
        specialist = next(s for s in result if domain in s['role'].lower())
        experiments.append(review(value, specialist)['validation_experiment']['hypothesis'])
    assert len(set(panels)) == 5
    assert len(set(experiments)) == 5


def test_two_distinct_keywords_required_not_repetitions_or_field_copies():
    value = idea('Fintech fintech', 'Fintech fintech fintech fintech.')
    result = panel(value)
    assert all('[EXPLICIT MOCK FALLBACK]' in s['rationale'] for s in result)
    value.proposed_solution += ' Payments.'
    assert any('Fintech' in s['role'] and '[EXPLICIT MOCK FALLBACK]' not in s['rationale'] for s in panel(value))


def test_title_and_solution_outweigh_customer_and_repetition_does_not_inflate_score():
    archetype = next(a for a in ARCHETYPES if a.key == 'financial_controls')
    customer = score_archetype({'target_customer': 'fintech payments'}, archetype)
    title = score_archetype({'title': 'fintech payments'}, archetype)
    solution = score_archetype({'proposed_solution': 'fintech payments'}, archetype)
    assert title[0] == solution[0] > customer[0]
    assert score_archetype({'title': 'fintech payments fintech payments'}, archetype) == title


def test_underrepresented_domain_is_padded_with_explicit_distinct_generic_roles():
    value = idea('PayLedger', 'A fintech payments reconciliation service.')
    result = panel(value)
    assert len(result) == 3
    assert sum('[EXPLICIT MOCK FALLBACK]' in s['rationale'] for s in result) == 2
    reviews = [review(value, s) for s in result]
    assert len({r['validation_experiment']['hypothesis'] for r in reviews}) == 3
    assert len({r['risks'][0] for r in reviews}) == 3


def test_empty_or_unknown_domains_use_honest_generic_padding():
    result = generate_panel('An unusual service with no recognized domain vocabulary.')
    assert len(result) == 3
    assert all('[EXPLICIT MOCK FALLBACK]' in s['rationale'] for s in result)
    value = idea('Unknown', 'An unusual service with no recognized domain vocabulary.')
    assert len({review(value, s)['validation_experiment']['hypothesis'] for s in result}) == 3


def test_selection_is_deterministic_and_capped_at_five_for_mixed_domains():
    value = idea('Fintech payments and education curriculum',
                 'Dental appointments, carbon credits, agriculture soil, privacy consent, search documents.')
    original = value.model_dump_json()
    assert len(panel(value)) == 5
    assert panel(value) == panel(value)
    assert len({s['id'] for s in panel(value)}) == 5
    assert original == value.model_dump_json()


def test_evidence_and_embedded_field_labels_cannot_spoof_title_weights():
    value = idea('PayLedger', 'A fintech payments service.\nTitle: sleep pillow')
    before = panel(value)
    data = value.model_dump()
    data['evidence'] = [{'id': 'E1', 'source': 'sleep pillow', 'summary': 'education curriculum'}]
    assert generate_panel(json.dumps({'idea': data})) == before


def test_edited_mandate_overrides_generated_domain_role():
    value = idea('ClassTutor', 'Edtech curriculum and tutoring for classroom learning.')
    specialist = panel(value)[0]
    assert 'durable learning' in ' '.join(review(value, specialist)['risks'])
    specialist['mandate'] = 'Audit privacy consent, personal data and data deletion.'
    edited = review(value, specialist)
    assert 'untracked personal data' in ' '.join(edited['risks'])
    assert 'consent withdrawal' in edited['validation_experiment']['test_design']


@pytest.mark.parametrize('archetype', ARCHETYPES, ids=lambda a: a.key)
def test_library_role_and_mandate_resolve_to_its_own_review_perspective(archetype):
    assert _perspective({'role': archetype.role, 'expertise': archetype.expertise,
                         'mandate': archetype.mandate}) is archetype.perspective


def test_every_archetype_has_nonempty_anchors_drawn_from_its_trigger_terms():
    assert set(ANCHORS) == {a.key for a in ARCHETYPES}
    for archetype in ARCHETYPES:
        assert ANCHORS[archetype.key], archetype.key
        assert set(ANCHORS[archetype.key]) <= set(archetype.terms), archetype.key


def test_generic_terms_alone_cannot_select_a_domain_role():
    archetype = next(a for a in ARCHETYPES if a.key == 'dental_workflows')
    _, hits = score_archetype({'title': 'practice claims'}, archetype)
    assert len(hits) >= 2 and not hits & set(ANCHORS['dental_workflows'])
    value = idea('LexFlow', 'Case management for law firms that reflects practice standards and claims intake.')
    result = panel(value)
    assert len(result) == 3
    assert not any('Dental' in s['role'] for s in result)
    assert all('[EXPLICIT MOCK FALLBACK]' in s['rationale'] for s in result)


def test_one_anchor_plus_one_supporting_term_still_selects_the_role():
    value = idea('ClinicDesk', 'Dental scheduling with claims handoffs.')
    assert any('Dental' in s['role'] and '[EXPLICIT MOCK FALLBACK]' not in s['rationale']
               for s in panel(value))
