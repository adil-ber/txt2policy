import os
import csv
import json
import requests

import config

OPENROUTER_API_KEY = "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"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Recommended: A fast, smart model that handles JSON reliably.
MODEL = "openai/gpt-oss-120b:free" 

roles_set = set()


def get_graph_schema():
    graph_schema = """
    ### TARGET GRAPH SCHEMA
    
    NODES & ATTRIBUTES:
    - (:Staff {id: string, name: string})
    - (:Protocol {id: string, name: string, details: string})
    - (:Invoice {id: string, code: string, status: string, amount: float})
    
    RELATIONSHIPS & ATTRIBUTES:
    - (:Staff) -[:APPLY {since: int, conditions: string}]-> (:Protocol)
    - (:Staff) -[:WORK_TOGETHER {since: int, conditions: string}]-> (:Staff)
    """    
    return graph_schema

def extract_acp_statement(text: str) -> dict:
    """
    Calls OpenRouter LLM to analyze text, extract entities, and classify the ACP model.
    """
    
    graph_schema= get_graph_schema()
    
    
    print(f"roles size: {len(roles_set)}")
    
    system_prompt = f"""
You are an expert Access Control Policy (ACP) analyzer mapping natural language to a graph database security model. 
    Analyze the user's text and extract the semantics into a strict JSON format.

    {graph_schema}

    #### ROLES SET:
    {roles_set}

    Your task is to populate this exact JSON schema:
    {{
      "is_policy": boolean,
      "subject": string | null,
      "action": "TRAVERSE" | "CREATE" | "DELETE" | "AddProperty" | "RemoveProperty" | "ReadProperty" | null,
      "resource": string | null,
      "attribute": string | null,
      "decision": "grant" | "deny" | null,
      "position": string | null,
      "conditions": string | null
    }}

    Definitions & Extraction Rules:
    - is_policy: True only if the text describes a clear access control rule.
    - subject: The role, user, or entity performing the action. (match it to an existing role in the roles set, if no similar role exists put the new role)
    - action: You MUST map the natural language verb to one of the strict graph actions:
        * TRAVERSE (e.g., access, view, read, traverse a node or relation)
        * CREATE (e.g., establish, make, build a node or relation)
        * DELETE (e.g., remove, destroy a node or relation)
        * AddProperty (e.g., update, add data to an existing node/relation)
        * RemoveProperty (e.g., delete an attribute)
        * ReadProperty (e.g., view, read, access data)
    - resource: The specific node label or relation label being acted upon. (the resource should be one of the defined graph schema nodes or relationships)
    - attributes: The target attribute names of the mentionned resource if specified. (the attributes should be one of the defined graph schema attributes for the mentioned resource)
    - decision: "grant" (allow/can) or "deny" (block/cannot/must not).
    - position: If the resource is a RELATION, describe any constraints regarding the source and target nodes (e.g., "only relations between Hospital Admin and Staff records"). If the resource is just a node, return null.
    - conditions: Any dynamic attribute conditions (e.g., "during business hours", "if they are the owner").

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


    i=0
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
                detected_role = extracted_data.get("subject", None)
                
                if detected_role and detected_role not in roles_set:
                    print(f"New role detected: {detected_role}")
                    roles_set.add(detected_role)

                """# 2. Validate Semantics (Only if it was identified as a policy)
                if is_policy and "error" not in extracted_data:
                    # Create a copy without the rule_id for cleaner validation context
                    clean_extracted = {k: v for k, v in extracted_data.items() if k != 'rule_id'}
                    validation_result = validate_acp_semantics(rule_text, clean_extracted)
                    
                    # Append validation results to the final payload
                    extracted_data["validation"] = validation_result
                """
                # 3. Output the result
                print(json.dumps(extracted_data, separators=(',', ':')))
                i+=1
                # If you want to process the whole file, remove the 'break'
                if i == config.LIMIT:      
                    break

if __name__ == "__main__":
    # Adjust path if needed
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "1_natural_policy.csv")
    process_csv(csv_path)