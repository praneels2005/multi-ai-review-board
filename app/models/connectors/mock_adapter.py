"""
Deterministic Mock Adapter for Multiple AI Review Board.
Provides offline, deterministic, rich generation without requiring any API keys.
Accurately simulates latency, token usage, cost, and failure modes for testing.
Grounded strictly in supplied evidence (not superficial keywords).
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse
from app.models.connectors.execution_usage import ProviderCallError, ProviderTimeoutError, usage_counts, exception_usage, conservative_tokens


class DeterministicMockAdapter(BaseAIAdapter):
    """Deterministic mock adapter generating rich domain-specific review responses."""
    provider_name = "mock"

    def estimate_input_tokens(self, system_prompt, user_prompt):
        # Exact input count for the mock's defined simulated tokenizer.
        return len(system_prompt + user_prompt) // 4

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = "mock-deterministic",
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
        *,
        task: AITask = "specialist_review",
        max_output_tokens: int = 4096,
    ) -> NormalizedProviderResponse:
        start_time = time.perf_counter()
        active_model = model or "mock-deterministic"

        # Handle failure simulations for tests and demo walkthroughs
        if simulate_failure == "timeout":
            if timeout_seconds > 0:
                await asyncio.sleep(timeout_seconds)
            raise ProviderTimeoutError(f"Mock call to {active_model} timed out after {timeout_seconds}s; local simulation stopped", request_sent=False)

        if simulate_failure == "provider_error":
            await asyncio.sleep(min(0.1, timeout_seconds / 2))
            raise ProviderCallError(f"Simulated upstream connection failure to provider '{self.provider_name}'", retryable=True, request_sent=False)

        if simulate_failure == "malformed_output":
            await asyncio.sleep(min(0.15, timeout_seconds / 2))
            malformed_text = '{"status": "incomplete", "strengths": ["Premature closure", "error": syntax_error'
            latency = (time.perf_counter() - start_time) * 1000
            return NormalizedProviderResponse(
                raw_text=malformed_text,
                parsed_json=None,
                provider=self.provider_name,
                model=active_model,
                is_simulated=True,
                latency_ms=round(latency, 2),
                input_tokens=150,
                output_tokens=30,
                total_tokens=180,
                cost_estimate_usd=self.calculate_cost(self.provider_name, active_model, 150, 30),
                usage_source="simulated",
                error="malformed_json: Malformed JSON response from mock provider"
            )

        # Realistic simulated network latency (150ms to 350ms)
        await asyncio.sleep(min(0.15, timeout_seconds / 2))

        # Generate deterministic response based on prompt contents
        parsed_data = self._generate_deterministic_content(task, system_prompt, user_prompt)
        raw_text = json.dumps(parsed_data, indent=2)
        parsed_data, output_error = self.parse_output(raw_text, task)

        latency = (time.perf_counter() - start_time) * 1000
        input_tokens = len(system_prompt + user_prompt) // 4
        output_tokens = len(raw_text) // 4
        total_tokens = input_tokens + output_tokens
        cost = self.calculate_cost(self.provider_name, active_model, input_tokens, output_tokens)

        return NormalizedProviderResponse(
            raw_text=raw_text,
            parsed_json=parsed_data,
            provider=self.provider_name,
            model=active_model,
            is_simulated=True,
            latency_ms=round(latency, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_estimate_usd=cost,
            usage_source="simulated",
            error=output_error
        )

    def _generate_deterministic_content(
        self, task: AITask, system_prompt: str, user_prompt: str
    ) -> Dict[str, Any]:
        """Select the operation from trusted caller metadata, never prompt text."""
        if task == "panel_generation":
            return self._generate_panel(user_prompt)
        if task == "specialist_review":
            return self._generate_specialist_feedback(system_prompt, user_prompt)
        if task == "challenge_generation":
            return self._generate_challenger_point(user_prompt)
        if task == "challenge_response":
            return self._generate_target_defense(user_prompt)
        if task == "coordinator_synthesis":
            return self._generate_coordinator_synthesis(user_prompt)
        raise ValueError(f"Unsupported AI task: {task!r}")

    def _generate_panel(self, user_prompt: str) -> Dict[str, Any]:
        """Generate domain-relevant specialists depending on startup type."""
        prompt_lower = user_prompt.lower()

        # DevTool / Infrastructure idea
        if any(w in prompt_lower for w in ["ebpf", "kubernetes", "k8s", "tracing", "profiler", "developer", "infra", "devtool", "api", "database"]):
            specialists = [
                {
                    "id": "spec_1",
                    "role": "Developer Experience & CLI Usability Specialist",
                    "expertise": "Developer onboarding friction, SDK ergonomics, CLI workflows, and engineering team adoption.",
                    "mandate": "Evaluate whether developers will willingly adopt and maintain this tool, assess configuration overhead, and review local-to-cloud workflows.",
                    "rationale": "Developer tools fail primarily on initial friction; dev-ex review ensures workflow friction does not kill bottom-up adoption.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_2",
                    "role": "Cloud Infrastructure & Kernel Systems Architect",
                    "expertise": "eBPF kernel telemetry, Linux observability, CPU/memory overhead, and large-scale Kubernetes clustering.",
                    "mandate": "Scrutinize runtime overhead claims, node-level security privileges, Linux kernel compatibility, and agent footprint.",
                    "rationale": "Enterprise platform teams will reject observability agents that add latency or introduce kernel instability.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_3",
                    "role": "DevSecOps & Compliance Auditor",
                    "expertise": "Production host security, privileged daemonsets, SOC2, HIPAA compliance, and telemetry data redaction.",
                    "mandate": "Assess risks of root access / privileged daemonset deployment and sensitive data exfiltration in production traces.",
                    "rationale": "Enterprise CISOs block observability tools that request excessive container capabilities without verification.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_4",
                    "role": "Open-Core & Enterprise GTM Strategist",
                    "expertise": "Open-core monetization, buyer vs user persona dynamics, competitive displacement against Datadog/Dynatrace.",
                    "mandate": "Evaluate pricing tiers, willingness to pay from VP/Director buyers, and defense against legacy observability incumbents.",
                    "rationale": "High developer love must translate into a scalable enterprise contract model with clear buyer value.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                }
            ]
        # Consumer D2C / Sustainability / E-Commerce
        elif any(w in prompt_lower for w in ["cosmetic", "refill", "sustainable", "ecommerce", "d2c", "beauty", "consumer", "waste", "fashion", "packaging"]):
            specialists = [
                {
                    "id": "spec_1",
                    "role": "Sustainable Supply Chain & Reverse Logistics Specialist",
                    "expertise": "Closed-loop circular packaging, return shipping logistics, wash/sterilization facility operations, and carton lifecycle.",
                    "mandate": "Analyze unit costs and friction of customer container returns, sanitation compliance, and breakage/loss rates in transit.",
                    "rationale": "Refillable models collapse when return logistics costs exceed the savings of reusable packaging.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_2",
                    "role": "D2C Retention & Customer Lifecycle Strategist",
                    "expertise": "Subscription churn modeling, cohort retention, unboxing behavior, and paid customer acquisition payback.",
                    "mandate": "Evaluate churn risk at 90 days, customer willingness to complete physical return loops, and LTV-to-CAC ratios.",
                    "rationale": "D2C brands live and die by repeat purchase rates; physical friction in returning empties often causes subscription cancellations.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_3",
                    "role": "Cosmetic Formulation & FDA Regulatory Compliance Officer",
                    "expertise": "FDA cosmetic safety, stability testing in refill containers, preservative efficacy, and MoCRA regulation standards.",
                    "mandate": "Assess microbial contamination risks during customer refills and compliance with US MoCRA labelling and safety requirements.",
                    "rationale": "Refilled bottles run contamination risks that can trigger FDA recalls or severe liability without preservative stability.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_4",
                    "role": "Unit Economics & Packaging Procurement Analyst",
                    "expertise": "Bill of materials (BOM), custom aluminum/glass mold costs, shipping tare weight, and gross margin optimization.",
                    "mandate": "Audit gross margin after accounting for two-way shipping, packaging depreciation, and return sanitization labor.",
                    "rationale": "Circular products often suffer from hidden operational labor that drains gross margins below 50%.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                }
            ]
        # Thin Evidence / Health / Hardware / Neurotech
        elif any(w in prompt_lower for w in ["sleep", "brainwave", "eeg", "neuro", "quantum", "medical", "health", "pillow", "headband", "acoustic"]):
            specialists = [
                {
                    "id": "spec_1",
                    "role": "Neurobiology & Sleep Medicine Researcher",
                    "expertise": "EEG polysomnography, acoustic binaural stimulation, circadian rhythm physiology, and sleep architecture (REM/NREM).",
                    "mandate": "Scrutinize scientific plausibility of acoustic brainwave entrainment through sleep surfaces, demand peer-reviewed citations.",
                    "rationale": "Consumer sleep aids frequently make claims unsupported by double-blind clinical trials.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_2",
                    "role": "Consumer Hardware & Ergonomics Engineer",
                    "expertise": "Transducer acoustic integration, washable foam textiles, thermal dissipation, battery safety, and wearability.",
                    "mandate": "Examine thermal dissipation, transducer comfort during side-sleeping, and machine-washable mechanical durability.",
                    "rationale": "Hardware in bedding faces extreme comfort constraints and sweat/washing degradation.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_3",
                    "role": "FDA Regulatory & Health Claims Attorney",
                    "expertise": "FDA 510(k) wellness exemptions vs Class II medical device classification, FTC advertising truth-in-claims standards.",
                    "mandate": "Identify high-risk disease treatment claims (insomnia/apnea) versus general wellness wording, evaluate recall liability.",
                    "rationale": "Unsubstantiated therapeutic sleep claims draw immediate FTC and FDA warning letters.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                }
            ]
        # General B2B / SaaS default
        else:
            specialists = [
                {
                    "id": "spec_1",
                    "role": "Product-Market Fit & Customer Discovery Specialist",
                    "expertise": "User persona interviews, ICP validation, pain severity quantification, and workflow substitution analysis.",
                    "mandate": "Evaluate whether the target problem represents a top-3 critical pain point or an optional nice-to-have.",
                    "rationale": "Most software startups fail because users do not feel sufficient urgency to abandon existing habits.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_2",
                    "role": "Systems Architecture & Technical Feasibility Lead",
                    "expertise": "Scalable cloud infrastructure, data pipelines, third-party API dependencies, and reliability engineering.",
                    "mandate": "Probe feasibility bottlenecks, vendor lock-in risks, and maintenance complexity at production scale.",
                    "rationale": "Early architectures often accumulate debt that derails rapid product iteration.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                },
                {
                    "id": "spec_3",
                    "role": "GTM & Competitive Differentiation Strategist",
                    "expertise": "Customer acquisition channels, competitive positioning against market incumbents, pricing and packaging.",
                    "mandate": "Analyze competitive moats, pricing resistance, and channel scalability.",
                    "rationale": "A strong product cannot succeed without sustainable customer distribution.",
                    "provider": "mock",
                    "model": "mock-deterministic"
                }
            ]

        return {"specialists": specialists}

    def _generate_specialist_feedback(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_specialist import specialist_feedback
        return specialist_feedback(user_prompt)

    def _generate_challenger_point(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import challenge
        return challenge(user_prompt)

    def _generate_target_defense(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import respond
        return respond(user_prompt)

    def _generate_coordinator_synthesis(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import synthesize
        return synthesize(user_prompt)
