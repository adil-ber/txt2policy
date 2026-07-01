import os
import csv
import json
import spacy

# Load the small English NLP model
nlp = spacy.load("en_core_web_sm")

def extract_acp_statement(text: str) -> dict:
    """
    Uses spaCy dependency parsing and token attributes to analyze text,
    safely handling negations and dynamically detecting ACP models.
    """
    doc = nlp(text)
    
    result = {
        "is_policy": False,
        "subject": None,
        "action": None,
        "resource": None,
        "decision": "grant",  # Default to grant unless negation is found
        "model_type": "RBAC", # Default baseline
        "conditions": None
    }

    # --- 1. HANDLE NEGATION & DECISION ---
    # Look for explicit negation tokens anywhere in the sentence dependency tree
    has_negation = False
    for token in doc:
        # Catching "not", "n't", "never", "no"
        if token.dep_ == "neg" or token.text.lower() in {"cannot", "never", "forbidden", "prohibited"}:
            has_negation = True
            break
            
    if has_negation:
        result["decision"] = "deny"

    # --- 2. EXTRACT SUBJECT, ACTION, RESOURCE (GRAMMAR-BASED) ---
    condition_start_idx = None
    
    # Locate where a conditional clause starts (e.g., "if", "when", "during", "unless")
    for i, token in enumerate(doc):
        if token.text.lower() in {"if", "when", "during", "provided", "unless", "based on"}:
            condition_start_idx = i
            break

    # Extract nouns / noun phrases as structural units
    for chunk in doc.noun_chunks:
        # If this chunk belongs to the condition clause, skip it for core entity extraction
        if condition_start_idx is not None and chunk.start >= condition_start_idx:
            continue
            
        # Subject is typically the nominal subject (nsubj) of the sentence root
        if chunk.root.dep_ in {"nsubj", "nsubjpass"} and not result["subject"]:
            result["subject"] = chunk.text
            
        # Resource is typically the direct object (dobj) or object of a preposition (pobj)
        elif chunk.root.dep_ in {"dobj", "pobj", "attr"} and not result["resource"]:
            result["resource"] = chunk.text

    # Extract the main action verb
    for token in doc:
        if condition_start_idx is not None and token.i >= condition_start_idx:
            continue
        if token.pos_ == "VERB" and token.dep_ == "ROOT":
            result["action"] = token.lemma_
            break

    # --- 3. EXTRACT CONDITIONS & CLASSIFY MODEL TYPE ---
    if condition_start_idx is not None:
        condition_span = doc[condition_start_idx:]
        result["conditions"] = condition_span.text.strip()
        condition_text_lower = result["conditions"].lower()
        
        # Check if the condition describes a Relationship (ReBAC)
        if any(rel in condition_text_lower for rel in ["owner", "creator", "parent", "supervisor", "belong", "member of"]):
            result["model_type"] = "ReBAC"
        # Check if the condition describes environmental/object Attributes (ABAC)
        elif any(attr in condition_text_lower for attr in ["time", "date", "location", "ip", "device", "department", "clearance", "tier"]):
            result["model_type"] = "ABAC"
        else:
            result["model_type"] = "ABAC" # Conditions usually point to dynamic attributes
    else:
        # If no condition clause exists but the core subject uses specific attribute triggers
        if result["subject"] and any(attr in result["subject"].lower() for attr in ["department", "branch", "clearance"]):
            result["model_type"] = "ABAC"
        else:
            result["model_type"] = "RBAC" # Static assignment based purely on the Subject identity/role

    # Validate if it looks like an actionable policy sentence
    if result["subject"] and result["action"]:
        result["is_policy"] = True

    return result

def process_csv(file_path: str):
    """
    Loops through the CSV and processes each rule using the enhanced pipeline.
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            rule_id = row.get("rule_id", "").strip()
            rule_text = row.get("rule_text", "").strip()
            
            if not rule_text:
                continue
            
            extracted_data = extract_acp_statement(rule_text)
            
            if extracted_data.get("is_policy"):
                extracted_data["rule_id"] = rule_id
                print(json.dumps(extracted_data, indent=2))
                # Remove break statement if you wish to run across your entire file
                break

if __name__ == "__main__":
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "1_natural_policy.csv")
    process_csv(csv_path)