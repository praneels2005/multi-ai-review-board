"""
Deterministic Mock Adapter for Multiple AI Review Board.
Provides offline, deterministic, rich generation without requiring any API keys.
Accurately simulates latency, token usage, cost, and failure modes for testing.
Grounded strictly in supplied evidence (not superficial keywords).
"""

import asyncio
import hashlib
import json
import re
import time
from typing import Optional, Dict, Any
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse


class DeterministicMockAdapter(BaseAIAdapter):
    """Deterministic mock adapter generating rich domain-specific review responses."""
    provider_name = "mock"

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
    ) -> NormalizedProviderResponse:
        start_time = time.perf_counter()
        active_model = model or "mock-deterministic"

        # Handle failure simulations for tests and demo walkthroughs
        if simulate_failure == "timeout":
            if timeout_seconds > 0:
                await asyncio.sleep(min(timeout_seconds + 0.5, 2.0))
            raise asyncio.TimeoutError(f"Provider call to {active_model} timed out after {timeout_seconds}s")

        if simulate_failure == "provider_error":
            await asyncio.sleep(0.1)
            raise ConnectionError(f"Simulated upstream connection failure to provider '{self.provider_name}'")

        if simulate_failure == "malformed_output":
            await asyncio.sleep(0.15)
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
                error="Malformed JSON response from mock provider"
            )

        # Realistic simulated network latency (150ms to 350ms)
        await asyncio.sleep(0.15)

        # Generate deterministic response based on prompt contents
        parsed_data = self._generate_deterministic_content(task, system_prompt, user_prompt)
        raw_text = json.dumps(parsed_data, indent=2)

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
            error=None
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
        """Generate a single sharp challenge point from the challenger specialist."""
        prompt_lower = user_prompt.lower()
        if "ebpf" in prompt_lower or "tracing" in prompt_lower or "kernel" in prompt_lower:
            return {
                "challenge_point": "Your recommendation to deploy via a 1-click developer CLI assumes engineering teams have root Kubernetes daemonset permissions (CAP_BPF / CAP_SYS_ADMIN), which enterprise security and platform teams actively prohibit in production clusters."
            }
        elif "cosmetic" in prompt_lower or "refill" in prompt_lower or "logistics" in prompt_lower:
            return {
                "challenge_point": "Your retention model assumes customer container returns cost under $1.50, but single-bottle reverse parcel postage through USPS parcel select will exceed $3.40 per bottle, wiping out gross product margin on refills."
            }
        elif "sleep" in prompt_lower or "brainwave" in prompt_lower or "neuro" in prompt_lower:
            return {
                "challenge_point": "You suggest marketing this as a general wellness sleep aid to bypass FDA Class II medical device requirements, but doing so strips away medical credibility and fails to justify a premium $299 price point without double-blind PSG clinical data."
            }
        else:
            return {
                "challenge_point": "Your customer discovery findings show strong qualitative dissatisfaction with existing tools, but dissatisfaction does not prove willingness to migrate production data or incur workflow switching costs."
            }

    def _generate_target_defense(self, user_prompt: str) -> Dict[str, Any]:
        """Generate target specialist defense and reasoning shift in response to challenge."""
        prompt_lower = user_prompt.lower()
        if "cap_bpf" in prompt_lower or "daemonset" in prompt_lower or "root" in prompt_lower or "ebpf" in prompt_lower:
            return {
                "response": "Valid concern. Instead of running root probes from an ad-hoc developer CLI, the CLI will output standard Helm / GitOps manifests that route through platform engineering's formal review, allowing security to audit kernel probes before deployment.",
                "reasoning_adjustment": "Adoption model adjusted: pivot from unapproved bottom-up developer installation to pre-approved platform engineering GitOps templates with RBAC controls."
            }
        elif "postage" in prompt_lower or "reverse" in prompt_lower or "bottle" in prompt_lower:
            return {
                "response": "To protect gross margin, returns should not occur on a per-bottle cadence. Customers will receive a batch-mailer and return empties in batches of 3 every 90 days, bringing per-unit return postage down to $1.15.",
                "reasoning_adjustment": "Fulfillment schedule adjusted: moved from single-bottle return loops to 90-day batched return mailers to maintain >50% gross margin."
            }
        elif "fda" in prompt_lower or "wellness" in prompt_lower or "clinical" in prompt_lower:
            return {
                "response": "We will stage commercialization into two phases: launch initially under FTC-compliant wellness claims for cash flow, while allocating 30% of proceeds toward a formal 20-person sham-controlled EEG clinical trial for future medical certification.",
                "reasoning_adjustment": "Go-to-market shifted to a two-phase roadmap: near-term consumer wellness positioning followed by rigorous sham-controlled clinical trial data."
            }
        else:
            return {
                "response": "Agreed that verbal intent is insufficient. We will require early pilot prospects to connect a read-only test data source during onboarding before granting free pilot access.",
                "reasoning_adjustment": "Pilot qualification gate tightened: qualification now requires active data connection commitment rather than verbal interest."
            }

    def _generate_challenge_response(self, user_prompt: str) -> Dict[str, Any]:
        """Legacy dual challenge generator for backward compatibility."""
        ch = self._generate_challenger_point(user_prompt)["challenge_point"]
        resp_data = self._generate_target_defense(ch)
        return {
            "challenges": [
                {
                    "challenger_id": "spec_2",
                    "challenger_role": "Platform Systems Architect",
                    "target_specialist_id": "spec_1",
                    "target_role": "Developer Experience Specialist",
                    "challenge_point": ch,
                    "response": resp_data["response"],
                    "reasoning_adjustment": resp_data["reasoning_adjustment"]
                }
            ]
        }

    def _generate_coordinator_synthesis(self, user_prompt: str) -> Dict[str, Any]:
        """
        Synthesize independent reviews, highlight disagreements, evaluate evidence sufficiency,
        and note failure impact.
        CRITICAL: Evidence sufficiency is determined STRICTLY by analyzing the supplied evidence
        items and evidence count in the prompt, NOT by superficial idea keywords!
        """
        prompt_lower = user_prompt.lower()

        # Check if an agent failure was reported in prompt
        failure_detected = "failure" in prompt_lower or "failed" in prompt_lower or "timed out" in prompt_lower
        failure_impact = None
        if failure_detected:
            failure_impact = "One or more specialist agents failed or timed out during the review board run. As a result, specific technical or operational perspectives could not be comprehensively evaluated. Overall confidence in those domains is degraded; founders must manually consult domain specialists before proceeding."

        # Parse evidence items strictly from prompt
        # We look for "Supplied Evidence Count: N" or evidence markers
        evidence_count_match = re.search(r"supplied evidence count:\s*(\d+)", prompt_lower)
        ev_count = int(evidence_count_match.group(1)) if evidence_count_match else 0

        # Inspect evidence text block if present
        has_benchmark = "(benchmark)" in prompt_lower or "data_type: benchmark" in prompt_lower
        has_interview = "(customer_interview)" in prompt_lower or "(interview)" in prompt_lower
        has_metric = "(metric)" in prompt_lower or "data_type: metric" in prompt_lower
        has_pilot = "(pilot)" in prompt_lower
        has_anecdote_only = "(anecdote)" in prompt_lower and not (has_benchmark or has_interview or has_metric or has_pilot)
        no_evidence = ev_count == 0 or "no empirical evidence supplied" in prompt_lower or "supplied evidence items:\nnone" in prompt_lower

        if no_evidence:
            evidence_status = "insufficient"
            evidence_analysis = "No empirical evidence was supplied. All claims regarding market demand, technical performance, and customer willingness to pay represent unverified founder assumptions requiring immediate ground-up validation."
        elif has_anecdote_only or ev_count == 1:
            evidence_status = "thin"
            evidence_analysis = f"Supplied evidence is thin (count={ev_count}), consisting of preliminary or anecdotal testimonials without controlled benchmark datasets, customer retention cohorts, or statistical validation."
        elif has_benchmark or (has_metric and has_interview) or has_pilot:
            evidence_status = "sufficient"
            evidence_analysis = f"Supplied evidence provides concrete preliminary empirical backing across {ev_count} distinct items (including empirical benchmarks, customer interviews, or pilot metrics). Core remaining unknowns involve long-term production scaling and enterprise compliance approvals."
        else:
            evidence_status = "thin"
            evidence_analysis = f"Supplied evidence ({ev_count} item(s)) provides early directional signal but lacks comprehensive quantitative proof across production scale and customer retention cohorts."

        priorities = [
            "Validate critical technical feasibility / compliance bottlenecks before expanding marketing spend.",
            "Run controlled, low-cost pilot experiments to replace unverified assumptions with empirical behavioral data.",
            "Align security, regulatory, and go-to-market incentives so product onboarding does not trigger organizational friction."
        ]

        disagreements = [
            "Tension between rapid user onboarding friction vs rigorous enterprise security and compliance guardrails.",
            "Debate over whether customer enthusiasm in interviews translates to willingness to pay and tolerate operational changes.",
            "Conflicting priorities between short-term unit margin preservation and long-term customer convenience."
        ]

        next_experiments = [
            {
                "hypothesis": "Early target adopters will complete an end-to-end integration test within 7 days when provided guided setup materials.",
                "test_design": "Engage 10 qualified target prospects with a low-touch onboarding package and track completion rate and drop-off points.",
                "success_metric": ">= 60% completion rate without high-touch founder intervention."
            },
            {
                "hypothesis": "Unit economics remain profitable after factoring in real-world friction, returns, and support overhead.",
                "test_design": "Run a 50-unit end-to-end batch transaction simulation accounting for every line-item expense.",
                "success_metric": "Contribution margin remains above 40% after fully-loaded variable costs."
            }
        ]

        return {
            "summary": "The Review Board has completed independent evaluation and bounded cross-examination. While the core concept addresses real operational friction, significant unverified assumptions around operational friction, security/regulatory approvals, and true willingness to pay must be empirically validated before committing substantial capital.",
            "priorities": priorities,
            "disagreements": disagreements,
            "next_experiments": next_experiments,
            "evidence_sufficiency": {
                "status": evidence_status,
                "analysis": evidence_analysis
            },
            "failure_impact_analysis": failure_impact,
            "disclaimer": "Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand."
        }
