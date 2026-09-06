import os, re, json
from datetime import datetime
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
TICKETS_FILE, AUDIT_FILE, TAGS_FILE = "tickets.txt", "audit.log", "tags.json"
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
def _doc(r): return r[0]
def _meta(r): return r[1]
def _dist(r): return r[2]

def main():
    st.set_page_config(layout="wide")
    st.title("JATAVED – Air-Gapped Agentic AI Workbench")
    st.caption("100% on-premise • Code decides, model writes • Wi-Fi OFF")
    role = st.sidebar.selectbox("Select Role", list(ROLES.keys()))
    tab_ask, tab_diagram, tab_logs = st.tabs(["Ask", "Diagram", "Logs"])

    # ── ASK ──────────────────────────────────────────────────────────
    with tab_ask:
        st.header("Ask")
        q = st.text_input("Enter your query:")
        if st.button("Submit", key="ask_submit") and q:
            if not is_in_scope(q, SCOPE):
                ticket(role, f"Out of scope: {q}"); log_event(role, "BLOCKED", f"Out of scope: {q}")
                st.error("⛔ BLOCKED — out of scope. Ticket sent to Shift Engineer. LLM never called."); st.stop()
            unrestricted = search_docs(q, "Shift Engineer (E-1042)")
            if unrestricted and _meta(unrestricted[0]).get("cat") not in ROLES[role]:
                log_event(role, "RBAC DENIED", f"Best match cat={_meta(unrestricted[0]).get('cat')} | {q}")
                st.warning("🔒 RBAC: your role has no access to the best-matching document. Denied + logged."); st.stop()
            results = [r for r in unrestricted if _meta(r).get("cat") in ROLES[role]]
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
                ans = generate_safe("", context=context, query=q)
                if not ans or ans == "None":
                    st.error("⚠ Model returned empty response. Escalated."); ticket(role, f"Empty model response: {q}"); st.stop()
                src = f"{_meta(top3[0]).get('file')} • {_meta(top3[0]).get('section')}"
                log_event(role, "ANSWERED", f"{q} | src={src}")
                st.caption(f"Source: {src}"); st.success("Cited Answer"); st.write(ans)
                with st.expander("Top-3 source chunks"):
                    for i, r in enumerate(top3, 1):
                        st.markdown(f"**Chunk {i}** (distance: {_dist(r):.4f})"); st.write(_doc(r))
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
        st.code(open(TICKETS_FILE, encoding="utf-8").read() if os.path.exists(TICKETS_FILE) else "No tickets yet.", language="text")

if __name__ == "__main__":
    main()
    
