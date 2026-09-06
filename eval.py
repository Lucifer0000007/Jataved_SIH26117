import json
import os
import statistics
from search import search

def create_sample_questions():
    """Generates schema-compliant questions.json if missing."""
    if not os.path.exists("questions.json"):
        q_data = [
            {"q": "What PPE is mandatory for P-101A interaction?", "file": "pumps_SOP-01.txt"},
            {"q": "How do I safely establish flow using V-101?", "file": "pumps_SOP-01.txt"},
            {"q": "What to do if P-101A trips the main breaker?", "file": "pumps_SOP-01.txt"},
            {"q": "Who is within the scope of this procedure?", "file": "pumps_SOP-01.txt"},
            {"q": "Are LSH-201 level sensors covered here?", "file": "pumps_SOP-01.txt"}
        ]
        with open("questions.json", "w", encoding="utf-8") as f:
            json.dump(q_data, f, indent=2)

def run_eval():
    create_sample_questions()
    
    with open("questions.json", "r", encoding="utf-8") as f:
        questions = json.load(f)

    hit_1 = 0
    hit_3 = 0
    correct_distances = []
    wrong_distances = []
    
    role = "Shift Engineer (E-1042)"
    print(f"Evaluating as {role}...\n")

    for i, item in enumerate(questions, 1):
        q = item["q"]
        expected_file = item["file"]
        
        results = search(q, role, top=6)
        if not results:
            print(f"Q{i}: No results for query '{q}'")
            continue
            
        top_1_file = results[0][1]["file"]
        top_3_files = [r[1]["file"] for r in results[:3]]
        
        if top_1_file == expected_file:
            hit_1 += 1
        if expected_file in top_3_files:
            hit_3 += 1
            
        print(f"Q{i}: '{q}' \n   -> Top 1 Match: {top_1_file}")
        
        for doc, meta, dist in results:
            if meta["file"] == expected_file:
                correct_distances.append(dist)
            else:
                wrong_distances.append(dist)

    total_q = len(questions)
    
    print("\n--- EVALUATION METRICS ---")
    print(f"Hit@1: {(hit_1 / total_q) * 100:.2f}%")
    print(f"Hit@3: {(hit_3 / total_q) * 100:.2f}%")
    
    mean_correct = statistics.mean(correct_distances) if correct_distances else 0.0
    mean_wrong = statistics.mean(wrong_distances) if wrong_distances else 0.0
    
    print(f"Mean Distance (Correct Docs): {mean_correct:.4f}")
    print(f"Mean Distance (Wrong Docs):   {mean_wrong:.4f}")
    
    print("\n--- THRESHOLD RECOMMENDATION ---")
    if correct_distances and wrong_distances:
        suggested = (mean_correct + mean_wrong) / 2
        print(f"Suggested THRESHOLD: {suggested:.4f} (Midpoint between correct/wrong distances)")
    elif correct_distances:
        suggested = mean_correct + 0.1
        print(f"Suggested THRESHOLD: {suggested:.4f} (Mean Correct + 0.1)")

if __name__ == "__main__":
    run_eval()