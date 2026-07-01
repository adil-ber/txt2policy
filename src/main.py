import os
import csv
import json

from evaluator import RuleEvaluator
import config
import logging
import requests

OPENROUTER_API_KEY = "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"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Recommended: A fast, smart model that handles JSON reliably.
MODEL = "openai/gpt-oss-120b" 

#roles_set = set()
#to have exact same roles with ground truth we initialize roles set:
roles_set = {"Hospital_Admin","Nurse","Data_Analyst","Auditor","HR_Manager", "Hospital_Clerk"}

def get_graph_schema():
    graph_schema = """
    ### TARGET GRAPH SCHEMA
    
    NODES & ATTRIBUTES:
    - (:Staff {{id: string, name: string, age: int, salary: float, level: int, status: string}})
    - (:ClinicalProtocol {{id: string, name: string, details: string}})
    - (:BillingRecord {{id: string, code: string, status: string, amount: float}})
    - (:MedicalDocument {{id: string, name: string, confidential: boolean, status: string}})
    - (:MedicalEquipment {{id: string, name: string, value: float}})
    - (:Patient {{id:string, name: string, address: string, email: string, phone: string, credit_limit: float}})
    - (:Insurance {{id: string, code: string, status: string, amount: float}})
    - (:Diagnosis {{id:string, type: string, status: string, details: string, cost:float}})
    
    PRESCRIBES
    
    RELATIONSHIPS & ATTRIBUTES:
    - (:Staff) -[:OWNS {{since: int, conditions: string}}]-> (:ClinicalProtocol)
    - (:Staff) -[:COLLABORATES_WITH]-> (:Staff)
    - (:Staff) -[:PRESCRIBES{{dosage: string,prescribtion_date:date}}]-> (:MedicalDocument)
    - (:Patient) -[:HAS_INSURANCE{{approval: boolean}}]-> (:Insurance)
    - (:Staff) -[:TREATS{{since:date}}]-> (:Patient)
    - (:Staff) -[:MAKE{{date:date}}]-> (:Diagnosis)
    - (:ClinicalProtocol) -[:REQUIRES]-> (:MedicalEquipment)
    - (:Staff) -[:USES]-> (:MedicalEquipment)
    - (:Insurance) -[:INCLUDE]-> (:BillingRecord)
    """    
    return graph_schema

"""
def get_graph_schema():
    graph_schema = \"""
    ### TARGET GRAPH SCHEMA
    
    NODES & ATTRIBUTES:
    - (:PatientRecord {id: string, name: string})
    - (:CareUnit {id: string, name: string})
    - (:Insurance {id: string, code: string, status: string, amount: float})
    
    RELATIONSHIPS & ATTRIBUTES:
    - (:PatientRecord) -[:ADMITTED_IN {since: int, conditions: string}]-> (:CareUnit)
    - (:PatientRecord) -[:DIAGNOSED_IN {since: int, conditions: string}]-> (:CareUnit)
    \"""    
    return graph_schema
"""

def extract_acp_entities(text: str) -> dict:
    """
    Calls OpenRouter LLM to analyze text, extract entities, and classify the ACP model.
    """
    
    graph_schema= get_graph_schema()
    
    
    #print(f"subjects size: {len(roles_set)}")
    
    system_prompt = f"""
    You are an expert Access Control Policy (ACP) analyzer mapping natural language to a graph database security model. 
    Analyze the user's text and extract the semantics into a strict JSON format.

    {graph_schema}

    #### SUBJECTS SET:
    {roles_set}

    Your task is to populate this exact JSON schema:
    {{
      "subject": string | null,
      "action": "TRAVERSE" | "CREATE" | "DELETE" | "AddProperty" | "RemoveProperty" | "ModifyProperty" | "Read" | null,
      "resource": string | "*" | null,
      "resource_type": "nodes" | "relationships" | null,
      "attributes": string | null,
      "decision": "grant" | "deny" | null,
      "position": {{
          "source": string | null,
          "target": string | null
      }} | null,
      "conditions": string | null
    }}

    Definitions & Extraction Rules:
    If the text does not describe a clear access control rule, return null
    If the text describes a clear access control rule then extract:
    - subject: The role, user, or entity performing the action. (match it to an existing role in the roles set, if no similar role exists put the new role)
    - action: You MUST map the natural language verb to one of the strict graph actions:
        * TRAVERSE (e.g., access, view, read, traverse a node or relation) -> applied for nodes or relationships only (no attributes)
        * CREATE (e.g., establish, make, build a node or relation) -> applied for nodes or relationships only (no attributes)
        * DELETE (e.g., remove, destroy a node or relation)  -> applied for nodes or relationships only (no attributes)
        * AddProperty (e.g., update, add data to an existing node/relation)  -> applied for attributes of nodes or relationships
        * RemoveProperty (e.g., delete an attribute)   -> applied for attributes of nodes or relationships
        * ModifyProperty (e.g., setting an attribute)  -> applied for attributes of nodes or relationships
        * Read (e.g., view, read, access attribute)   -> applied for attributes of nodes or relationships
    
    - resource: The specific node label or relationship label being acted upon. 
    The resource must be one of the node or relationship types defined in the graph schema. 
    If the policy applies to all nodes or all relationships, use "*" to represent a wildcard matching all resources.

    - resource_type: The type of the resource (nodes or relationships)
    - attributes: The target attribute names of the mentionned resource if specified. (the attributes should be one of the defined graph schema attributes for the mentioned resource)
    If the policy applies to all attributes of a resource, use "*" to represent a wildcard matching all resource's attributes.
    
    - decision: "grant" (allow/can) or "deny" (block/cannot/must not).
    - position: If the resource is a RELATION, and the source and target resources explicitly mentioned in the natural statement, mention them in a JSON object (e.g., "only relations between Hospital Admin and Staff records"). If the resource is just a node, return null.
    - conditions: Any dynamic attribute conditions (e.g., "during business hours", "if they are the owner").
   
    **Ensure that if attribute is not null, then action is either Read,AddProperty,RemoveProperty or ModifyProperty**

    
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
        return {"error": str(e), "original_text": response.text}



def transform_conditions(text: str) -> dict:
    """
    Calls OpenRouter LLM to analyze text, extract entities, and classify the ACP model.
    """
    
    graph_schema= get_graph_schema()
    
    
    
    system_prompt = f"""
        You are an expert access control policy translator specializing in property graph databases. Your task is to translate natural language conditions into formal, machine-enforceable syntax based STRICTLY on the provided data graph schema and roles set.

            <graph_schema>
            {graph_schema}
            </graph_schema>

            <roles_set>
            {roles_set}
            </roles_set>

            ### TRANSLATION RULES
            1. **Strict Adherence:** You must use ONLY the node labels, relationship types, and property keys explicitly defined in the `<graph_schema>` or `<roles_set>`. Do not invent or hallucinate properties.
            2. **Operators:** You are restricted to the following mathematical operators: `=`, `<>`, `>`, `<`, `>=`, `<=`. 
                * Translate logical negations (e.g., "is not", "does not equal", "different) into `<>`.
                * Translate equivalencies (e.g., "is", "matches") into `=`.
                * Translate strict inequalities (e.g., "greater than", "more than", "less than", "fewer than", "under", "over") into `>` or `<`.
                * Translate inclusive inequalities (e.g., "at least", "minimum of", "at most", "maximum of") into `>=` or `<=`.
            3. **Property Targeting:** Ensure the generated syntax correctly compares property keys and values only (e.g., `Patient.status = 'critical'`).
            4. **Strict JSON Output:** You must output ONLY a valid JSON object. Do not include markdown code blocks (e.g., ```json), explanations, or any conversational text.

            ### JSON OUTPUT SCHEMA
            If the translation is successful:
            {{
            "constraints": "<translated_syntax>"
            }}

            If the translation is not possible (e.g., missing schema elements):
            {{
            "error": "<brief explanation of why translation failed>"
            }}

            ### EXAMPLES

            Input: "when the CareUnit is not the nurse's currently assigned department"
            Output: 
            {{
            "constraints": "CareUnit.unitID <> Nurse.careUnit"
            }}

            Input: "the patient's status is listed as critical"
            Output: 
            {{
            "constraints": "Patient.status = 'critical'"
            }}

            Input: "if the doctor has a high reputation score"
            Output: 
            {{
            "error": "Translation failed: 'reputation score' is not defined as a property in the provided graph schema."
            }}
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
        output_json = json.loads(result_content)
        print(f"Transformed conditions for text '{text}': {output_json}")
        log_file = "log_details.log"
        
        # Configure logging to write to the specified file
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(message)s'
        )
        logging.info(f"Transformed conditions for text '{text}': {output_json}")

        return output_json
        
    except Exception as e:
        return {"error": str(e), "original_text": text}


import json
import logging

def syntax_validator(original_text: str, initial_translation: dict) -> dict:
    """
    Acts as a Semantic Validator and Self-Healing LLM. 
    Verifies that generated constraints align with the schema, or attempts 
    to fix translation errors from the initial extraction.
    """
    
    graph_schema = get_graph_schema()
    # Assuming roles_set is retrieved similarly to your first function
    # roles_set = get_roles_set() 
    
    system_prompt = f"""
        You are an expert Graph Database Policy Validator and Self-Healing AI.
        Your task is to review an initial attempt to translate a natural language access control rule into a graph database constraint.

        <graph_schema>
        {graph_schema}
        </graph_schema>

        ### VALIDATION & HEALING RULES
        1. **Schema Verification:** Analyze the `initial_translation`. Every `NodeLabel` and `property` used in the constraint MUST exist exactly as written in the `<graph_schema>`. 
        2. **Error Recovery (Self-Healing):** If the `initial_translation` contains an "error" (e.g., it failed to translate), you must look at the `original_text` and attempt to fix it. 
            * *Common Fix:* Often, initial translations fail because they mistake a string value (like 'private', 'known', or 'critical') for a missing property. Ensure you map descriptive states to string literals (e.g., `Patient.address <> 'private'`).
        3. **Operator Check:** Ensure only allowed operators are used: `=`, `<>`, `>`, `<`, `>=`, `<=`, `IS NULL`, `IS NOT NULL`.
        4. **Strict JSON Output:** You must output ONLY a valid JSON object.

        ### JSON OUTPUT FORMAT
        If the syntax is fully verified or successfully healed:
        {{
            "status": "success",
            "validated_constraints": "<the_verified_or_fixed_syntax>"
        }}

        If the syntax uses properties that DO NOT exist in the schema, or the error truly cannot be fixed:
        {{
            "status": "failed",
            "unresolvable_error": "<brief explanation of why it violates the schema>"
        }}
    """

    user_prompt = f"""
        Original Text: "{original_text}"
        Initial Translation Attempt: {json.dumps(initial_translation)}
        
        Evaluate, verify against the schema, and self-heal if necessary.
    """

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-app-domain.com",
        "X-Title": "ACP Syntax Validator"
    }

    payload = {
        "model": MODEL, # e.g., gpt-oss-120b
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"}, 
        "temperature": 0.0 # Strict deterministic validation
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        result_content = response.json()['choices'][0]['message']['content']
        output_json = json.loads(result_content)
        
        # Logging the validation step
        logging.info(f"Validation Result for '{original_text}': {output_json}")
        print(f"Validation Result for '{original_text}': {output_json}")

        return output_json
        
    except Exception as e:
        error_msg = {"status": "api_error", "unresolvable_error": str(e)}
        logging.error(f"Validator API Error: {error_msg}")
        return error_msg


def rule_generator(decision,action,resource,resource_type,attributes,subject,acm,conditions,position):
    if attributes:
        attributes=f"{{{attributes}}}"
    else :
        attributes=""
    
    rule = f"{decision} {action}{attributes} on {resource_type} (:{resource})"

    if "ABAC" in acm:
        rule += f" where {conditions}"

    if "ReBAC" in acm:
        rule += f" source (:{position['source']}) target (:{position['target']})"

    if "RBAC" in acm:
        rule += f" to {subject}"

    
    return rule






def validate_acp_semantics(original_text: str, extracted_json: dict) -> dict:
    """
    Calls OpenRouter LLM to perform Natural Language Inference (NLI).
    Checks if the extracted JSON accurately reflects the original text without hallucination.
    """
    system_prompt = """
        You are a semantic validator for access control policies.

        Your task is to compare:
        1) A Natural Language policy (written by a human)
        2) A Formal policy (written using a predefined syntax)

        You must determine whether both express the SAME access control intent.

        IMPORTANT RULES:

        - Do NOT require exact word matching.
        - Accept synonyms and equivalent meanings:
        - "view", "access", "read", "traverse" may be equivalent
        - singular/plural differences (Nurse vs Nurses) are NOT errors
        - Focus ONLY on semantic equivalence of Role, Action, Resource, and Conditions.

        - GRAPH SCHEMA EXCEPTION: Formal graph rules often require specifying the 'source' and 'target' node labels for a relationship to be valid (e.g., adding "source (:Staff) target (:ClinicalProtocol)"). If the formal rule adds these structural node bounds to make a relationship graph-compliant, DO NOT consider this a hallucination or an incorrect restriction.

        - A policy is COHERENT if:
        - The formal rule preserves the meaning of the natural language statement
        - There is NO critical information missing
        - There is NO hallucinated constraint (EXCEPT necessary graph source/target labels as noted above)

        - A policy is NOT coherent if:
        - A logical condition is missing or incorrectly added (e.g., missing "since > 2000")
        - A fundamentally different role or action is used

        - is_coherent is a boolean either True or False
        ---

        Return ONLY JSON:
        {
        "is_coherent": True or False,
        "reason": "Explain briefly ONLY if false, otherwise return empty string"
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
        output_json = json.loads(result_content)
        return output_json
    except Exception as e:
        return {"is_coherent": False, "reason": f"Validation API error: {str(e)}"}


import json
import logging

def heal_acp_semantics(original_text: str, rejected_json: dict, validation_feedback: str) -> dict:
    """
    Acts as a Self-Healing LLM. Takes a rejected formal policy and the validator's 
    critique, cross-references them against the target schema, and generates a corrected, 
    schema-compliant formal rule.
    """
    
    # Retrieve the schema to ground the self-healing process
    graph_schema = get_graph_schema()
    
    system_prompt = f"""
        You are a highly logical Self-Healing AI for Graph Database Access Control Policies.
        
        A previous extraction attempt was rejected by a semantic validator. Your task is to review the validator's feedback, fix the formal rule if the validator is correct, OR override the validator if it is demanding elements that do not exist in the schema.

        <graph_schema>
        {graph_schema}
        </graph_schema>

        ### HEALING INSTRUCTIONS & RULES:
        1. **Schema is Absolute Law:** The validator may complain that a specific word from the natural language is missing (e.g., "Patient Accounts"). If that specific word is NOT a valid Node or Relationship in the `<graph_schema>`, you must map it to the closest valid schema element (e.g., `Patient` or `BillingRecord`). Do not hallucinate new nodes to satisfy the validator.
        2. **Fix Structural Errors:** If the validator correctly identified missing properties, missing logical constraints (e.g., a missing date limitation), or incorrect roles, update the formal rule to include them.
        3. **Format Integrity:** Ensure the final output is perfectly structured to match the expected formal graph access control syntax. 
        4. **Strict JSON Output:** You must return ONLY a valid JSON object containing the corrected formal rule.

        ### JSON OUTPUT FORMAT
        {{
            "status": "healed",
            "healed_rule": <the_complete_corrected_json_rule_object>,
            "healing_rationale": "<Brief explanation of what you changed, or why you ignored the validator's pedantic critique>"
        }}
    """

    user_prompt = f"""
        Original Text (Intent): "{original_text}"
        Rejected Formal Rule: {json.dumps(rejected_json)}
        Validator's Critique: "{validation_feedback}"
        
        Generate the healed formal rule.
    """

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-app-domain.com",
        "X-Title": "ACP Self-Healer Pipeline"
    }

    payload = {
        "model": MODEL, 
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"}, 
        "temperature": 0.0 # Must be deterministic
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        result_content = response.json()['choices'][0]['message']['content']
        output_json = json.loads(result_content)
        
        logging.info(f"Self-Healed Rule for '{original_text}': {output_json}")
        return output_json
        
    except Exception as e:
        error_msg = {"status": "healing_failed", "error": str(e)}
        logging.error(f"Healer API Error: {error_msg}")
        return error_msg


def process_csv(file_path: str):
    """
    Loops through the CSV and processes each rule, including semantic validation.
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return


    i=0
    valid_generated_rules = []
    
    limit = float('inf') if config.LIMIT == 'all' else int(config.LIMIT)
    
    with open(file_path, mode='r', encoding='utf-8') as file:
        
        
        reader = csv.DictReader(file)
        
        for row in reader:
            rule_id = row.get("rule_id", "").strip()
            rule_text = row.get("rule_text", "").strip()
            i+=1
            if not rule_text:
                continue
            
            # 1. Extract the Data
            extracted_data = extract_acp_entities(rule_text)
            
            if isinstance(extracted_data, dict):
                extracted_data["rule_id"] = rule_id
                detected_role = extracted_data.get("subject", None)
                detected_action = extracted_data.get("action", None)
                detected_resource = extracted_data.get("resource", None)
                detected_resource_type = extracted_data.get("resource_type", None)
                detected_decision = extracted_data.get("decision", None)
                detected_attributes = extracted_data.get("attributes", None)
                detected_conditions = extracted_data.get("conditions", None)
                detected_position = extracted_data.get("position", None)

                if detected_position and isinstance(detected_position, dict):
                    source_node= detected_position.get("source")
                    target_node= detected_position.get("target")
                # ADD ROLE IF NOT FOUND (or similar not found)
                if detected_role and detected_role not in roles_set:
                    print(f"New role detected: {detected_role}")
                    roles_set.add(detected_role)
                    
                if not detected_role or not detected_action or not detected_resource:
                    print(f"Warning: Incomplete extraction for rule_id {rule_id}. Extracted data: {extracted_data}")
                    continue  # Skip further processing for this row (if 3 times)
                
                elif detected_action and detected_action not in ["TRAVERSE", "CREATE", "DELETE", "AddProperty", "RemoveProperty","ModifyProperty", "Read"]:
                    print(f"Warning: Detected action '{detected_action}' is not in the predefined set.")
                    continue


                #classify the rule if rbac,abac or rebac
                acm=["RBAC"] #default is rbac, if no condition or position is detected
                if detected_conditions:
                    acm.append("ABAC")
                    detected_conditions=transform_conditions(detected_conditions)
                    # 2. Validation & Self-Healing
                    if config.VALIDATION:
                        final_result = syntax_validator(original_text=rule_text, initial_translation=detected_conditions)

                        # 3. Pipeline Routing
                        if final_result.get("status") == "success":
                            detected_conditions = final_result["validated_constraints"]
                        else:
                            if 'unresolvabe_error' in final_result:
                                print(f"Warning: Condition translation failed for rule_id {rule_id}. Error: {final_result['unresolvable_error']}")
                            else :
                                print(f"Warning: Condition translation failed for rule_id {rule_id}. Error: {json.dumps(final_result)}")
                            continue  # Skip further processing for this row
                    else:
                        if "constraints" in detected_conditions:
                            detected_conditions = detected_conditions["constraints"]
                        elif "error" in detected_conditions:
                            print(f"Warning: Condition translation failed for rule_id {rule_id}. Error: {detected_conditions['error']}")
                            continue  # Skip further processing for this row
                        

                      
                if detected_position:
                    acm.append("ReBAC")
                    
                    
                # 2. Output the extracted result
                #print(json.dumps(extracted_data, separators=(',', ':')))
                rule=rule_generator(detected_decision,detected_action,detected_resource,detected_resource_type,detected_attributes,detected_role,acm,detected_conditions,detected_position)
                print(f"Generated rule: {rule}")
                
                # 2. Validate Semantics (Only if it was identified as a policy)
                validation_result = validate_acp_semantics(rule_text, extracted_data)
                if config.VALIDATION:
                    # 2. Check and Heal
                    if not validation_result.get("is_coherent", False):
                        reason = validation_result.get("reason", "Unknown semantic drift")
                        
                        # Trigger the Self-Healing module
                        healed_result = heal_acp_semantics(rule_text, validation_result, reason)
                        
                        if healed_result.get("status") == "healed":
                            # Overwrite the broken extraction with the newly healed rule
                            validation_result = healed_result.get("healed_rule")
                    
                print(f"Validation result for rule_id {rule_id}: {validation_result}")
                log_file = "log_details.log"
        
                # Configure logging to write to the specified file
                logging.basicConfig(
                    filename=log_file,
                    level=logging.INFO,
                    format='%(message)s'
                )
                logging.info(f"Generated rule: {rule}\nValidation result for rule_id {rule_id}: {validation_result}")
                
                
                if validation_result.get('is_coherent', False):
                    valid_generated_rules.append({
                        'rule_id': rule_id,
                        'rule': rule
                    })
                # Create a copy without the rule_id for cleaner validation context
                    #clean_extracted = {k: v for k, v in extracted_data.items() if k != 'rule_id'}
                    #validation_result = validate_acp_semantics(rule_text, clean_extracted)
                    
                    # Append validation results to the final payload
                    #extracted_data["validation"] = validation_result
                

            print("\n---\n") 
            log_file = "log_details.log"
        
            # Configure logging to write to the specified file
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format='%(message)s'
            )
            logging.info(f"\n---\n")
            
                # If you want to process the whole file, remove the 'break'
            if i >= limit:      
                break
            
    return valid_generated_rules








if __name__ == "__main__":
    # Adjust path if needed
    
    if config.POLICY_TYPE=="all":
        input_file="1_natural_policy.csv"  
        ground_truth="1_formal_policy.csv"
    elif config.POLICY_TYPE=="rbac":
        input_file="2_natural_rbac.csv"  
        ground_truth="2_formal_rbac.csv"
    elif config.POLICY_TYPE=="abac":
        input_file="3_natural_abac.csv"
        ground_truth="3_formal_abac.csv"   
    elif config.POLICY_TYPE=="rebac":
        input_file="4_natural_rebac.csv" 
        ground_truth="4_formal_rebac.csv"      
    else:
        input_file="5_natural_hybrid.csv"
        ground_truth="5_formal_hybrid.csv"
        
    
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", input_file)
    valid_generated_rules = process_csv(csv_path)
    
    
    # 1. Construct the dynamic path to your ground truth CSV
    current_dir = os.path.dirname(__file__)
    csv_path = os.path.join(current_dir, "..", "data", ground_truth)

    # Optional: use abspath to clean up the ".." and get the absolute path
    csv_path = os.path.abspath(csv_path)
    evaluator = RuleEvaluator(ground_truth_csv=csv_path, log_file="logfile.log")
    metrics = evaluator.evaluate(valid_generated_rules)