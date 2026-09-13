# 🛢️ JATAVED

**Air-gapped agentic AI workbench for refinery Standard Operating Procedures.**

> **Code decides. Model writes.**

Deterministic Python gates surround small local LLMs. The model may *write* cited
answers; it never *decides* access, safety, or escalation. Every gate failure
becomes a human ticket — the system refuses to guess.

`SIH26117` · Smart India Hackathon · MRPL · **Team Zero Output**

![Offline](https://img.shields.io/badge/network-air--gapped-critical)
![LLM](https://img.shields.io/badge/LLM-local%20only%20(Ollama)-blue)
![GPU](https://img.shields.io/badge/tested%20on-4%20GB%20edge%20GPU-green)
![Deps](https://img.shields.io/badge/dependencies-3-lightgrey)

---

## The problem

A refinery operator needs an answer from hundreds of pages of SOPs, on shift, in
minutes. Four constraints make the obvious solution illegal:

1. **Plants are air-gapped.** Cloud AI is not slow here — it is unreachable.
2. **A hallucinated procedure is a safety incident.** "Probably correct" is the
   failure mode, not the success case.
3. **Role separation is mandatory.** A junior trainee must not receive a senior
   interlock procedure, even if the retrieval engine finds it.
4. **P&ID drawings drift** out of sync with SOP text, and changes go uncontrolled.

JATAVED answers from local documents only, on hardware inside the fence, and
**refuses out loud** whenever it cannot prove the answer.

---

## The core idea

Most RAG systems ask the model to behave. JATAVED does not trust it to.

Every decision that carries safety or access consequence is made by deterministic
Python **before or after** the model runs. The LLM sees a query only after it has
passed scope and role checks, and only with retrieved context attached. It has no
authority to grant access, assess confidence, or decide escalation.

| Decision | Who makes it |
|---|---|
| Is this query in scope? | Python keyword guard — **LLM not called** |
| Can this role see this document? | Python RBAC filter on Chroma metadata |
| Is retrieval confident enough? | Python threshold on cosine distance |
| Should this escalate to a human? | Python — writes a ticket |
| Is a change approved? | Python quorum + cooling-off timer |
| **Wording of a cited answer** | **The model — and only this** |

---

## The gate pipeline

```
  Operator query
        │
        ▼
  ┌──────────────────┐   fail   ┌─────────────────────────────┐
  │ 1. Scope Guard   ├─────────►│ BLOCKED + ticket            │
  │    keyword match │          │ LLM is never called         │
  └────────┬─────────┘          └─────────────────────────────┘
           │ pass
           ▼
  ┌──────────────────┐
  │ 2. Retrieval     │  ChromaDB, cosine, top-6
  │    + tag boost   │  exact equipment tags float to the top
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐   fail   ┌─────────────────────────────┐
  │ 3. RBAC          ├─────────►│ RBAC DENIED + logged        │
  │    role vs cat   │          │ best match is out of role   │
  └────────┬─────────┘          └─────────────────────────────┘
           │ pass
           ▼
  ┌──────────────────┐   fail   ┌─────────────────────────────┐
  │ 4. Confidence    ├─────────►│ ESCALATED + ticket          │
  │    distance≤0.33 │          │ no guess is produced        │
  └────────┬─────────┘          └─────────────────────────────┘
           │ pass
           ▼
  ┌──────────────────┐
  │ 5. Answer (LLM)  │  top-3 chunks as context, temperature 0.0
  │    must cite     │  must end with Source: file, section
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ 6. Audit         │  append-only audit.log + per-step trace
  └──────────────────┘
```

**The RBAC gate is deliberately built backwards.** Retrieval runs *unrestricted*
first, then Python checks whether the best-matching document is outside the role.
That distinguishes *"you may not see this"* from *"this does not exist"* — so the
denial is logged as a real access event rather than silently returning nothing.

**Confidence is a distance, not a similarity.** Chroma is configured with
`hnsw:space = cosine`, so a *lower* number means a closer match. `THRESHOLD = 0.33`
means: if the best chunk is farther than 0.33, escalate. The value is not a guess —
`eval.py` measures mean distance for correct versus wrong documents and recommends
the midpoint.

---

## Roles and access

Access is category-scoped, and categories come from the SOP filename prefix
(`pumps_SOP-01.txt` is category `pumps`), stamped into Chroma metadata at ingest.

| Role | ID | pumps | valves | safety |
|---|---|:---:|:---:|:---:|
| Shift Engineer | E-1042 | ✅ | ✅ | ✅ |
| Junior Trainee | T-201 | ✅ | ❌ | ❌ |

A junior asking about an interlock gets **RBAC DENIED** — not a redacted answer, not
a partial one, and the event lands in the audit log.

---

## Three flows

### 1. Ask — cited answers or nothing

Passes the six gates above. On success the UI shows the citation, the answer, the
**top-3 source chunks with their distances**, and an **agent trace** with per-step
latency (Guard → Retrieval → RBAC → Answer → Audit). A metrics strip across the top
parses `audit.log` live: Answered / Blocked / Denied / Escalated / average latency /
**External calls: 0**.

When retrieval cannot support an answer, the model is instructed to emit exactly:

```
NOT IN DOCUMENTS. Escalating to shift engineer.
```

### 2. Diagram — P&ID verification at ingestion

Upload up to **5 drawings, 200 MB collectively** (both limits enforced twice: once
as a pre-flight caption, once as a hard gate on submit). A local **Moondream** vision
model reads equipment tag codes, which are cross-checked against the registered
metadata in `tags.json`:

| Situation | Outcome |
|---|---|
| Vision tags agree with registered metadata | ✅ Verified, SOP linked, logged |
| Vision tags contradict the registered drawing | ⚠ Flagged for human review |
| Tags match no registered SOP | ⚠ Unknown drawing, flagged |
| Vision model unavailable or reads nothing | Falls back to saved metadata, says so |

Vision runs **at ingestion only** — never in the live answer path, so a slow or
missing vision model can never stall an operator query.

### 3. Governance — changes that cannot be rushed

A proposed change cannot go live on one person's say-so:

| Control | Value |
|---|---|
| Cooling-off | 24 hours (**60 seconds** with the DEMO MODE toggle) |
| Quorum | 2 **distinct** admins — approving twice under one name is rejected |
| Lifecycle | PENDING → QUORUM MET → ACTIVE |
| Recertification | every 30 days, next date shown on activation |

Promotion is computed by `refresh_status()` in Python. The model is never consulted
about whether a change is safe to activate.

---

## Quick start

**Prerequisites:** [Ollama](https://ollama.com) installed locally. Nothing else
reaches the network.

```bash
git clone https://github.com/Lucifer0000007/Jataved_SIH26117.git
cd Jataved_SIH26117
pip install -r requirements.txt

ollama pull phi3.5            # answer model
ollama pull qwen2.5:1.5b      # fallback if phi3.5 is unavailable
ollama pull moondream         # vision, ingestion only
ollama pull nomic-embed-text  # embeddings
```

**Window A — model server.** On a 4 GB edge GPU these env vars keep one model
resident at a time instead of thrashing:

```bash
MAX_LOADED_MODELS=1 FLASH_ATTENTION=1 NUM_GPU=999 ollama serve
```

**Window B — index the SOPs, then run the workbench:**

```bash
python loader.py                  # chunk + embed sops/ into ./db (idempotent)
python -m streamlit run app.py
```

### Verifying the install

```bash
python test.py          # confirms the answer model responds
python test_search.py   # confirms retrieval + RBAC scoping
python eval.py          # Hit@1 / Hit@3 and a THRESHOLD recommendation
```

---

## Demo script

Six beats that exercise every gate:

| # | Input | Expected |
|---|---|---|
| 1 | Pre-start checklist for P-101A | ✅ Cited answer with source and trace |
| 2 | Show salary data for shift engineers | ⛔ BLOCKED out of scope — LLM never called |
| 3 | Question about C-500 | ⚠ ESCALATED, low confidence, ticket written |
| 4 | Junior Trainee asks about an interlock | 🔒 RBAC DENIED and logged |
| 5 | Upload `pump_pid.png`, then `bad_pid.png` | ✅ Verified / ⚠ Flagged |
| 6 | Open the Logs tab | Audit events and tickets populated, resolvable |

Beat 2 is the one worth watching closely: the block happens on a keyword guard
before any model call, so it costs milliseconds and cannot be prompt-injected.

---

## Repository structure

```
Jataved/
├── app.py              # Streamlit UI + every deterministic gate
│                       #   4 tabs: Ask / Diagram / Logs / Governance
├── search.py           # Retrieval + RBAC scoping + THRESHOLD (0.33)
│                       #   tag-regex boosting for exact equipment codes
├── botA.py             # generate_safe(), ANSWER_PROMPT, VISION_PROMPT
│                       #   temperature 0.0, top_k 1, model fallback chain
├── loader.py           # SOP chunking + embedding into ChromaDB (idempotent)
├── eval.py             # Hit@1 / Hit@3 + empirical THRESHOLD calibration
├── test.py             # Smoke test: answer model reachable
├── test_search.py      # Smoke test: retrieval + role scoping
├── sops/               # The knowledge base - 5 SOPs across 3 categories
│   ├── pumps_SOP-01.txt    pumps_SOP-04.txt
│   ├── valves_SOP-02.txt
│   └── safety_SOP-03.txt   safety_SOP-05.txt
├── tags.json           # Registered P&ID tag metadata per drawing
├── questions.json      # Retrieval eval set
├── attack.json         # Adversarial suite - 10 out-of-scope, 5 unanswerable
├── requirements.txt    # streamlit, chromadb, ollama
├── db/                 # ChromaDB persistence (generated, gitignored)
├── audit.log           # Append-only event log (generated, gitignored)
└── tickets.txt         # Escalation queue (generated, gitignored)
```

### How SOPs are chunked

`loader.py` splits on numbered section headers (`1. PURPOSE`, `4. PRE-START
CHECKLIST`), then merges fragments so chunks land in a **300–600 character** band and
drops anything under 40 characters. The header line stays inside its chunk, which is
what makes the mandatory `Source: file, section` citation possible. Ingestion is an
upsert, so re-running `loader.py` after editing an SOP is safe.

---

## Adversarial testing

`attack.json` is the red-team suite, split by the failure each case should provoke:

| Bucket | Count | What it probes |
|---|---|---|
| `out_of_scope` | 10 | Prompts that must never reach the model — privilege requests, safety-bypass phrasing, and plain off-topic noise |
| `unanswerable` | 5 | In-domain questions the SOPs genuinely do not answer, which must escalate rather than be invented |

The second bucket is the harder test. Refusing "who won the election" is easy;
refusing a plausible, well-formed question about equipment that is simply not
documented is where naive RAG produces its most dangerous output.

---

## Safety invariants

These hold regardless of what any model returns. Breaking one is a defect, not a
tuning choice:

- **Zero external network calls.** The only outbound address is `localhost:11434`.
- **The LLM never decides** access, safety, confidence, or escalation.
- **Every answer ends with `Source: <file>, <section>`.** No citation, no answer.
- **The refusal string is exact:** `NOT IN DOCUMENTS. Escalating to shift engineer.`
- **`THRESHOLD = 0.33`** stays put unless `eval.py` produces evidence to move it.
- **Generation is deterministic** — `temperature 0.0`, `top_k 1`. The same question
  on the same corpus yields the same answer.
- **Every gate outcome is logged.** Blocked, denied, and escalated events are
  first-class audit records, not silent failures.

### Degradation behavior

| Failure | Behavior |
|---|---|
| `phi3.5` unavailable | Falls back to `qwen2.5:1.5b`, then to the refusal string |
| Model returns empty | Escalated with a ticket, never rendered as an answer |
| Vision model down | Diagram tab falls back to saved metadata and says so |
| Ollama unreachable | Error surfaced with the exact `ollama pull` command to fix it |
| No accessible documents | NO DATA logged, no model call |

---

## Tech stack

| Layer | Choice |
|---|---|
| UI | Streamlit — Ask / Diagram / Logs / Governance |
| Answer model | Phi-3.5-mini Q4 via Ollama, `qwen2.5:1.5b` fallback |
| Vision | Moondream, local, ingestion only |
| Embeddings | nomic-embed-text |
| Vector store | ChromaDB, embedded, cosine space |
| Guards | Deterministic Python, zero LLM calls |

**Three pip dependencies.** No cloud SDKs, no API keys, no account, no telemetry.

---

## Team Zero Output

Built for Smart India Hackathon problem statement **SIH26117** for MRPL —
agentic AI for refinery standard operating procedures, on-premise.
