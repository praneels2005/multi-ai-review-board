"""
Tests for panel structure and dynamic variation across contrasting ideas.
Verifies that 3 to 5 specialists are generated, roles and mandates are tailored,
and different business ideas produce meaningfully different specialist mixes.
"""

import pytest
from app.schemas.review_board_schema import StartupIdeaInput, EvidenceItem
from app.services.panel_service import PanelService


@pytest.mark.anyio
async def test_panel_generation_count_and_fields():
    """Verify that generated panels contain between 3 and 5 specialists with required fields."""
    idea = StartupIdeaInput(
        title="DocuSearch",
        idea="Semantic vector search engine for enterprise PDFs and technical manuals.",
        target_customer="Enterprise engineering and support teams.",
        problem="Support engineers spend 40% of their time finding answers in legacy PDFs.",
        proposed_solution="Instant neural search with exact citation links into PDF pages.",
        evidence=[]
    )

    specialists = await PanelService.generate_panel(idea)
    assert 3 <= len(specialists) <= 5

    for spec in specialists:
        assert spec.id.startswith("spec_")
        assert len(spec.role) > 3
        assert len(spec.expertise) > 10
        assert len(spec.mandate) > 10
        assert len(spec.rationale) > 10
        assert spec.provider in ["mock", "openai", "gemini"]


@pytest.mark.anyio
async def test_contrasting_ideas_produce_different_panels():
    """Verify that two contrasting ideas produce meaningfully different specialist panels."""
    presets = PanelService.get_presets()
    idea_devtool = presets["devtool_ebpf"]["idea"]
    idea_ecommerce = presets["ecommerce_d2c"]["idea"]

    panel_dev = await PanelService.generate_panel(idea_devtool)
    panel_ecom = await PanelService.generate_panel(idea_ecommerce)

    dev_roles = [s.role.lower() for s in panel_dev]
    ecom_roles = [s.role.lower() for s in panel_ecom]

    # Verify DevTool panel has infrastructure/developer/eBPF roles
    assert any("kernel" in r or "infrastructure" in r or "developer" in r or "ebpf" in r for r in dev_roles)
    # Verify E-Commerce panel has logistics/cosmetic/retention/merchandising roles
    assert any("logistics" in r or "retention" in r or "cosmetic" in r or "supply chain" in r for r in ecom_roles)

    # Panels should share no identical specialist titles
    assert set(dev_roles).isdisjoint(set(ecom_roles))


@pytest.mark.anyio
async def test_thin_evidence_panel_structure():
    """Verify panel generation for the thin-evidence neurotech preset."""
    presets = PanelService.get_presets()
    idea_neuro = presets["thin_evidence_neuro"]["idea"]

    panel_neuro = await PanelService.generate_panel(idea_neuro)
    assert 3 <= len(panel_neuro) <= 5

    roles = [s.role.lower() for s in panel_neuro]
    assert any("neuro" in r or "sleep" in r or "hardware" in r or "fda" in r for r in roles)

