import os
import csv
import json
import requests

OPENROUTER_API_KEY = "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"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Recommended: A fast, smart model that handles JSON reliably.
MODEL = "openai/gpt-oss-120b:free" 


def get_graph_schema():
    graph_schema = """
    ### TARGET GRAPH SCHEMA
    
    NODES & ATTRIBUTES:
    - (:Subject {identity: string, role: string, department: string})
    - (:Resource {identity: string, type: string, classification: string})
    - (:Environment {time_window: string, location: string, ip_range: string})
    
    RELATIONSHIPS & ATTRIBUTES:
    - (:Subject) -[:PERFORMS_ACTION {action_name: string, decision: "grant" | "deny"}]-> (:Resource)
    - (:Subject) -[:HAS_RELATION_WITH {type: "owner" | "supervisor" | "peer"}]-> (:Resource)
    - (:PERFORMS_ACTION) -[:CONSTRAINED_BY]-> (:Environment)
    """    
    return graph_schema

def extract_acp_statement(text: str) -> dict:
    """
    Calls OpenRouter LLM to analyze text, extract entities, and classify the ACP model.
    """
    
    graph_schema= get_graph_schema()
    
    system_prompt = """
    You are an expert Access Control Policy (ACP) analyzer. 
    Analyze the user's text and extract the access control semantics into a strict JSON format.

    Your task is to populate this exact JSON schema:
    {
      "is_policy": boolean,
      "subject": string | null,
      "action": string | null,
      "resource": string | null,
      "decision": "grant" | "deny" | null,
      "model_type": "RBAC" | "ABAC" | "ReBAC" | null,
      "conditions": string | null
    }

    Classification Rules:
    - RBAC: Based purely on a user's role or tier.
    - ABAC: Involves environmental or dynamic attributes.
    - ReBAC: Involves a relationship between entities.

    If 'is_policy' is false, return null for all other fields.
    Respond ONLY with valid, raw JSON. Do not use markdown formatting like ```json.
    """

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://your-app-domain.com](https://your-app-domain.com)",
        "X-Title": "ACP Extractor Pipeline"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"}, 
        "temperature": 0.0 # Deterministic output
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result_content = response.json()['choices'][0]['message']['content']
        return json.loads(result_content)
    except Exception as e:
        return {"error": str(e), "original_text": text}

def validate_acp_semantics(original_text: str, extracted_json: dict) -> dict:
    """
    Calls OpenRouter LLM to perform Natural Language Inference (NLI).
    Checks if the extracted JSON accurately reflects the original text without hallucination.
    """
    system_prompt = """
    You are a strict semantic validator (Natural Language Inference). 
    Your job is to compare a human's original text against an extracted JSON policy.
    
    Determine if the JSON accurately and completely reflects the intent of the original text.
    Check for hallucinations (data in JSON not present in text) and omissions (critical data in text missing from JSON).
    
    Output ONLY in this exact JSON schema:
    {
      "is_coherent": boolean, // true if the JSON perfectly matches the text intent, false otherwise
      "reason": string // A brief, 1-sentence explanation of your validation decision
    }
    """
    
    # We pass both the original text and the parsed JSON to the validator
    user_prompt = f"Original Text: {original_text}\n\nExtracted JSON: {json.dumps(extracted_json)}"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://your-app-domain.com](https://your-app-domain.com)",
        "X-Title": "ACP Validator Pipeline"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"}, 
        "temperature": 0.0 
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result_content = response.json()['choices'][0]['message']['content']
        return json.loads(result_content)
    except Exception as e:
        return {"is_coherent": False, "reason": f"Validation API error: {str(e)}"}

def process_csv(file_path: str):
    """
    Loops through the CSV and processes each rule, including semantic validation.
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
            
            # 1. Extract the Data
            extracted_data = extract_acp_statement(rule_text)
            
            if isinstance(extracted_data, dict):
                extracted_data["rule_id"] = rule_id
                is_policy = extracted_data.get("is_policy", False)
                
                # 2. Validate Semantics (Only if it was identified as a policy)
                if is_policy and "error" not in extracted_data:
                    # Create a copy without the rule_id for cleaner validation context
                    clean_extracted = {k: v for k, v in extracted_data.items() if k != 'rule_id'}
                    validation_result = validate_acp_semantics(rule_text, clean_extracted)
                    
                    # Append validation results to the final payload
                    extracted_data["validation"] = validation_result
                
                # 3. Output the result
                print(json.dumps(extracted_data, separators=(',', ':')))
                
                # If you want to process the whole file, remove the 'break'
                # Currently left in to test the first successful policy extraction
                if is_policy:      
                    break

if __name__ == "__main__":
    # Adjust path if needed
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "1_natural_policy.csv")
    process_csv(csv_path)