import os
import csv
import json
import requests
from gliner import GLiNER
import config

OPENROUTER_API_KEY = "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"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-oss-120b:free"

roles_set = set()

# Initialize GLiNER globally so it only loads into memory once
print("Loading GLiNER model...")
gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
print("GLiNER model loaded.")

def get_graph_schema():
    return """
    ### TARGET GRAPH SCHEMA
    
    NODES & ATTRIBUTES:
    - (:Staff {id: string, name: string})
    - (:Protocol {id: string, name: string, details: string})
    - (:Invoice {id: string, code: string, status: string, amount: float})
    
    RELATIONSHIPS & ATTRIBUTES:
    - (:Staff) -[:APPLY {since: int, conditions: string}]-> (:Protocol)
    - (:Staff) -[:WORK_TOGETHER {since: int, conditions: string}]-> (:Staff)
    """

def run_gliner_extraction(text: str) -> dict:
    """
    Step 1: Use GLiNER to rapidly extract raw entity spans from the text.
    """
    labels = ["subject", "action", "resource", "attribute", "decision", "condition", "target specification"]
    entities = gliner_model.predict_entities(text, labels, threshold=0.4)
    
    # Restructure the GLiNER output into a clean dictionary for the LLM
    extracted_spans = {}
    for entity in entities:
        extracted_spans[entity["label"]] = entity["text"]
        
    print(f"GLiNER extracted spans: {extracted_spans}")
    return extracted_spans

def map_and_validate_acp(original_text: str, gliner_spans: dict) -> dict:
    """
    Step 2: Calls OpenRouter LLM to normalize the GLiNER spans to the schema, 
    resolve semantics, and validate against the original text in one pass.
    """
    graph_schema = get_graph_schema()
    print(json.dumps(gliner_spans))
    system_prompt = f"""
    You are an expert Access Control Policy (ACP) semantic mapper and validator.
    You will receive the user's original text and a set of raw entities extracted by an NLP model.
    
    Your goal is twofold:
    1. Map the raw entities strictly to the provided graph database security model.
    2. Validate if your mapped JSON completely and accurately reflects the original text without hallucinations.

    {graph_schema}

    #### ROLES SET:
    {list(roles_set)}

    Your task is to populate this exact JSON schema:
    {{
      "is_policy": boolean,
      "subject": string | null,
      "action": "TRAVERSE" | "CREATE" | "DELETE" | "AddProperty" | "RemoveProperty" | "ReadProperty" | null,
      "resource": string | null,
      "attribute": string | null,
      "decision": "grant" | "deny" | null,
      "Target Specification (E)": string | null,
      "conditions": string | null,
      "validation": {{
          "is_coherent": boolean,
          "reason": string
      }}
    }}

    Mapping Rules:
    - is_policy: True only if the text describes a clear access control rule.
    - subject: Match the raw subject to an existing role in the roles set, or define a new one.
    - action: Map the raw action verb to ONE of the strict graph actions: TRAVERSE, CREATE, DELETE, AddProperty, RemoveProperty, ReadProperty.
    - resource: Map to one of the defined graph schema nodes or relationships.
    - attribute: Target attribute names of the mentioned resource.
    - decision: Translate the raw intent to "grant" or "deny".
    - Target Specification (E): If the resource is a RELATION, describe any constraints regarding the source and target nodes. If just a node, return null.
    - conditions: Any dynamic attribute conditions.
    
    Validation Rules:
    - Set validation.is_coherent to true ONLY if the mapped JSON accurately and fully reflects the original text intent.
    - Set it to false if the raw extraction missed critical data or if the mapping hallucinated information.
    - Provide a 1-sentence reason.

    If 'is_policy' is false, return null for all fields except 'is_policy' and 'validation'.
    Respond ONLY with valid, raw JSON. Do not use markdown formatting like ```json.
    """

    user_prompt = f"Original Text: {original_text}\nRaw Extracted Entities: {json.dumps(gliner_spans)}"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://your-app-domain.com](https://your-app-domain.com)",
        "X-Title": "ACP Mapper & Validator"
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
        return {"error": str(e), "original_text": original_text}


def process_csv(file_path: str):
    """
    Loops through the CSV, running the GLiNER extraction and LLM mapping/validation pipeline.
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    i = 0
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            rule_id = row.get("rule_id", "").strip()
            rule_text = row.get("rule_text", "").strip()
            
            if not rule_text:
                continue
            
            # Step 1: Raw Extraction (Fast/Local)
            gliner_spans = run_gliner_extraction(rule_text)
            
            # Step 2: Normalization & Validation (LLM)
            final_data = map_and_validate_acp(rule_text, gliner_spans)
            
            if isinstance(final_data, dict):
                final_data["rule_id"] = rule_id
                
                # Update our live roles set
                detected_role = final_data.get("subject", None)
                if detected_role and detected_role not in roles_set:
                    print(f"New role detected: {detected_role}")
                    roles_set.add(detected_role)

                # Output the combined result
                print(json.dumps(final_data, separators=(',', ':')))
                
                i += 1
                if hasattr(config, 'LIMIT') and i == config.LIMIT:      
                    break

if __name__ == "__main__":
    # Adjust path if needed
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "1_natural_policy.csv")
    process_csv(csv_path)