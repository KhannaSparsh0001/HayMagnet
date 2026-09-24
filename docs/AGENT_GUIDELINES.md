# Agent Guidelines & Operational Policies

This document establishes the guidelines, prompt conventions, anti-hallucination policies, and operational behavior required for AI agents in HayMagnet.

---

## 1. Core Principles

1. **Evidence-Grounded Reasoning**:
   An investigator agent must NEVER invent transaction IDs, card numbers, device fingerprints, or historical outcomes. Every fact cited in a verdict must trace directly to evidence retrieved by the DB Expert or given in the trigger.

2. **Default-to-Fraud on Missing Risk Signals**:
   Per institutional fraud policy, if a transaction is under review and has a null or missing risk score, or suspicious velocity across unverified devices, the agent must treat the risk as elevated unless corroborated by established customer profile history.

3. **Multi-Turn Investigation Budget**:
   The investigation loop is strictly bounded (maximum 5 to 8 turns). Agents must converge toward a definitive verdict (`Confirmed Fraud` or `False Positive`) before the turn budget expires.

4. **Overseer Veto Power**:
   Agent 3 has strict veto authority. If the Overseer identifies that a rule was improperly cited or facts were assumed without query proof, the Lead Investigator must rectify its hypothesis in the next turn.

---

## 2. Agent Prompting Contracts

### Agent 2: Lead Investigator Contract
The prompt must always adhere to the following output format:
- If additional database evidence is required:
  ```text
  Data Request: [Specific entity lookup or graph traversal needed]
  ```
- If sufficient evidence exists:
  ```text
  Final Verdict: [Detailed factual reasoning] [Decision: Confirmed Fraud | False Positive]
  ```

### Agent 1: DB Expert Contract
- Always targets the graph `FraudGraph`.
- Calls TigerGraph MCP tools cleanly with valid arguments matching vertex types (`Customer`, `Card`, `Transaction`, `DeviceProfile`, `BillingRegion`, `ClosedCase`).
- Translates IDs to strings to conform with TigerGraph REST-30200 schema constraints.
- Emits clean, synthesized text answering the Lead Investigator's specific question.

### Agent 3: Senior Overseer Contract
- Must verify that every single assertion in the submitted verdict is backed by `db_evidence`.
- If valid:
  ```text
  APPROVED
  ```
- If invalid:
  ```text
  REJECTED: [Actionable critique explaining what was hallucinated or missed]
  ```

---

## 3. Formatting Contract (`format_final_verdict`)

The final output written to `cases/{case_id}.json` must strictly adhere to the JSON schema:
```json
{
  "decision": "Confirmed Fraud | False Positive",
  "reasoning": "A concise paragraph explaining the evidence and rule citations."
}
```

---

## 4. Error Handling and Resilience Standards

- **Timeouts**: All LLM and database invocations MUST be wrapped in timeouts (60 seconds for LLMs, 45 seconds for MCP tool executions).
- **Asynchronous Integrity**: Synchronous blocking network calls (e.g. standard HTTP clients) must never run directly on the event loop; use `asyncio.to_thread` to prevent thread starvation.
- **Stateless Tool Synthesis**: To avoid SDK recursion bugs where LLMs chain function calls uncontrollably, tool results must be summarized in a fresh stateless prompt.
