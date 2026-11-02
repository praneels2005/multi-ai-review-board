"""
Panel Service for Multiple AI Review Board.
Generates 3 to 5 domain-specific specialist agents for any startup idea,
and supplies curated contrasting presets for demonstration and testing.
"""

import json
from typing import List, Dict, Any
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    EvidenceItem,
    SpecialistAgentConfig,
)
from app.models.connectors.factory import get_provider_adapter


PANEL_GENERATION_SYSTEM_PROMPT = """You are an expert startup advisor and panel chair.
Your task is to assemble a rigorous, bespoke panel of 3 to 5 specialist agents to review a startup idea.
The specialists MUST be tightly customized to the idea's specific technical, business, regulatory, and market domain.
Do NOT reuse generic roles (e.g. do NOT simply output 'Marketing Lead', 'Finance Person', 'Tech Lead').
Instead, use precise, domain-specific titles (e.g. 'eBPF Kernel Architect', 'Cosmetics Formulation & FDA Compliance Officer', 'Reverse Logistics Director').

Respond ONLY with a JSON object of this exact schema:
{
  "specialists": [
    {
      "id": "spec_1",
      "role": "<Domain-Specific Specialist Title>",
      "expertise": "<Detailed description of relevant domain expertise>",
      "mandate": "<Specific review mandate and key critical questions they must evaluate>",
      "rationale": "<Why the idea critically needs this specific perspective>",
      "provider": "mock",
      "model": "mock-deterministic"
    }
  ]
}
"""


class PanelService:
    """Service to create, customize, and supply specialist panels."""

    @staticmethod
    async def generate_panel(
        idea_input: StartupIdeaInput,
        provider: str = "mock",
        model: str = "mock-deterministic"
    ) -> List[SpecialistAgentConfig]:
        """Generate 3 to 5 tailored specialist agents for the provided startup idea."""
        adapter = get_provider_adapter(provider)

        evidence_summary = "\n".join([f"- [{e.id}] ({e.data_type}) {e.summary} (Source: {e.source})" for e in idea_input.evidence]) or "No empirical evidence supplied."

        user_prompt = f"""Generate a panel of 3 to 5 specialist agents to review this startup idea:
Title: {idea_input.title}
Target Customer: {idea_input.target_customer}
Problem: {idea_input.problem}
Proposed Solution: {idea_input.proposed_solution}
Idea Description: {idea_input.idea}
Supplied Evidence:
{evidence_summary}
"""

        response = await adapter.call(
            system_prompt=PANEL_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=model,
            timeout_seconds=15.0
        )

        specialists: List[SpecialistAgentConfig] = []
        parsed = response.parsed_json or {}
        raw_specs = parsed.get("specialists", [])

        if not raw_specs or len(raw_specs) < 3:
            # Fallback to deterministic generation if parsing failed or fewer than 3 generated
            mock_adapter = get_provider_adapter("mock")
            fallback_res = await mock_adapter.call(
                system_prompt=PANEL_GENERATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model="mock-deterministic"
            )
            raw_specs = (fallback_res.parsed_json or {}).get("specialists", [])

        for idx, s in enumerate(raw_specs[:5]):
            spec_id = s.get("id") or f"spec_{idx+1}"
            specialists.append(SpecialistAgentConfig(
                id=spec_id,
                role=s.get("role", f"Domain Specialist {idx+1}"),
                expertise=s.get("expertise", "Relevant industry and technical domain expertise."),
                mandate=s.get("mandate", "Scrutinize assumptions and identify operational failure risks."),
                rationale=s.get("rationale", "Provides necessary specialized perspective for this business model."),
                provider="mock",
                model="mock-deterministic"
            ))

        return specialists

    @staticmethod
    def get_presets() -> Dict[str, Dict[str, Any]]:
        """Return curated contrasting startup ideas with evidence and preconfigured panels."""
        return {
            "devtool_ebpf": {
                "name": "Contrasting Idea A: DevPulse (B2B Infrastructure / DevTool)",
                "description": "High technical complexity, sub-2% eBPF kernel profiling with benchmark and interview evidence.",
                "idea": StartupIdeaInput(
                    title="DevPulse - Continuous eBPF Tracing & Distributed Profiler",
                    idea="A low-overhead, kernel-level distributed tracing and APM platform built on Linux eBPF. It provides complete microservice latency graphs and CPU profiling across Kubernetes clusters with zero code instrumentation, eliminating manual OpenTelemetry SDK maintenance.",
                    target_customer="Platform Engineering Leads, DevOps Architects, and Cloud Infrastructure VPs at growth-stage SaaS companies (50-500 engineers).",
                    problem="Modern microservices incur 8-15% CPU overhead when running traditional user-space APM agents (Datadog/Dynatrace), while engineering teams waste hundreds of hours updating manual tracing SDKs across polyglot microservice repos.",
                    proposed_solution="A single privileged DaemonSet deploying pre-compiled eBPF CO-RE probes to inspect Linux kernel socket buffers and schedulers, generating distributed span traces with < 1.5% CPU overhead.",
                    evidence=[
                        EvidenceItem(
                            id="E1",
                            source="Internal Synthetic Benchmark on 50-node AWS EKS cluster (c6g.2xlarge)",
                            summary="eBPF agent recorded 1.18% average CPU overhead and 38MB RAM footprint under sustained 25,000 req/sec synthetic HTTP workload.",
                            data_type="benchmark"
                        ),
                        EvidenceItem(
                            id="E2",
                            source="Customer Discovery Interviews (n=12 Platform Leads)",
                            summary="10 of 12 platform leads cited Datadog egress and host bill fatigue as a top-3 cost grievance and actively seek zero-instrumentation alternatives.",
                            data_type="customer_interview"
                        )
                    ]
                )
            },
            "ecommerce_d2c": {
                "name": "Contrasting Idea B: GlowGreen (Consumer E-Commerce / Circular Refills)",
                "description": "Direct-to-consumer physical goods with reverse logistics, cosmetic regulation, and customer return loops.",
                "idea": StartupIdeaInput(
                    title="GlowGreen - Closed-Loop Refillable Skincare Subscription",
                    idea="A direct-to-consumer clean skincare brand utilizing heavy weighted aluminum refillable bottles. Customers subscribe to daily cleansers and serums, receiving concentrated refill pouches and prepaid return envelopes to mail back empties for industrial sanitization and reuse.",
                    target_customer="Eco-conscious millennial and Gen Z consumers (aged 24-38) who regularly spend $40+ per month on skincare and express strong climate values.",
                    problem="The beauty and personal care industry generates over 120 billion units of non-recyclable plastic packaging per year. Sustainable alternatives are often ugly, messy to refill, or lack premium skincare active formulations.",
                    proposed_solution="A closed-loop subscription service where customers receive aesthetic, durable anodized aluminum pump bottles, and return empty refill pouches via USPS mailers with deposit return incentives.",
                    evidence=[
                        EvidenceItem(
                            id="E1",
                            source="Meta/TikTok Paid Ads Test Campaign ($1,200 spend)",
                            summary="Acquired 540 email waitlist signups at $2.22 blended CPA with a 6.4% landing page conversion rate on the refillable concept.",
                            data_type="metric"
                        ),
                        EvidenceItem(
                            id="E2",
                            source="Austin Local Pilot Cohort (n=50 users over 60 days)",
                            summary="42% of pilot participants physically returned their empties within 45 days when provided with prepaid mailers, revealing customer drop-off friction.",
                            data_type="pilot"
                        )
                    ]
                )
            },
            "thin_evidence_neuro": {
                "name": "Thin-Evidence Case: QuantumSleep (Consumer Hardware / Neurotech)",
                "description": "Bold medical/neurotech claims with zero clinical trials or peer-reviewed empirical evidence.",
                "idea": StartupIdeaInput(
                    title="QuantumSleep - Brainwave Entraining Acoustic Sleep Pillow",
                    idea="A memory foam sleeping pillow with embedded bone-conduction piezo-transducers that pulse sub-audible delta-wave binaural beats to entrain neural oscillations into restorative deep stage-3 NREM sleep, curing chronic sleep disturbances.",
                    target_customer="Adults suffering from sleep onset latency, chronic fatigue, and tech-forward biohackers willing to pay $299 for hardware sleep interventions.",
                    problem="Over 70 million Americans report chronic sleep issues. Prescription sedatives alter sleep architecture and cause dependence, while passive sleep trackers do nothing to actively induce sleep.",
                    proposed_solution="An ergonomic pillow that uses real-time acoustic neural entrainment to lock brainwaves into 0.5-4 Hz delta frequencies within 15 minutes of head contact.",
                    evidence=[
                        EvidenceItem(
                            id="E1",
                            source="Founder Personal Sleep Diary (n=1)",
                            summary="Founder self-reported falling asleep in 12 minutes rather than 45 minutes across 14 consecutive nights of personal prototype testing.",
                            data_type="anecdote"
                        )
                    ]
                )
            }
        }

