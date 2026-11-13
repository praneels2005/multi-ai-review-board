"""Live review-board evidence policy; ratings are scoped to a stated decision."""

LIVE_EVIDENCE_RUBRIC = """
Evidence sufficiency rubric (apply in this order):
1. Scope: identify the next consequential founder decision implied by the idea and reviews
   (for example, commit to a bounded paid pilot). State that decision in analysis. If no decision
   is explicit, use whether to commit to an initial customer pilot; do not shrink the scope to
   'do more research' just to earn a sufficient rating. Never rate the entire startup as proven.
2. Qualify evidence: a usable empirical report identifies a traceable source, relevant customer
   or operating setting, method, sample size or observation coverage, observed outcome, and
   material limitations. Quantitative claims need units, timeframe and a baseline/comparison
   where the inference requires one. Qualitative findings need participant selection and a
   documented collection method. Assess adequacy for the decision; there is no universal sample
   size or numeric score. Missing decision-critical details do not count as established.
   Founder narrative, proposed tests, hypothetical examples, market-size estimates alone, and
   repeated AI opinions are not empirical validation. A source label or URL alone is not verification;
   assess only supplied content and disclose when authenticity cannot be independently checked.
3. Coverage: identify the assumptions that could reverse this decision. For a customer pilot,
   cover a real problem in the target segment plus product feasibility and willingness to commit
   resources at the level the pilot requires. Broader launch/scale decisions also require observed
   usage or retention, commercial viability, and operational readiness as relevant. Evidence of
   interest alone cannot establish willingness to pay, retention, or feasible unit economics.
4. Assign exactly one status:
   - insufficient: no relevant empirical evidence supports assessment of the scoped decision;
     all supplied material is absent, irrelevant, hypothetical, or unsupported assertions.
   - thin: some relevant observations exist (including anecdotes), but any sufficient gate below
     is unmet. Without evidence mark 'insufficient'. Anecdotes remain 'thin' at best.
   - sufficient: ALL gates must pass:
     a. At least two distinct, qualified empirical reports provide complementary support, including
        direct observations from the intended customers or real operating setting. Duplicate reports,
        repeated summaries, or two metrics from the same study count as one report. Different type
        labels alone do not satisfy this gate. Two studies by the founder may qualify if genuinely
        distinct; disclose common-source bias rather than claiming independent corroboration.
     b. Together the reports address every decision-critical assumption, using methods, sample
        coverage, and recency appropriate to the decision's cost, reversibility, and potential harm.
     c. No unresolved material contradiction, methodological flaw, or missing specialist perspective
        could reasonably reverse the decision. A failed specialist is a blocker only when its missing
        perspective is decision-critical and not adequately covered by another successful review.
     d. Limitations are explicit, remaining unknowns are non-blocking for this decision, and any
        safety, legal, or regulated claims needed for it have appropriate domain-specific support.
        A pilot or anecdote alone cannot establish clinical efficacy or broad safety claims.
   Sufficient means enough evidence to choose the scoped action, including a decision to stop or
   pivot after well-supported negative results. It does not mean favorable results, guaranteed
   success, investment readiness, or proof of market demand. Do not average away a failed gate.
5. Explain: in evidence_sufficiency.analysis, name the decision, cite supplied evidence IDs for
   decisive support or adverse findings, and identify the blocking gate and smallest evidence step
   needed to upgrade the rating. If sufficient, explain why the gates pass and state the boundary
   or remaining non-blocking limitation. Usually use 3 short sentences; add detail if needed for rigor.
   Keep the existing status/analysis JSON structure; do not add gate scores or new fields.

Calibration examples (illustrative only; never cite these as supplied evidence):
- A pitch plus a planned survey: insufficient; there are no observed customer results.
- Several enthusiastic customer quotes without methods or measured commitment: thin.
- Two complementary documented studies of target-customer pain and actual paid-pilot commitment,
  with relevant feasibility measurements, adequate coverage, explicit limitations and no unresolved
  blocker: sufficient for that bounded pilot; not sufficient to scale.
- Those same reports with an unresolved critical reliability or safety contradiction: thin.
- Two rigorous relevant studies showing demand and economics fail the founder's decision thresholds:
  sufficient to stop or pivot, if all gates pass; do not downgrade solely because findings are negative.
"""
