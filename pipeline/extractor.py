import os
import json
import httpx
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

try:
    from ollama import Client as OllamaClient
    OLLAMA_CLIENT_AVAILABLE = True
except ImportError:
    OLLAMA_CLIENT_AVAILABLE = False

load_dotenv()


def get_llm_api_key() -> Optional[str]:
    """Get LLM API key from environment"""
    return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")


def get_ollama_base_url() -> str:
    """Get Ollama base URL from environment"""
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def build_extract_prompt(
    chunks: List[Dict[str, Any]],
    task: str,
    schema_type: str
) -> str:
    """
    Build the extraction prompt with chunks and schema.
    
    Args:
        chunks: Top-ranked chunks
        task: Task description
        schema_type: Target schema type
    
    Returns:
        Formatted prompt for LLM
    """
    chunk_texts = "\n\n---\n\n".join([
        f"[Source: {chunk['doc_id']}_chunk_{chunk['chunk_id']}]\n{chunk['text']}"
        for chunk in chunks
    ])
    
    schema_examples = {
        "tasks_v1": '''{
  "tasks": [
    {
      "task": "Complete the report",
      "priority": "high",
      "deadline": "2026-05-01",
      "source": "doc_0_chunk_0"
    }
  ],
  "summary": "Brief summary of extracted tasks"
}''',
        "summary_v1": '''{
  "summary": "Brief summary",
  "key_points": ["Point 1", "Point 2"]
}''',
        "entities_v1": '''{
  "entities": [
    {
      "name": "John Smith",
      "type": "person",
      "source": "doc_0_chunk_0"
    }
  ]
}'''
    }
    
    example_output = schema_examples.get(schema_type, '{}')

    # FIX-3 & FIX-4: Enhanced prompt with implicit task detection and better priority calibration
    prompt = f"""You are a JSON extractor. Return ONLY valid JSON matching the EXACT schema below.

CRITICAL RULES:
1. Return ONLY the data object - NO wrapper, NO "status", NO "meta"
2. NO markdown, NO code blocks, NO explanations
3. Do NOT wrap in ```json or ``` - just raw JSON
4. Use EXACT field names from schema: "tasks", "summary" (for tasks_v1)
5. Include source for each item (e.g., "doc_0_chunk_0")
6. Do NOT invent new field names - use the schema exactly

FIX-3: OWNER EXTRACTION (MANDATORY):
When extracting tasks, always identify the owner if one is stated or clearly implied in the source text.
Prefix the task description with the owner's first name followed by a colon, e.g.:
  - "Marcus: send calendar invite for QA sync"
  - "Dev: ping Rachel in Slack"
  - "Unassigned: update documentation"

If no owner is identifiable from the chunk, prefix with "Unassigned:".
Never omit the owner prefix. Unassigned is a valid and expected value.

IMPLICIT TASK DETECTION (CRITICAL):
Extract tasks even when they are NOT written as direct commands. Look for these patterns:

1. **Conditional tasks** - "if X happens, Y should do Z"
   Example: "If the API latency exceeds 500ms, Vikram needs to investigate"
   → Extract: "Vikram: investigate if API latency exceeds 500ms"

2. **Decision-based tasks** - "we decided to X" or "X will do Y"
   Example: "We decided that Sandra will draft the API changelog"
   → Extract: "Sandra: draft the API changelog"

3. **Dependency tasks** - "waiting on X" or "blocked until Y"
   Example: "The mobile fix is blocked until Rachel completes the audit"
   → Extract: "Rachel: complete the audit"

4. **Side-effect tasks** - mentioned as consequences of other actions
   Example: "After the deployment, James should verify the metrics"
   → Extract: "James: verify the metrics after deployment"

5. **Question-based tasks** - "Can X do Y?" or "Who will handle Z?"
   Example: "Can Marcus send the calendar invite?"
   → Extract: "Marcus: send calendar invite"

Do NOT limit extraction to imperative sentences. Extract ANY action that needs to be taken, regardless of how it's phrased.

FIX-4: PRIORITY CLASSIFICATION RUBRIC (NON-NEGOTIABLE):
Follow these rules exactly. Pay special attention to blocking dependencies.

**HIGH priority** — task meets ONE or MORE of these conditions:
  - Explicitly marked as "urgent", "critical", "ASAP", "blocker", or "blocking" in source text
  - Has a deadline within 72 hours of the document date
  - **BLOCKING DEPENDENCY**: Another task cannot start until this one is done
    - Look for: "blocked on", "waiting for", "depends on", "until X is done"
    - Example: "Mobile fix blocked until Rachel completes audit" → Rachel's audit is HIGH
  - Is tied to a company OKR, executive decision, or leadership waiting on it
  - Involves a vendor, contract, or external dependency with a hard deadline
  - Related to production incidents, outages, security issues, or compliance

**MEDIUM priority** — task meets THESE conditions (and NONE of the HIGH conditions):
  - Has a specific named deadline more than 72 hours away
  - Does not block other tasks (nothing is waiting on this)
  - Is internally owned with no external dependency
  - Part of current sprint but not marked urgent
  - **CONDITIONAL TASKS**: Tasks that depend on a condition being met
    - Example: "If latency is high, investigate" → MEDIUM (condition may not trigger)

**LOW priority** — task meets THESE conditions:
  - No explicit deadline stated in source text
  - Is a coordination, notification, or reminder action (e.g., "ping", "check with", "send link", "confirm")
  - Does not block any other task
  - Documentation updates without urgency
  - "Nice to have" or "when time permits"
  - Follow-up actions with no hard deadline

FIX-4: DEADLINE EXTRACTION RULES:
- Only extract a deadline if one is EXPLICITLY stated in the source text
- If no deadline is mentioned, set deadline to null
- NEVER infer, estimate, or hallucinate a deadline
- Common explicit formats: "by April 30", "due May 2", "deadline: 2026-05-01", "before Friday"
- Conditional deadlines are NOT deadlines: "if needed by Friday" → null

TASK: {task}

DOCUMENT CHUNKS:
{chunk_texts}

EXACT OUTPUT SCHEMA (MUST MATCH THIS):
{example_output}

Return ONLY the JSON object above with your extracted data. Apply implicit task detection and priority rubric strictly. Start with {{ and end with }}."""

    return prompt


async def call_llm(
    prompt: str,
    schema_type: str,
    api_key: Optional[str] = None,
    model: str = None
) -> str:
    # Auto-select model based on schema type
    if model is None:
        model = "ministral-3:3b"
    """
    Call LLM API for extraction.
    
    Args:
        prompt: Extraction prompt
        schema_type: Target schema
        api_key: API key (uses env if not provided)
        model: Model to use
    
    Returns:
        Raw LLM response text
    """
    ollama_url = os.getenv("OLLAMA_BASE_URL")
    
    if ollama_url and ("localhost" in ollama_url or "127.0.0.1" in ollama_url):
        return await call_ollama(prompt, ollama_url, model)
    
    if ollama_url and "cloud" in ollama_url.lower():
        if not api_key:
            api_key = get_llm_api_key()
        if not api_key:
            raise ValueError("No API key found. Set LLM_API_KEY for Ollama Cloud")
        return call_ollama_cloud(prompt, api_key, model)
    
    if not api_key:
        api_key = get_llm_api_key()
    
    if not api_key:
        raise ValueError("No API key found. Set LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY")
    
    if "anthropic" in api_key.lower() or os.getenv("USE_ANTHROPIC"):
        return await call_anthropic(prompt, api_key, model)
    else:
        return await call_openai(prompt, api_key, model)


async def call_ollama(
    prompt: str,
    base_url: str,
    model: str = "gemma3:31b"
) -> str:
    """Call Ollama API (OpenAI-compatible endpoint)"""
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 2000
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def call_ollama_cloud(
    prompt: str,
    api_key: str,
    model: str = "ministral-3:3b"
) -> str:
    """Call Ollama Cloud API using official ollama client"""
    if not OLLAMA_CLIENT_AVAILABLE:
        raise ImportError("ollama client not installed. Run: pip install ollama")
    
    client = OllamaClient(
        host="https://ollama.com",
        headers={'Authorization': f'Bearer {api_key}'}
    )
    
    messages = [
        {
            'role': 'system',
            'content': 'You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown.'
        },
        {
            'role': 'user',
            'content': prompt
        }
    ]
    
    response = client.chat(
        model=model,
        messages=messages,
        stream=False
    )
    
    return response['message']['content']


async def call_openai(
    prompt: str,
    api_key: str,
    model: str = "gpt-4o-mini"
) -> str:
    """Call OpenAI API"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 2000
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def call_anthropic(
    prompt: str,
    api_key: str,
    model: str = "claude-3-haiku-20240307"
) -> str:
    """Call Anthropic API"""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    
    payload = {
        "model": model,
        "max_tokens": 2000,
        "system": "You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown.",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


def parse_llm_response(response: str) -> Dict[str, Any]:
    """
    Parse LLM response, stripping markdown if present.
    
    Args:
        response: Raw LLM response
    
    Returns:
        Parsed JSON dict
    """
    cleaned = response.strip()
    
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    cleaned = cleaned.strip()
    
    return json.loads(cleaned)
