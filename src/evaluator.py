import csv
import logging
from datetime import datetime
import re

class RuleEvaluator:
    def __init__(self, ground_truth_csv, log_file="evaluation_results.log"):
        self.ground_truth_csv = ground_truth_csv
        self.log_file = log_file
        
        # Configure logging to write to the specified file
        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format='%(message)s'
        )

    def load_ground_truth(self):
        """Loads the ground truth CSV into a dictionary mapped by rule_id."""
        ground_truth = {}
        try:
            with open(self.ground_truth_csv, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # Use the exact key as it appears in the CSV header
                    rule_id = str(row['rule_id']).strip()
                    
                    # Use 'rule_text;' and use .rstrip(';') to remove the trailing semicolon from the value
                    ground_truth[rule_id] = str(row['rule_text;']).strip().rstrip(';')
                    
        except FileNotFoundError:
            print(f"Error: Ground truth file '{self.ground_truth_csv}' not found.")
        return ground_truth


    def _normalize_rule(self, rule):
        """
        Normalizes a graph access control rule string by removing superficial 
        syntactic differences (case, semicolons, spacing, node variables, wildcards, 
        and property variable prefixes).
        """
        # 1. Convert to lowercase and remove leading/trailing spaces and semicolons
        rule = rule.lower().strip().rstrip(';')
        
        # 2. Remove node/relationship variables. 
        # Converts "(e:Staff)" or "(node:Staff)" into "(:Staff)"
        rule = re.sub(r'\(\s*[a-z0-9_]+\s*:', '(:', rule)
        
        # 3. Standardize whitespace (replace multiple spaces with a single space)
        rule = re.sub(r'\s+', ' ', rule)
        
        # 4. Remove spaces around colons and parentheses to ensure strict matching
        rule = rule.replace('(: ', '(:').replace(' )', ')')
        
        # 5. Normalize wildcards (NEW FIX)
        # Converts "(:*)" into "(*)" so they match perfectly
        rule = rule.replace('(:*)', '(*)')
        
        # 6. Normalize property variable prefixes (NEW FIX FOR VARIABLE DRIFT)
        # Converts "medicalequipment.value" or "a.value" into "_.value"
        # Looks for word characters/numbers/underscores followed by a dot, 
        # ensuring it's a variable reference.
        rule = re.sub(r'\b[a-z0-9_]+\.(?=[a-z0-9_]+)', '_.', rule)
        
        return rule

    def _rules_match(self, generated, expected):
        """
            Determines if the generated rule matches the expected rule after normalization.
        """
        norm_gen = self._normalize_rule(generated)
        norm_exp = self._normalize_rule(expected)
            
            # Optional: Print to debug what the normalized strings look like
        print(f"Comparing:\n Gen: {norm_gen}\n Exp: {norm_exp}")
        
        return norm_gen == norm_exp
    
    
    def evaluate(self, generated_rules_list, limit='all'):
        """
        Evaluates the generated rules against the ground truth.
        generated_rules_list: List of dicts [{'rule_id': '1', 'rule': '...'}, ...]
        limit: Max number of rules to evaluate ('all' or integer)
        """
        ground_truth = self.load_ground_truth()
        if not ground_truth:
            return

        tp = 0  # True Positives: Generated rule matches ground truth
        fp = 0  # False Positives: Generated rule does NOT match ground truth
        fn = 0  # False Negatives: Rule exists in ground truth but was not generated/coherent

        # Convert generated rules list to a dictionary for easy lookup
        generated_dict = {str(item['rule_id']): item['rule'] for item in generated_rules_list}

        # Calculate TP, FP, FN
        max_limit = float('inf') if str(limit).lower() == 'all' else int(limit)
        i=0
        for rule_id, expected_rule in ground_truth.items():
            if(i>= max_limit):
                break
            i += 1
            
            if rule_id in generated_dict:
                generated_rule = generated_dict[rule_id]
                if self._rules_match(generated_rule, expected_rule):
                    tp += 1
                else:
                    fp += 1
            else:
                # The rule was likely dropped because validate_acp_semantics returned False
                fn += 1

        # Calculate Metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Format the output string
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (f"[{timestamp}] Total Evaluated: {limit} | "
                     f"TP: {tp}, FP: {fp}, FN: {fn} | "
                     f"Precision: {precision:.4f} | Recall: {recall:.4f} | F1-Score: {f1_score:.4f}")

        # Print to console and write to log file
        print(f"\n--- Evaluation Complete ---")
        print(log_entry)
        logging.info(log_entry)
        
        return {"precision": precision, "recall": recall, "f1": f1_score}