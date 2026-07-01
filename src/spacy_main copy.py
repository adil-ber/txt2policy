import os
import csv
import json
import spacy

# Load the small English NLP model
nlp = spacy.load("en_core_web_sm")

# Define keyword sets for heuristic matching
GRANT_KEYWORDS = {"allow", "permit", "grant", "can", "may", "authorized"}
DENY_KEYWORDS = {"deny", "block", "restrict", "cannot", "must not", "unauthorized", "forbid"}

RBAC_KEYWORDS = {"role", "admin", "manager", "user", "employee", "tier"}
ABAC_KEYWORDS = {"time", "location", "ip", "device", "department", "attribute", "business hours"}
REBAC_KEYWORDS = {"owner", "friend", "parent", "supervisor", "belongs to", "creator"}

def extract_acp_statement(text: str) -> dict:
    """
    Uses spaCy NLP to analyze text and extract access control semantics based on grammar and rules.
    """
    # Process text with spaCy
    doc = nlp(text)
    
    result = {
        "is_policy": False,
        "subject": None,
        "action": None,
        "resource": None,
        "decision": None,
        "model_type": None,
        "conditions": None
    }
    
    text_lower = text.lower()

    # 1. Determine Decision (Grant/Deny) and if it's a policy
    if any(word in text_lower for word in GRANT_KEYWORDS):
        result["decision"] = "grant"
        result["is_policy"] = True
    elif any(word in text_lower for word in DENY_KEYWORDS):
        result["decision"] = "deny"
        result["is_policy"] = True

    # If it doesn't look like a policy, return early
    if not result["is_policy"]:
        return result

    # 2. Determine Model Type based on keyword frequency
    if any(word in text_lower for word in REBAC_KEYWORDS):
        result["model_type"] = "ReBAC"
    elif any(word in text_lower for word in ABAC_KEYWORDS):
        result["model_type"] = "ABAC"
    elif any(word in text_lower for word in RBAC_KEYWORDS):
        result["model_type"] = "RBAC"

    # 3. Extract Subject, Action, and Resource using Dependency Parsing
    condition_tokens = []
    in_condition_clause = False

    for token in doc:
        # Detect condition clauses (e.g., starts with "if", "when", "during")
        if token.text.lower() in {"if", "when", "during", "provided", "unless"}:
            in_condition_clause = True

        if in_condition_clause:
            condition_tokens.append(token.text)
            continue # Skip extracting subject/action from the condition clause

        # Subject: usually a nominal subject attached to a verb
        if token.dep_ in ("nsubj", "nsubjpass") and not result["subject"]:
            result["subject"] = token.text

        # Action: usually the root verb of the sentence
        if token.pos_ == "VERB" and token.dep_ == "ROOT" and not result["action"]:
            result["action"] = token.lemma_

        # Resource: usually a direct object or object of a preposition
        if token.dep_ in ("dobj", "pobj") and not result["resource"]:
            # Capture the compound noun if it exists (e.g., "database server" instead of "server")
            resource_chunks = [c for c in doc.noun_chunks if token in c]
            if resource_chunks:
                result["resource"] = resource_chunks[0].text
            else:
                result["resource"] = token.text

    # 4. Clean up conditions
    if condition_tokens:
        result["conditions"] = " ".join(condition_tokens).strip()

    return result

def process_csv(file_path: str):
    """
    Loops through the CSV and processes each rule using spaCy.
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
            
            # Extract data using the spaCy function
            extracted_data = extract_acp_statement(rule_text)
            
            if extracted_data.get("is_policy"):
                extracted_data["rule_id"] = rule_id
                
                # Output the result as JSON
                print(json.dumps(extracted_data, indent=2))
                break



if __name__ == "__main__":
    # Adjust path if needed
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "1_natural_policy.csv")
    process_csv(csv_path)