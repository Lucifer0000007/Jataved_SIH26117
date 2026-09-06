# JATAVED — Air-Gapped Agentic AI Workbench for Refinery SOPs

> **Code decides. Model writes.** A 100% on-premise, hallucination-controlled
> agentic AI workbench for refinery Standard Operating Procedures.
> Smart India Hackathon • SIH26117 • MRPL • Team Zero Output

`100% Offline` • `Local LLMs only` • `Zero cloud APIs` • `Edge GPU (4 GB) tested`

## The Problem
Refinery operators need fast answers from hundreds of SOP pages, but:
1. Plants are **air-gapped** — cloud AI is impossible.
2. A **hallucinated procedure** is a safety incident.
3. Juniors must not access senior procedures (**RBAC**).
4. P&ID drawings **drift** out of sync with SOP text; changes are uncontrolled.

## The Philosophy
Deterministic Python gates surround small local LLMs. Models may *write*
cited answers; they never *decide* access, safety, or escalation.
Every gate failure becomes a human t
icket — the system **refuses to guess**.

## Architecture (three flows)
1. **Main Query:** Login→Role (RBAC) → Scope Guard → Role-Scoped Search
   (ChromaDB) → Confidence Gate (cosine > 0.33 ⇒ escalate) → Cited Answer
   (mandatory `Source: file, section`) → Audit Log.
2. **Doc-Control Ingestion (multimodal):** Upload P&ID → Moondream extracts
   tags → cross-check vs registered metadata → Link+Log **or** Flag for
   human review. Vision runs at ingestion only.
3. **Governance:** Admin change → 24h cooling-off → 2-party quorum →
   active → monthly recertification → mutual oversight logs.

## Tech Stack
| Layer | Tool |
|---|---|
| UI | Streamlit (Ask / Diagram / Logs) |
| Answer LLM | Phi-3.5-mini Q4 via Ollama (+ qwen2.5:1.5b fallback) |
| Vision | Moondream (local) |
| Embeddings | nomic-embed-text |
| Vector store | ChromaDB (embedded, cosine) |
| Guards | deterministic Python (zero LLM calls) |

## Repository Structure