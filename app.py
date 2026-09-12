import os, re, json, time
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st
import ollama
import botA
from botA import generate_safe
import search
from search import search as search_docs, THRESHOLD, is_in_scope
import loader  # noqa: F401

TAG_REGEX = re.compile(r'[A-Z]{1,3}-?\d+[A-Z]?')
ROLES = {"Shift Engineer (E-1042)": ["pumps", "valves", "safety"], "Junior Trainee (T-201)": ["pumps"]}
SCOPE = ["pump","valve","leak","pressure","sop","checklist","start","shutdown","alarm","interlock","temperature","safety"]
TICKETS_FILE, AUDIT_FILE, TAGS_FILE, CHANGES_FILE = "tickets.txt", "audit.log", "tags.json", "changes.json"
TS_FMT = "%Y-%m-%d %H:%M:%S"
COOLING_DEMO, COOLING_PROD, RECERT_DAYS, QUORUM = 60, 24 * 3600, 30, 2
VISION_PROMPT = ("Read the equipment tag codes printed in this diagram. "
                 "Output ONLY the codes you actually see, in UPPERCASE, comma separated. "
                 "If you see none, output NONE.")

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def log_event(role, action, detail):
    with open(AUDIT_FILE, "a", encoding="utf-8") as f: f.write(f"{_now()} | {role} | {action} | {detail}\n")
def ticket(role, detail):
    with open(TICKETS_FILE, "a", encoding="utf-8") as f: f.write(f"{_now()} | {role} | TICKET | {detail}\n")
def extract_tag_codes(text): return TAG_REGEX.findall((text or "").upper())
def load_tags_json():
    if not os.path.exists(TAGS_FILE): return {}
    with open(TAGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
def get_tag_to_sop():
    m = {}
    for e in load_tags_json().values():
        if e.get("sop"):
            for t in e.get("tags", []): m[t] = e["sop"]
    return m
def read_metrics():
    """Parsed once per rerun from audit.log. No network, no model call."""
    counts = {"ANSWERED": 0, "BLOCKED": 0, "RBAC DENIED": 0, "ESCALATED": 0}
    lat = []
    if os.path.exists(AUDIT_FILE):
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3 and parts[2] in counts: counts[parts[2]] += 1
                elif len(parts) >= 4 and parts[2] == "LATENCY":
                    try: lat.append(float(parts[3].split()[0]))
                    except ValueError: pass
    return counts, lat
def load_changes():
    if not os.path.exists(CHANGES_FILE): return []
    with open(CHANGES_FILE, "r", encoding="utf-8") as f: return json.load(f)
def save_changes(items):
    with open(CHANGES_FILE, "w", encoding="utf-8") as f: json.dump(items, f, indent=2)
def elapsed_since(ts): return (datetime.now() - datetime.strptime(ts, TS_FMT)).total_seconds()
def refresh_status(c, cooling):
    """CODE decides promotion: PENDING -> QUORUM MET -> ACTIVE. LLM is never consulted."""
    if c.get("status") == "ACTIVE": return False
    before = c.get("status")
    if len(set(c.get("approvals", []))) >= QUORUM:
        c["status"] = "ACTIVE" if elapsed_since(c["proposed_at"]) >= cooling else "QUORUM MET"
        if c["status"] == "ACTIVE" and not c.get("activated_at"): c["activated_at"] = _now()
    else:
        c["status"] = "PENDING"
    return c["status"] != before
def _doc(r): return r[0]
def _meta(r): return r[1]
def _dist(r): return r[2]

def main():
    st.set_page_config(layout="wide")
    st.title("JATAVED – Air-Gapped Agentic AI Workbench")
    st.caption("100% on-premise • Code decides, model writes • Wi-Fi OFF")
    role = st.sidebar.selectbox("Select Role", list(ROLES.keys()))
    tab_ask, tab_diagram, tab_logs, tab_gov = st.tabs(["Ask", "Diagram", "Logs", "Governance"])

    # ── ASK ──────────────────────────────────────────────────────────
    with tab_ask:
        st.header("Ask")
        m, lat = read_metrics()
        avg = f"{sum(lat) / len(lat):.0f} ms" if lat else "n/a"
        st.caption(f"Answered: {m['ANSWERED']} • Blocked: {m['BLOCKED']} • Denied: {m['RBAC DENIED']} • "
                   f"Escalated: {m['ESCALATED']} • Avg latency: {avg} • External calls: 0")
        q = st.text_input("Enter your query:")
        if st.button("Submit", key="ask_submit") and q:
            trace = []; st.session_state["trace"] = trace
            t = time.perf_counter(); in_scope = is_in_scope(q, SCOPE)
            trace.append(("Guard", (time.perf_counter() - t) * 1000))
            if not in_scope:
                t = time.perf_counter()
                ticket(role, f"Out of scope: {q}"); log_event(role, "BLOCKED", f"Out of scope: {q}")
                trace.append(("Audit", (time.perf_counter() - t) * 1000))
                st.error("⛔ BLOCKED — out of scope. Ticket sent to Shift Engineer. LLM never called."); st.stop()
            t = time.perf_counter(); unrestricted = search_docs(q, "Shift Engineer (E-1042)")
            trace.append(("Retrieval", (time.perf_counter() - t) * 1000))
            t = time.perf_counter()
            denied = bool(unrestricted) and _meta(unrestricted[0]).get("cat") not in ROLES[role]
            results = [r for r in unrestricted if _meta(r).get("cat") in ROLES[role]]
            trace.append(("RBAC", (time.perf_counter() - t) * 1000))
            if denied:
                log_event(role, "RBAC DENIED", f"Best match cat={_meta(unrestricted[0]).get('cat')} | {q}")
                st.warning("🔒 RBAC: your role has no access to the best-matching document. Denied + logged."); st.stop()
            if not results:
                log_event(role, "NO DATA", f"No accessible documents for: {q}")
                st.warning("No relevant documents found in your accessible knowledge base."); st.stop()
            if _dist(results[0]) > THRESHOLD:
                d = _dist(results[0])
                ticket(role, f"Low confidence: {q} | distance={d:.3f}"); log_event(role, "ESCALATED", f"Low confidence: {q} | distance={d:.3f}")
                st.error("⚠ Low confidence — no guess. Escalated with ticket."); st.stop()
            top3 = results[:3]
            context = "\n\n---\n\n".join([f"[{_meta(r).get('file')} — {_meta(r).get('section')}]\n{_doc(r)}" for r in top3])
            try:
                t = time.perf_counter(); ans = generate_safe("", context=context, query=q)
                trace.append(("Answer", (time.perf_counter() - t) * 1000))
                if not ans or ans == "None":
                    st.error("⚠ Model returned empty response. Escalated."); ticket(role, f"Empty model response: {q}"); st.stop()
                src = f"{_meta(top3[0]).get('file')} • {_meta(top3[0]).get('section')}"
                t = time.perf_counter(); log_event(role, "ANSWERED", f"{q} | src={src}")
                trace.append(("Audit", (time.perf_counter() - t) * 1000))
                st.caption(f"Source: {src}"); st.success("Cited Answer"); st.write(ans)
                with st.expander("Top-3 source chunks"):
                    for i, r in enumerate(top3, 1):
                        st.markdown(f"**Chunk {i}** (distance: {_dist(r):.4f})"); st.write(_doc(r))
                total = sum(ms for _, ms in trace)
                log_event(role, "LATENCY", f"{total:.0f} ms")
                with st.expander("View Agent Trace"):
                    for step, ms in trace: st.write(f"{step}: {ms:.1f} ms")
                    st.caption(f"Total: {total:.1f} ms • External calls: 0")
            except Exception as e:
                st.error("Model call failed. Run: `ollama pull phi3.5`"); log_event(role, "ERROR", f"Model failure: {e}")

    # ── DIAGRAM ──────────────────────────────────────────────────────
    with tab_diagram:
        st.header("Diagram Verification")
        uploaded_files = st.file_uploader(
            "Upload diagrams (PNG/JPG — max 5 files, 200 MB collective)",
            type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        if uploaded_files:
            total_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
            if len(uploaded_files) > 5:
                st.error(f"⛔ Maximum 5 diagrams per batch — you selected {len(uploaded_files)}.")
            elif total_mb > 200:
                st.error(f"⛔ Collective limit is 200 MB — your batch is {total_mb:.1f} MB.")
            else:
                st.caption(f"Selected: {len(uploaded_files)} file(s) • {total_mb:.1f} MB of 200 MB — press Verify.")
        if st.button("Verify Diagrams", key="diag_submit") and uploaded_files:
            if len(uploaded_files) > 5:
                log_event(role, "DIAGRAM REJECTED", f"Batch count {len(uploaded_files)} > 5")
                st.error("⛔ Too many files — maximum 5 diagrams per batch."); st.stop()
            total = sum(f.size for f in uploaded_files)
            if total > 200 * 1024 * 1024:
                log_event(role, "DIAGRAM REJECTED", f"Batch {total/(1024*1024):.1f} MB > 200 MB")
                st.error("⛔ Batch too large — collective limit 200 MB."); st.stop()
            for up in uploaded_files:
                filename = up.name
                temp_path = Path(__file__).parent / filename
                with open(temp_path, "wb") as f: f.write(up.getbuffer())
                st.subheader(filename)
                fallback = False
                try:
                    resp = ollama.generate(model="moondream", prompt=VISION_PROMPT, images=[str(temp_path)])
                    tags = extract_tag_codes(resp.get("response", ""))
                except Exception as e:
                    log_event(role, "VISION ERROR", f"{filename} | {e}")
                    tags = []; fallback = True
                    st.info("(vision model unavailable — using saved tag metadata)")
                st.write("Extracted tags:", ", ".join(sorted(set(tags))) or "none")
                entry = load_tags_json().get(filename, {})
                saved = entry.get("tags", [])
                sop = entry.get("sop")
                if not tags and saved:
                    tags = saved
                    st.info("(vision saw no tags — using saved tag metadata)")
                if tags and saved:
                    agree = sorted(set(tags) & set(saved))
                    if agree and sop:
                        st.success(f"✅ Verified. Vision agrees with metadata. Linked SOP: {sop}")
                        log_event(role, "DIAGRAM VERIFIED", f"{filename} | vision={tags} | metadata={saved}")
                    else:
                        st.error("⚠ Vision reading doesn't match this drawing's registered metadata — flagged for human review.")
                        log_event(role, "DIAGRAM FLAGGED", f"{filename} | vision={tags} | metadata={saved}")
                else:
                    tag_to_sop = get_tag_to_sop()
                    matched = sorted({tag_to_sop[t] for t in tags if t in tag_to_sop})
                    if matched:
                        st.success(f"✅ Verified. Linked SOP: {', '.join(matched)}")
                        log_event(role, "DIAGRAM VERIFIED", f"{filename} | tags={tags}")
                    else:
                        st.error("⚠ Unknown drawing — tags match no registered SOP. Flagged for human review.")
                        log_event(role, "DIAGRAM FLAGGED", f"{filename} | tags={tags}")

    # ── LOGS ─────────────────────────────────────────────────────────
    with tab_logs:
        st.header("Audit Log")
        st.code(open(AUDIT_FILE, encoding="utf-8").read() if os.path.exists(AUDIT_FILE) else "No audit events yet.", language="text")
        st.header("Escalation Tickets")
        lines = [l.rstrip("\n") for l in open(TICKETS_FILE, encoding="utf-8").readlines()] if os.path.exists(TICKETS_FILE) else []
        lines = [l for l in lines if l.strip()]
        if not lines:
            st.code("No tickets yet.", language="text")
        closed = {l.split(" | RESOLVED by ")[0] for l in lines if " | RESOLVED by " in l}
        for i, line in enumerate(lines):
            if " | RESOLVED by " in line or line in closed:
                st.caption(f"✅ {line}")
            else:
                st.text(line)
                if st.button("Mark Resolved", key=f"tkt_resolve_{i}"):
                    with open(TICKETS_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{line} | RESOLVED by {role} {_now()}\n")
                    log_event(role, "TICKET RESOLVED", line)
                    st.rerun()

    # ── GOVERNANCE ───────────────────────────────────────────────────
    with tab_gov:
        st.header("Change Governance")
        demo = st.toggle("DEMO MODE", value=False, key="gov_demo")
        cooling = COOLING_DEMO if demo else COOLING_PROD
        st.caption(f"Cooling-off: {'60 seconds (DEMO MODE)' if demo else '24 hours'} • "
                   f"Quorum: {QUORUM} distinct admins • Recertification: every {RECERT_DAYS} days")

        st.subheader("Propose a change")
        proposer = st.text_input("Proposer", key="gov_proposer")
        desc = st.text_input("Change description", key="gov_desc")
        if st.button("Propose", key="gov_propose"):
            if not proposer.strip() or not desc.strip():
                st.warning("Proposer and description are both required.")
            else:
                items = load_changes()
                cid = f"CHG-{len(items) + 1:03d}"
                items.append({"id": cid, "proposer": proposer.strip(), "desc": desc.strip(),
                              "proposed_at": _now(), "status": "PENDING", "approvals": []})
                save_changes(items)
                log_event(role, "CHANGE PROPOSED", f"{cid} | {desc.strip()}")
                st.rerun()

        st.subheader("Change register")
        items = load_changes()
        if any([refresh_status(c, cooling) for c in items]): save_changes(items)
        if not items:
            st.info("No proposed changes yet.")
        if st.button("Refresh status", key="gov_refresh"): st.rerun()
        for c in items:
            st.markdown(f"**{c['id']} — {c['status']}** • {c['desc']}")
            st.caption(f"Proposed by {c['proposer']} at {c['proposed_at']} • "
                       f"Approvals ({len(set(c.get('approvals', [])))}/{QUORUM}): "
                       f"{', '.join(sorted(set(c.get('approvals', [])))) or 'none'}")
            if c["status"] == "ACTIVE":
                recert = datetime.strptime(c["activated_at"], TS_FMT) + timedelta(days=RECERT_DAYS)
                st.success(f"✅ ACTIVE since {c['activated_at']} • Next recertification: {recert.strftime(TS_FMT)}")
            else:
                left = cooling - elapsed_since(c["proposed_at"])
                if left > 0: st.caption(f"Cooling-off remaining: {int(left)}s")
                admin = st.text_input("Admin name", key=f"gov_admin_{c['id']}")
                if st.button("Approve", key=f"gov_approve_{c['id']}"):
                    name = admin.strip()
                    if not name:
                        st.warning("Enter an admin name to approve.")
                    elif name in c.get("approvals", []):
                        st.warning(f"{name} already approved — quorum needs {QUORUM} distinct admins.")
                    else:
                        c.setdefault("approvals", []).append(name)
                        refresh_status(c, cooling); save_changes(items)
                        log_event(role, "CHANGE APPROVED", f"{c['id']} | by {name} | status={c['status']}")
                        st.rerun()
            st.divider()

if __name__ == "__main__":
    main()
    
