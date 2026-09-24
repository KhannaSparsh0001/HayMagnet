# Future Development Roadmap

This document outlines planned features, architectural improvements, and known technical debt for the HayMagnet platform.

## 1. UI & Transparency
- **DB Expert Execution Logs:** Implement a live streaming log for Agent 1 (DB Expert). Currently, when Agent 1 is executing multiple TigerGraph tools or thinking, the UI just shows a spinner. We need to expose its internal reasoning and network latency steps so the user knows exactly what it is doing during long wait times.
- **Advanced Dashboard Refinement:** The Streamlit dashboard needs to be further improved into a production-grade interface. This includes better visualization of the graph data, more interactive components, and potentially migrating from Streamlit to a full React/Next.js frontend for enterprise deployments.
- **State Persistence (Memory Retention):** Currently, refreshing the browser wipes the entire investigation state because Streamlit re-runs the script from top to bottom. A robust solution needs to be implemented (e.g., using `st.session_state` extensively combined with a lightweight local database like SQLite or Redis) to cache the agent's memory and chat history so investigations can be paused and resumed without data loss.

## 2. Agent Architecture Optimization (The "Agent 1 Overload" Problem)
Currently, Agent 1 handles the entire burden of translating massive, multi-faceted data requests from Agent 2 into TigerGraph MCP function calls. As the graph scales, this becomes a bottleneck:
- **Dynamic Sub-Agent Delegation (Swarm):** Instead of one monolithic DB Expert, we need an Overseer/Router agent that monitors and distributes the massive workload. This agent will use a custom function to dynamically decide how many specialized "helping agents" (e.g., `DeviceProfileSpecialist`, `TransactionHistorySpecialist`) are required for the query, and spawn them up to a hard concurrency limit.
- **Iterative Querying:** Force Agent 2 to ask smaller, sequential questions rather than demanding the entire graph history in a single massive prompt. This reduces the token load on Agent 1 and improves tool-calling accuracy.

## 3. Automation & Ingestion
- **Automated Case Starting Mechanism:** Currently, cases are manually selected from a static CSV via the dashboard. We need a live ingestion engine (e.g., Kafka or webhooks) that automatically triggers the agentic workflow as soon as a high-risk transaction hits the TigerGraph database.

## 4. Performance Optimization
- **Startup Latency:** The initial startup time for the application takes too long to load. We need to investigate lazy-loading the MCP server connection, caching the Streamlit initial render, or pre-warming the API models to reduce the time from launch to interaction.
