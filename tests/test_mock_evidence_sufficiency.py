"""The offline rating measures documented coverage, never startup success."""
from copy import deepcopy

import pytest

from app.models.connectors.mock_deliberation import _evidence


def documented_idea():
    return {
        'title': 'TraceKit Kubernetes tracing',
        'proposed_solution': 'Kubernetes tracing with below 1.5% CPU overhead',
        'evidence': [
            {'id': 'LAB-99', 'data_type': 'benchmark', 'source': 'Lab run A',
             'summary': 'Method: Kubernetes tracing tested under load; Sample: 50 workload runs; Result: measured Kubernetes tracing CPU overhead 1.18%; Limitations: synthetic workloads exclude production traffic'},
            {'id': 'CUSTOMERS', 'data_type': 'pilot', 'source': 'Customer cohort B',
             'summary': 'Method: Kubernetes tracing evaluated during onboarding; Sample: 12 customer teams; Result: observed Kubernetes tracing adoption in 8 teams; Limitations: voluntary cohort excludes nonparticipants'},
        ],
    }


def test_documented_reports_can_be_sufficient_without_claiming_validation():
    idea = documented_idea()
    original = deepcopy(idea)
    result = _evidence(idea, [])
    assert result['status'] == 'sufficient'
    assert '[LAB-99]' in result['analysis'] and '[CUSTOMERS]' in result['analysis']
    assert 'not independent evidence verification' in result['analysis']
    assert 'sufficient does not mean favorable' in result['analysis']
    assert _evidence(idea, []) == result
    assert idea == original


@pytest.mark.parametrize('change', ['duplicate_source', 'duplicate_text', 'anecdote', 'projection', 'missing_methods', 'irrelevant', 'negated', 'same_type'])
def test_count_and_labels_cannot_bypass_documentation_rubric(change):
    idea = documented_idea()
    a, b = idea['evidence']
    if change == 'duplicate_source': b['source'] = a['source']
    if change == 'duplicate_text': b['summary'] = a['summary']
    if change == 'anecdote': b['data_type'] = 'anecdote'
    if change == 'projection': b['source'] = 'Hypothetical forecast'
    if change == 'missing_methods': b['summary'] = '12 customers loved it'
    if change == 'irrelevant': b['summary'] = b['summary'].replace('Kubernetes tracing', 'dental scheduling')
    if change == 'negated': b['summary'] = b['summary'].replace('observed', 'not observed')
    if change == 'same_type': b['data_type'] = a['data_type']
    idea['evidence'] *= 4
    assert _evidence(idea, [])['status'] == 'thin'


def test_negative_measurement_is_documented_evidence_not_positive_validation():
    idea = documented_idea()
    idea['evidence'][0]['summary'] = idea['evidence'][0]['summary'].replace('1.18%', '24.5%')
    result = _evidence(idea, [])
    assert result['status'] == 'sufficient'
    assert '24.5%' in result['analysis'] and 'not below' in result['analysis']


def test_conflicting_cpu_observations_block_sufficiency():
    idea = documented_idea()
    other = deepcopy(idea['evidence'][0])
    other.update(id='CONFLICT', source='Lab C')
    other['summary'] = other['summary'].replace('1.18%', '24.5%')
    idea['evidence'].append(other)
    result = _evidence(idea, [])
    assert result['status'] == 'thin'
    assert 'conflicting measurements must be reconciled' in result['analysis']


def test_empty_evidence_remains_insufficient():
    assert _evidence({'evidence': []}, [])['status'] == 'insufficient'
