# HayMagnet AI Documentation Index

Welcome to the AI documentation hub for **HayMagnet**, the multi-agent fraud investigation platform powered by TigerGraph Cloud, Model Context Protocol (MCP), and multi-LLM reasoning.

This documentation suite is specifically structured for AI coding agents, autonomous subagents, and AI-assisted human engineers navigating or modifying this codebase.

---

## Documentation Sitemap

| Document | Purpose & Scope |
| :--- | :--- |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Multi-agent topology, data flow, MCP bridge, and system architecture. |
| **[AGENT_GUIDELINES.md](AGENT_GUIDELINES.md)** | Directives, prompt engineering standards, critique loops, and anti-hallucination policies. |
| **[GRAPH_SCHEMA.md](GRAPH_SCHEMA.md)** | TigerGraph `FraudGraph` schema: vertex types, attributes, edge relationships, and GSQL query patterns. |
| **[API_REFERENCE.md](API_REFERENCE.md)** | Detailed documentation for modules (`agent.py`, `tools.py`, `app.py`, etc.), functions, and schemas. |
| **[RUNBOOK.md](RUNBOOK.md)** | Operational guides: installation, environment setup, database provisioning, batch execution, and UI dashboard. |

---

## Core Mission & Context

Financial fraud investigations require synthesizing unstructured behavioral signals with structured, multi-hop relationship graphs. Traditional rule engines generate high rates of false positives, while human analysis is slow and fragmented.

HayMagnet automates this end-to-end through a specialized multi-agent hierarchy:
1. **Agent 2 (Lead Investigator)** plans the investigation, forms hypotheses based on institutional banking rules, and requests evidence.
2. **Agent 1 (DB Expert)** translates data requests into TigerGraph GSQL and MCP function calls, returning graph-native evidence.
3. **Agent 3 (Senior Overseer)** reviews verdicts against raw retrieved evidence to approve or reject with targeted critique.
4. **Structured Verdict Engine** formats approved verdicts into actionable JSON files (`cases/{case_id}.json`).
