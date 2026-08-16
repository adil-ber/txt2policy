# txt2policy

A Python pipeline that converts Natural Language Access Control Policies into Formal Access Control Rules for property graph databases. It utilizes LLMs (via OpenRouter) to extract entities, translate conditions, and semantically validate and self-heal the generated rules.

## Features
- **Extraction**: Maps NLP subjects, actions, and resources to a specific graph schema.
- **Validation**: Evaluates generated policies and compares them to the source text.
- **Self-Healing**: Fixes broken extractions based on the validation step.
- **Evaluation**: Computes Precision, Recall, and F1-Score against ground truth datasets.
- **Models**: Supports all graph policy types (RBAC, ABAC, ReBAC, Hybrid).

## Setup

1. Install dependencies (if any are missing, generally `requests`):
```bash
pip install requests
```

2. Configure the application:
Copy the template configuration file to `config.json`:
```bash
cp config.template.json config.json
```
Then, edit `config.json` and add your OpenRouter API Key. You can also customize the defaults (like model, limit, and acm) in this file.

Alternatively, you can provide your API key via an environment variable:
```bash
export OPENROUTER_API_KEY="your_api_key_here"
```

## Usage

You can run the pipeline with no arguments to use the defaults defined in `config.json`:
```bash
python src/main.py
```

### CLI Arguments (Overrides config.json)
- `--acm`: The Access Control Model type (`all`, `rbac`, `abac`, `rebac`, `hybrid`).
- `--limit`: Number of rules to evaluate (integer or `all`).
- `--validation`: Include this flag to enable semantic validation and self-healing.
- `--model`: The LLM to use.
- `--api-key`: Your OpenRouter API key.
- `--api-url`: The API endpoint to use.

Example with specific overrides:
```bash
python src/main.py --acm hybrid --limit all --validation --model "anthropic/claude-3-haiku"
```
