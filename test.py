import ollama
params = {"temperature": 0.0, "top_k": 1, "num_ctx": 2048, "num_predict": 220, "repeat_penalty": 1.1}
try:
    print(ollama.generate(model="phi3.5", prompt="Say OK", options=params))
except Exception as e:
    print("HIDDEN ERROR:", e)