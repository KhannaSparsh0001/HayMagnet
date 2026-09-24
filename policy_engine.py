"""
HayMagnet Policy Engine & Deterministic Reasoning Module.
Implements rigid Fraud Policy Rules (R1-R10), approval routing (auto/L1/L2), 
exposure summation, SAR thresholds, and Pydantic schemas for hackathon evaluation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

# ==============================================================================
# PYDANTIC SCHEMAS (HHGOA IEEE Benchmark Standard)
# ==============================================================================

class EvidenceRequestItem(BaseModel):
    type: str = Field(description="customer_validation | step_up_auth | analyst_info")
    asked_after_step: int = Field(default=1)
    assumed_response: str = Field(default="")

class EvidenceClaimItem(BaseModel):
    claim: str
    source: str = Field(description="graph | document | customer | external")
    ref: str = Field(description="query name, document section, or request id")
    entity_ids: List[str] = Field(default_factory=list)

class ActionItem(BaseModel):
    action: str = Field(description="Action name from Fraud Policy Section 1")
    route: str = Field(description="auto | L1 | L2")
    reason: str = Field(description="Rule citation and justification")

class NextBestActions(BaseModel):
    initial: List[ActionItem] = Field(default_factory=list)
    final: List[ActionItem] = Field(default_factory=list)
    what_changed: str = Field(default="nothing")

class SARReport(BaseModel):
    file: bool = Field(default=False)
    reason: str = Field(default="")
    narrative: str = Field(default="")
    subjects: List[str] = Field(default_factory=list)
    total_amount_usd: float = Field(default=0.0)
    activity_dates: List[str] = Field(default_factory=list)

class CaseDetails(BaseModel):
    status: str = Field(default="closed_legitimate", description="open | closed_fraud | closed_legitimate | escalated")
    verdict: str = Field(default="legitimate", description="fraud | legitimate | uncertain")
    fraud_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    pattern: str = Field(default="none", description="card_testing | card_not_present_fraud | card_not_present_new_device | out_of_region_use | account_takeover | undocumented | none")
    pattern_description: str = Field(default="")
    affected_txn_ids: List[str] = Field(default_factory=list)
    first_suspicious_txn_id: str = Field(default="")
    connected_card_ids: List[str] = Field(default_factory=list)
    connected_device_profiles: List[str] = Field(default_factory=list)
    exposure_usd: float = Field(default=0.0)
    evidence: List[EvidenceClaimItem] = Field(default_factory=list)
    similar_prior_cases: List[str] = Field(default_factory=list)
    summary: str = Field(default="")
    written_to_graph: bool = Field(default=False)
    graph_case_id: str = Field(default="")

class BenchmarkCaseResult(BaseModel):
    case_id: str
    case: CaseDetails
    evidence_requests: List[EvidenceRequestItem] = Field(default_factory=list)
    next_best_actions: NextBestActions
    sar: SARReport
    stop_reason: str = Field(default="Investigation concluded based on available evidence and policy rules.")
    tool_calls: int = Field(default=0)
    tokens: int = Field(default=0)
    latency_s: float = Field(default=0.0)

# ==============================================================================
# DETERMINISTIC CALCULATIONS & POLICY EVALUATION
# ==============================================================================

AUTO_ACTIONS = {
    "ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", 
    "WARN_CUSTOMER", "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH", 
    "GENERATE_REPORT", "CREATE_CASE", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD"
}

def get_approval_route(action_name: str, exposure_usd: float = 0.0) -> str:
    """Deterministically returns the required approval route ('auto', 'L1', 'L2') per Policy Section 2."""
    if action_name in AUTO_ACTIONS:
        return "auto"
    if action_name == "DECLINE_TRANSACTION":
        return "L1"
    if action_name == "BLOCK_CARD":
        return "L1" if exposure_usd <= 2500.0 else "L2"
    if action_name in ["BLOCK_ALL_CARDS", "FILE_REPORT"]:
        return "L2"
    return "L1"

def calculate_exposure(amounts: List[float]) -> float:
    """Deterministically sums absolute transaction amounts in USD."""
    return round(sum(abs(amt) for amt in amounts if amt is not None), 2)

def evaluate_policy_rules(
    verdict: str,
    fraud_prob: float,
    pattern: str,
    exposure_usd: float,
    has_shared_entity: bool = False,
    customer_response: Optional[str] = None,
    affected_txns_count: int = 1,
    connected_cards_count: int = 0
) -> tuple[List[ActionItem], List[ActionItem], str, bool, str]:
    """
    Evaluates Fraud Policy Rules R1-R10 deterministically.
    Returns:
      (initial_actions, final_actions, what_changed_summary, should_file_sar, sar_reason)
    """
    initial_actions: List[ActionItem] = []
    final_actions: List[ActionItem] = []
    what_changed = "nothing"
    should_sar = False
    sar_reason = ""

    # Rule R3 / Legitimate Verdict
    if verdict == "legitimate" or customer_response == "confirmed":
        action = ActionItem(
            action="CLOSE_NO_FRAUD",
            route=get_approval_route("CLOSE_NO_FRAUD"),
            reason="R3: Customer confirmed transaction / Evidence cleared alert as legitimate false positive."
        )
        initial_actions.append(action)
        final_actions.append(action)
        return initial_actions, final_actions, "nothing", False, "Case cleared as legitimate false positive."

    # Rule R8 / Uncertain Verdict
    if verdict == "uncertain":
        if exposure_usd > 500.0 or has_shared_entity:
            act = ActionItem(
                action="ESCALATE_TO_ANALYST",
                route=get_approval_route("ESCALATE_TO_ANALYST"),
                reason="R8: Investigation verdict is uncertain with exposure > $500 or conflicting graph signals."
            )
            initial_actions.append(act)
            final_actions.append(act)
        else:
            act1 = ActionItem(
                action="MONITOR_CARD",
                route=get_approval_route("MONITOR_CARD"),
                reason="R4: Elevated monitoring on uncertain signal with low exposure."
            )
            act2 = ActionItem(
                action="VERIFY_WITH_CUSTOMER",
                route=get_approval_route("VERIFY_WITH_CUSTOMER"),
                reason="R1: Weak signal with probability < 0.70; verify before blocking."
            )
            initial_actions.extend([act1, act2])
            final_actions.extend([act1, act2])
        return initial_actions, final_actions, "nothing", False, "Uncertain verdict; no SAR required."

    # Confirmed Fraud Logic (verdict == "fraud")

    # Initial actions before customer response
    if fraud_prob < 0.70 and not customer_response:
        # Rule R1: Weak signal verify before block
        initial_actions.append(ActionItem(
            action="VERIFY_WITH_CUSTOMER",
            route=get_approval_route("VERIFY_WITH_CUSTOMER"),
            reason="R1: Fraud probability < 0.70 on initial signals; verify with customer before blocking."
        ))
        initial_actions.append(ActionItem(
            action="MONITOR_CARD",
            route=get_approval_route("MONITOR_CARD"),
            reason="R1: Place card under 72h monitoring while awaiting customer response."
        ))
    else:
        # Strong signal or initial block recommendation
        if pattern == "card_testing":
            initial_actions.append(ActionItem(
                action="DECLINE_TRANSACTION",
                route=get_approval_route("DECLINE_TRANSACTION"),
                reason="R5: Card testing sequence observed (multiple small authorizations followed by larger purchase)."
            ))
            initial_actions.append(ActionItem(
                action="STEP_UP_AUTH",
                route=get_approval_route("STEP_UP_AUTH"),
                reason="R5: Require step-up authentication for subsequent authorizations."
            ))
        else:
            initial_actions.append(ActionItem(
                action="BLOCK_CARD",
                route=get_approval_route("BLOCK_CARD", exposure_usd),
                reason=f"R2/R5: High confidence fraud assessment ({fraud_prob:.2f}). Block card and reissue."
            ))

    # Determine Final Actions (after simulated customer response / evidence compilation)
    if customer_response == "denied" or fraud_prob >= 0.70:
        final_actions.append(ActionItem(
            action="BLOCK_CARD",
            route=get_approval_route("BLOCK_CARD", exposure_usd),
            reason=f"R2: Customer denied transaction / High confidence fraud confirmed ({fraud_prob:.2f}). Exposure: ${exposure_usd:.2f}."
        ))
        final_actions.append(ActionItem(
            action="CREATE_CASE",
            route=get_approval_route("CREATE_CASE"),
            reason="R2/3a: Open internal fraud case and log investigation evidence to graph memory."
        ))

        # Check SAR conditions (Rule 3a)
        sar_triggers = []
        if exposure_usd > 1000.0:
            sar_triggers.append(f"exposure (${exposure_usd:.2f}) exceeds $1,000 threshold")
        if has_shared_entity:
            sar_triggers.append("activity connects to shared device profile or connected card compromise")
        if pattern == "undocumented":
            sar_triggers.append("R9: undocumented coordinated fraud pattern identified")

        if sar_triggers:
            should_sar = True
            sar_reason = f"R2/3a: Confirmed fraud filing required because " + " and ".join(sar_triggers) + "."
            final_actions.append(ActionItem(
                action="FILE_REPORT",
                route=get_approval_route("FILE_REPORT"),
                reason=sar_reason
            ))

        if has_shared_entity or connected_cards_count > 0:
            final_actions.append(ActionItem(
                action="MONITOR_CONNECTED_CARDS",
                route=get_approval_route("MONITOR_CONNECTED_CARDS"),
                reason="R6: Shared device profile or billing region cluster detected across multiple cards."
            ))

        if customer_response == "denied" and fraud_prob < 0.70:
            what_changed = f"Customer denial raised fraud probability to {max(0.85, fraud_prob):.2f}, confirming card block and internal case creation."
        elif initial_actions != final_actions:
            what_changed = "Evidence synthesis confirmed fraud episode details, finalizing card block and regulatory report routing."

    else:
        final_actions = list(initial_actions)

    return initial_actions, final_actions, what_changed, should_sar, sar_reason
