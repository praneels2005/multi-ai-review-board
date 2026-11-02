"""
Deterministic Mock Adapter for Multiple AI Review Board.
Provides offline, deterministic, rich generation without requiring any API keys.
Accurately simulates latency, token usage, cost, and failure modes for testing.
"""

import asyncio
import hashlib
import json
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
            # Sleep longer than timeout or simulate immediate timeout
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

        # Realistic simulated network latency (150ms to 400ms)
        await asyncio.sleep(0.2)

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

        # 3. Challenge and Response
        if "challenge" in lower_prompt or "debate" in lower_prompt or "cross-examination" in lower_prompt:
            return self._generate_challenge_response(user_prompt)

        # 4. Default: Specialist Feedback
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
        """Generate independent specialist review with cited evidence and assumptions."""
        prompt_lower = (system_prompt + " " + user_prompt).lower()
        role = "Domain Specialist"
        if "role:" in prompt_lower:
            role = prompt_lower.split("role:")[1].split("\n")[0].strip()

        # Check for evidence IDs provided in prompt
        cited_evidence = []
        if "e1" in prompt_lower:
            cited_evidence.append("E1")
        if "e2" in prompt_lower and "metric" in prompt_lower:
            cited_evidence.append("E2")

        # Specific feedback based on domain keywords
        if "ebpf" in prompt_lower or "tracing" in prompt_lower or "developer" in prompt_lower:
            strengths = [
                "Zero-instrumentation telemetry drastically reduces developer onboarding friction compared to SDK injection.",
                "Citing benchmark data [E1] demonstrates sub-2% CPU overhead on representative containerized workloads." if "E1" in cited_evidence else "eBPF kernel-level visibility bypasses application runtime hooks, eliminating user-space code pollution.",
                "Direct alignment with DevOps pain points regarding excessive Datadog logging and APM egress fees."
            ]
            risks = [
                "Requires elevated Linux kernel capabilities (CAP_BPF / root daemonset), which enterprise security teams actively block in shared multi-tenant clusters.",
                "Kernel version fragmentation: eBPF CO-RE (Compile Once - Run Everywhere) can fail on older enterprise distributions (e.g. RHEL 7/8, legacy cloud AMIs).",
                "High customer support burden debugging kernel probes across bespoke enterprise microservice topologies."
            ]
            missing_assumptions = [
                "Assumes engineering teams have permission to deploy privileged DaemonSets into enterprise production environments.",
                "Assumes developers who inspect traces are the same budget holders willing to displace existing contract commitments."
            ]
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

        elif "cosmetic" in prompt_lower or "refill" in prompt_lower or "sustainable" in prompt_lower:
            strengths = [
                "Strong consumer alignment with sustainability trends and zero-waste bathroom aesthetics.",
                "Citing pilot data [E1] suggests early customer appetite, with reasonable initial acquisition costs." if "E1" in cited_evidence else "High repeat purchase potential if refill cycle matches household consumption cadence.",
                "Closed-loop brand story creates emotional loyalty and word-of-mouth defensibility."
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

        elif "sleep" in prompt_lower or "brainwave" in prompt_lower or "acoustic" in prompt_lower:
            strengths = [
                "Massive addressable market driven by widespread adult sleep dissatisfaction and insomnia complaints.",
                "Non-invasive acoustic approach eliminates the ingestion side-effects associated with pharmaceutical sleep aids."
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
            questions = [
                "Where is the empirical clinical data demonstrating statistically significant EEG delta wave phase-locking?",
                "What legal disclaimers prevent FTC action regarding unsubstantiated sleep improvement claims?"
            ]
            experiment = {
                "hypothesis": "Users sleeping on the prototype show statistically significant increase in deep (N3) sleep compared to a sham sound control.",
                "test_design": "Run a 20-person randomized crossover trial using validated consumer EEG headbands (e.g. Muse or Dreem) comparing active entrainment vs pink noise.",
                "success_metric": "Statistically significant (p < 0.05) increase in N3 deep sleep duration with zero comfort-induced awakenings."
            }
            assumptions = [
                "Assumption: Acoustic entrainment translates from controlled lab headphones to variable sleeping positions on a pillow.",
                "Unknown: Long-term mechanical durability and fire-retardancy compliance of embedded electronics in bedding foam."
            ]

        else:
            strengths = [
                "Addresses a clearly defined operational friction point with demonstrable buyer utility.",
                "Modular architecture allows incremental rollout without requiring high upfront migration costs."
            ]
            risks = [
                "Competitive vulnerability to platform incumbents who can replicate core features into existing bundles.",
                "Go-to-market friction: Customer acquisition cost may exceed lifetime value without established referral loops."
            ]
            missing_assumptions = [
                "Assumes users will actively adopt a new interface rather than sticking to default spreadsheets or existing tooling.",
                "Assumes high willingness to pay without verified pricing elasticity studies."
            ]
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

    def _generate_challenge_response(self, user_prompt: str) -> Dict[str, Any]:
        """Generate bounded challenge and response debate between specialists."""
        prompt_lower = user_prompt.lower()

        if "ebpf" in prompt_lower or "tracing" in prompt_lower or "developer" in prompt_lower:
            return {
                "challenges": [
                    {
                        "challenger_id": "spec_2",
                        "challenger_role": "Cloud Infrastructure & Kernel Systems Architect",
                        "target_specialist_id": "spec_1",
                        "target_role": "Developer Experience & CLI Usability Specialist",
                        "challenge_point": "You prioritize seamless 1-click CLI onboarding, but deploying eBPF probes requires privileged host access (CAP_SYS_ADMIN / CAP_BPF) that no enterprise platform engineer will grant via a developer-facing CLI tool.",
                        "response": "Understood. Rather than executing root commands locally, our CLI can generate standard GitOps Kubernetes manifests (Helm/Kustomize) that route through the security team's approval pipeline, maintaining dev-ex for tracing while honoring infra governance.",
                        "reasoning_adjustment": "Adjusted adoption model: shift from rogue bottom-up developer installation to a platform-engineered self-serve model with pre-approved RBAC permissions."
                    },
                    {
                        "challenger_id": "spec_4",
                        "challenger_role": "Open-Core & Enterprise GTM Strategist",
                        "target_specialist_id": "spec_3",
                        "target_role": "DevSecOps & Compliance Auditor",
                        "challenge_point": "Your recommendation to redact all payload telemetry by default neutralizes our primary enterprise value proposition—debugging root causes in distributed microservice transactions.",
                        "response": "Payload redaction must be configurable at the edge, using regex patterns and PII tokenization before network egress, ensuring enterprise compliance without stripping payload metadata needed for diagnosis.",
                        "reasoning_adjustment": "Risk appraisal updated: compliance is maintained via automated client-side data tokenization rather than blanket payload stripping."
                    }
                ]
            }
        elif "cosmetic" in prompt_lower or "refill" in prompt_lower or "sustainable" in prompt_lower:
            return {
                "challenges": [
                    {
                        "challenger_id": "spec_4",
                        "challenger_role": "Unit Economics & Packaging Procurement Analyst",
                        "target_specialist_id": "spec_1",
                        "target_role": "Sustainable Supply Chain & Reverse Logistics Specialist",
                        "challenge_point": "Your reverse logistics model assumes a $1.80 return shipping cost, but low-density parcel return rates through USPS parcel select will exceed $3.40 per bottle, wiping out gross margin on refills.",
                        "response": "To preserve margin, returns should not happen per bottle. Customers must accumulate a minimum of 3 empty containers in a batch-mailer before shipping, reducing per-unit reverse freight to $1.15.",
                        "reasoning_adjustment": "Logistical adjustment: customer refill schedule updated to batch-returns every 90 days rather than single-bottle return loops."
                    }
                ]
            }
        elif "sleep" in prompt_lower or "brainwave" in prompt_lower or "acoustic" in prompt_lower:
            return {
                "challenges": [
                    {
                        "challenger_id": "spec_1",
                        "challenger_role": "Neurobiology & Sleep Medicine Researcher",
                        "target_specialist_id": "spec_3",
                        "target_role": "FDA Regulatory & Health Claims Attorney",
                        "challenge_point": "You suggest softening marketing claims to 'general relaxation' to evade FDA 510(k) scrutiny, but doing so strips the product of any medical credibility and fails to justify its premium $299 price tag.",
                        "response": "We must bifurcate the roadmap: launch first under FTC-compliant wellness claims to generate non-clinical cash flow, while concurrently funding a formal sham-controlled clinical trial for future medical certification.",
                        "reasoning_adjustment": "Strategic roadmap updated: staged market entry separating immediate wellness revenue from long-term clinical trial validation."
                    }
                ]
            }
        else:
            return {
                "challenges": [
                    {
                        "challenger_id": "spec_3",
                        "challenger_role": "GTM & Competitive Differentiation Strategist",
                        "target_specialist_id": "spec_1",
                        "target_role": "Product-Market Fit & Customer Discovery Specialist",
                        "challenge_point": "Customer interviews may confirm users dislike existing tools, but dissatisfaction does not prove willingness to switch workflows or migrate data.",
                        "response": "Agreed. We must measure friction tolerance by requiring early design partners to export and connect live test data before admitting them to the pilot.",
                        "reasoning_adjustment": "Validation threshold tightened: qualification now requires active data connection commitment rather than verbal interest."
                    }
                ]
            }

    def _generate_coordinator_synthesis(self, user_prompt: str) -> Dict[str, Any]:
        """Synthesize independent reviews, highlight disagreements, evaluate evidence sufficiency, and note failure impact."""
        prompt_lower = user_prompt.lower()

        # Check if an agent failure was reported in prompt
        failure_detected = "failure" in prompt_lower or "failed" in prompt_lower or "timed out" in prompt_lower
        failure_impact = None
        if failure_detected:
            failure_impact = "One or more specialist agents failed or timed out during the review board run. As a result, specific technical facets (e.g. detailed kernel or dev-ex verification) could not be comprehensively scrutinized. Confidence in those specific domains is lower, and the founding team should manually consult domain experts before committing engineering resources."

        # Evaluate evidence sufficiency
        if "sleep" in prompt_lower or "brainwave" in prompt_lower or "thin" in prompt_lower:
            evidence_status = "thin"
            evidence_analysis = "Supplied evidence consists primarily of anecdotal founder testimonials without randomized, double-blind, or sham-controlled clinical datasets. Scientific claims regarding acoustic brainwave entrainment through sleep textiles remain unbacked by empirical polysomnography data."
        elif "ebpf" in prompt_lower or "tracing" in prompt_lower:
            evidence_status = "sufficient"
            evidence_analysis = "Supplied evidence provides concrete benchmark data on agent CPU overhead (< 2%) and qualitative interview findings from 12 prospective DevOps leads. Key remaining unknown is enterprise willingness to deploy privileged daemonsets in locked-down production."
        else:
            evidence_status = "thin"
            evidence_analysis = "Evidence provided offers early qualitative signals but lacks quantitative retention cohorts or unit-economic proof at operational scale."

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

