import re
import ollama

GENERATION_PARAMS = {
    "temperature": 0.0,
    "top_k": 1,
    "num_ctx": 2048,
    "num_predict": 220,
    "repeat_penalty": 1.1,
}

ANSWER_PROMPT = (
    "You are a refinery assistant. Answer the user's question using ONLY the provided context.\n"
    "Quote the exact relevant lines from the context. End your answer with 'Source: <filename>, <section>'.\n"
    "If the context does NOT contain the answer, output EXACTLY:\n"
    "'NOT IN DOCUMENTS. Escalating to shift engineer.'\n"
    "Do NOT add any preamble, apologies, or guesses.\n\n"
    "Context:\n{context}\n\n"
    "Question: {query}\n\n"
    "Answer:"
)

VISION_PROMPT = "List equipment tag codes visible in this diagram, like P-101A. Output only the codes, comma separated."

def extract_tag_codes(text: str) -> list[str]:
    return re.findall(r'[A-Z]{1,3}-?\d+[A-Z]?', text)

def generate_safe(prompt: str = "", context: str = "", query: str = "", vision_img=None) -> str:
    if context:
        full_prompt = ANSWER_PROMPT.replace("{context}", context).replace("{query}", query)
    else:
        full_prompt = prompt
    for model in ("phi3.5", "qwen2.5:1.5b"):
        try:
            r = ollama.generate(model=model, prompt=full_prompt, options=GENERATION_PARAMS)
            txt = (r["response"] or "").strip()
            if txt:
                return txt
            print("EMPTY FROM", model)
        except Exception as e:
            print("MODEL FAIL:", model, e)
    return "NOT IN DOCUMENTS. Escalating to shift engineer."