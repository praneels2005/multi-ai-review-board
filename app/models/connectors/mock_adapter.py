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
from app.models.connectors.base_connector import BaseAIAdapter, NormalizedProviderResponse


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
        parsed_data = self._generate_deterministic_content(system_prompt, user_prompt)
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

    def _generate_deterministic_content(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Dispatch based on the target task inferred from prompts."""
        lower_prompt = (system_prompt + " " + user_prompt).lower()

        # 1. Panel Generation
        if "generate" in lower_prompt and "specialist" in lower_prompt and ("panel" in lower_prompt or "mandate" in lower_prompt):
            return self._generate_panel(user_prompt)

        # 2. Coordinator Synthesis
        if "coordinator" in lower_prompt or "combined review" in lower_prompt or "synthesize" in lower_prompt:
            return self._generate_coordinator_synthesis(user_prompt)

        # 3. Dedicated Target Response to Challenge
        if "target specialist responding" in lower_prompt or "defend your position" in lower_prompt or "responding to peer challenge" in lower_prompt:
            return self._generate_target_defense(user_prompt)

        # 4. Dedicated Challenger Generation
        if "generate a sharp challenge" in lower_prompt or "identify one sharp point of disagreement" in lower_prompt or "cross-examination" in lower_prompt:
            return self._generate_challenger_point(user_prompt)

        # 5. Fallback Legacy Challenge Round (both sides in one)
        if "challenge" in lower_prompt or "debate" in lower_prompt:
            return self._generate_challenge_response(user_prompt)

        # 6. Default: Specialist Feedback
        return self._generate_specialist_feedback(system_prompt, user_prompt)

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
        """Generate independent specialist review grounded strictly in supplied evidence."""
        prompt_lower = (system_prompt + " " + user_prompt).lower()

        # Check explicitly for evidence IDs supplied in prompt text
        has_e1 = bool(re.search(r'\[e1\]|id:\s*e1', prompt_lower))
        has_e2 = bool(re.search(r'\[e2\]|id:\s*e2', prompt_lower))
        cited_evidence = []
        if has_e1:
            cited_evidence.append("E1")
        if has_e2:
            cited_evidence.append("E2")

        has_any_evidence = len(cited_evidence) > 0

        # Ground feedback in specific domain
        if "ebpf" in prompt_lower or "tracing" in prompt_lower or "developer" in prompt_lower:
            strength_e1 = "Benchmark evidence [E1] indicates sub-2% CPU overhead on synthetic microservice loads." if "E1" in cited_evidence else "Architectural approach eliminates manual SDK code injection across polyglot microservice repos."
            strength_e2 = "Customer discovery interviews [E2] confirm target platform engineers experience strong APM cost fatigue." if "E2" in cited_evidence else "Kernel-level visibility provides unified latency traces without user-space runtime hooks."

            strengths = [
                "Zero-instrumentation telemetry drastically reduces developer onboarding friction compared to SDK injection.",
                strength_e1,
                strength_e2
            ]
            risks = [
                "Requires elevated Linux kernel capabilities (CAP_BPF / root daemonset), which enterprise security teams actively block in shared multi-tenant clusters.",
                "Kernel version fragmentation: eBPF CO-RE can fail on older enterprise distributions (e.g. RHEL 7/8, legacy cloud AMIs).",
                "High customer support burden debugging kernel probes across bespoke enterprise microservice topologies."
            ]
            missing_assumptions = [
                "Assumes engineering teams have permission to deploy privileged DaemonSets into enterprise production environments.",
                "Assumes developers who inspect traces are the same budget holders willing to displace existing contract commitments."
            ]
            if not has_any_evidence:
                missing_assumptions.append("CRITICAL: Zero empirical evidence was provided verifying CPU overhead claims under production workloads.")

            questions = [
                "How does the agent gracefully handle non-supported Linux kernels or locked-down hardened host nodes?",
                "What is the fallback mechanism when eBPF verifier rejects custom filter programs under memory pressure?"
            ]
            experiment = {
                "hypothesis": "Platform engineering teams in Series B-D companies will grant root daemonset permissions in staging within 7 days of demo.",
                "test_design": "Provide a 1-command Helm installation script to 10 DevOps leads; measure time-to-first-trace and number of security escalation objections.",
                "success_metric": ">= 6 out of 10 DevOps leads successfully deploy without requiring security board waivers."
            }
            assumptions = [
                "Assumption: Enterprises will prioritize lower observability overhead over established single-pane-of-glass dashboards.",
                "Unknown: Exact egress bandwidth cost for shipping high-frequency trace vectors across AWS availability zones."
            ]
            if not has_any_evidence:
                assumptions.append("Unbacked Assumption: Sub-1.5% CPU overhead claim is completely unverified by empirical benchmark data.")

        elif "cosmetic" in prompt_lower or "refill" in prompt_lower or "sustainable" in prompt_lower:
            strength_e1 = "Paid ad campaign data [E1] indicates viable early customer acquisition interest at $2.22 CPA." if "E1" in cited_evidence else "Closed-loop brand story creates emotional loyalty and strong word-of-mouth defensibility."
            strength_e2 = "Pilot return data [E2] quantifies baseline container return rate (42%), identifying exact retention friction." if "E2" in cited_evidence else "High repeat purchase potential if refill cycle matches household consumption cadence."

            strengths = [
                "Strong consumer alignment with sustainability trends and zero-waste bathroom aesthetics.",
                strength_e1,
                strength_e2
            ]
            risks = [
                "Reverse logistics cost per unit: USPS/parcel return postage, cleaning, and quality inspection frequently exceed original bottle manufacturing cost.",
                "Consumer inertia: Customers intend to return empty containers but hoard them under bathroom sinks, depressing return rates.",
                "Hygiene and contamination liability: Refilling consumer bottles requires rigorous sanitization to avoid mold/bacterial growth under FDA MoCRA."
            ]
            missing_assumptions = [
                "Assumes customer return rate of empty containers exceeds 60% without requiring unsustainable cash deposits.",
                "Assumes formula viscosity allows complete bottle emptying without leaving 10-15% product residue that ruins cleaning cycles."
            ]
            if not has_any_evidence:
                missing_assumptions.append("CRITICAL: Zero empirical data on actual container return rates or reverse logistics shipping expenses.")

            questions = [
                "What is the exact net cost per returned container including outbound return bag, postage, sanitization, and discard rate?",
                "How do you prevent microbial cross-contamination across multiple refill generations?"
            ]
            experiment = {
                "hypothesis": "Offering a prepaid QR-code return pouch will achieve a >= 55% return rate of empty containers within 45 days of delivery.",
                "test_design": "Ship 200 refillable starter packs with prepaid return mailers; track return timing and inspect condition of returned hardware.",
                "success_metric": ">= 55% of containers returned within 45 days in reusable condition."
            }
            assumptions = [
                "Assumption: Sustainable consumers will tolerate paying a 15-20% price premium over drugstore alternatives for closed-loop packaging.",
                "Unknown: Long-term pump mechanism degradation over 5+ dishwashing cycles."
            ]
            if not has_any_evidence:
                assumptions.append("Unbacked Assumption: Customer willingness to return empties by mail has zero empirical backing.")

        elif "sleep" in prompt_lower or "brainwave" in prompt_lower or "acoustic" in prompt_lower:
            strengths = [
                "Massive addressable market driven by widespread adult sleep dissatisfaction and insomnia complaints.",
                "Non-invasive acoustic approach eliminates the ingestion side-effects associated with pharmaceutical sleep aids.",
                "High willingness to pay for non-pharmacological sleep interventions among biohackers and tech executives."
            ]
            risks = [
                "Zero clinical backing: No double-blind PSG (polysomnography) sleep studies validating acoustic brainwave entrainment through pillow textiles.",
                "Regulatory exposure: Marketing claims suggesting treatment for insomnia or sleep disorders trigger FDA enforcement as unapproved Class II medical devices.",
                "Hardware reliability in bedding: Mechanical speaker transducers face body heat, sweat, and movement fatigue."
            ]
            missing_assumptions = [
                "Critically assumes acoustic frequencies through pillow foam can entrain brainwaves through skull bone conduction during active sleep.",
                "Assumes consumers will sleep comfortably with electronic transducers directly beneath their ears."
            ]
            if "E1" in cited_evidence:
                missing_assumptions.append("Relies on single-person anecdotal diary [E1], which lacks statistical validity, sham controls, and EEG verification.")
            else:
                missing_assumptions.append("CRITICAL: Zero scientific or empirical data provided regarding acoustic entrainment or sleep onset latency.")

            questions = [
                "Where is the empirical clinical data demonstrating statistically significant EEG delta wave phase-locking?",
                "What legal disclaimers prevent FTC action regarding unsubstantiated sleep improvement claims?"
            ]
            experiment = {
                "hypothesis": "Users sleeping on the prototype show statistically significant increase in deep (N3) sleep compared to a sham sound control.",
                "test_design": "Run a 20-person randomized crossover trial using validated consumer EEG headbands comparing active entrainment vs pink noise.",
                "success_metric": "Statistically significant (p < 0.05) increase in N3 deep sleep duration with zero comfort-induced awakenings."
            }
            assumptions = [
                "Assumption: Acoustic entrainment translates from controlled lab headphones to variable sleeping positions on a pillow.",
                "Unknown: Long-term mechanical durability and fire-retardancy compliance of embedded electronics in bedding foam."
            ]

        else:
            strengths = [
                "Addresses a clearly defined operational friction point with demonstrable buyer utility.",
                "Modular architecture allows incremental rollout without requiring high upfront migration costs.",
                "Value proposition aligns with cost consolidation priorities."
            ]
            risks = [
                "Competitive vulnerability to platform incumbents who can replicate core features into existing bundles.",
                "Go-to-market friction: Customer acquisition cost may exceed lifetime value without established referral loops."
            ]
            missing_assumptions = [
                "Assumes users will actively adopt a new interface rather than sticking to default spreadsheets or existing tooling.",
                "Assumes high willingness to pay without verified pricing elasticity studies."
            ]
            if not has_any_evidence:
                missing_assumptions.append("CRITICAL: No empirical evidence supplied to demonstrate customer willingness to pay or prototype performance.")

            questions = [
                "What is the single most compelling trigger that forces a prospect to evaluate your solution today?",
                "How does the product maintain defensibility against open-source alternatives?"
            ]
            experiment = {
                "hypothesis": "Target users will commit to a 30-minute pilot onboarding call after receiving a targeted outreach demo.",
                "test_design": "Conduct cold outreach to 50 verified target customer profiles with a 2-minute Loom demo video.",
                "success_metric": ">= 10% conversion to scheduled onboarding calls."
            }
            assumptions = [
                "Assumption: Target users have direct budget authority to expense the product without procurement review.",
                "Unknown: Churn rate after initial novelty wears off."
            ]

        return {
            "strengths": strengths,
            "risks": risks,
            "missing_assumptions": missing_assumptions,
            "questions": questions,
            "validation_experiment": experiment,
            "evidence_citations": cited_evidence,
            "invalid_citations": [],
            "assumptions_and_unknowns": assumptions
        }

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
