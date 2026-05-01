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

# Model configuration - schema-based model selection
_MODEL_TASKS = os.getenv("MODEL_TASKS", "ministral-3:3b")
_MODEL_SUMMARY = os.getenv("MODEL_SUMMARY", "minimax-m2.5")
_MODEL_ENTITIES = os.getenv("MODEL_ENTITIES", "qwen3.5")

# Global httpx client for connection pooling
_httpx_client = None


def get_model(schema_type: str) -> str:
    """Get model for schema type"""
    if schema_type == "tasks_v1":
        return _MODEL_TASKS
    elif schema_type == "summary_v1":
        return _MODEL_SUMMARY
    elif schema_type == "entities_v1":
        return _MODEL_ENTITIES
    else:
        return _MODEL_TASKS


def get_httpx_client() -> httpx.AsyncClient:
    """Get or create shared httpx client with connection pooling"""
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
    return _httpx_client


def get_llm_api_key() -> Optional[str]:
    """Get LLM API key from environment"""
    return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")


def get_ollama_base_url() -> str:
    """Get Ollama base URL from environment"""
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def trim_chunk_text(text: str, max_words: int = 100) -> str:
    """Trim chunk text for prompt (reduces token count by 30-40%)"""
    words = text.split()
    if len(words) <= max_words:
        return text
    keep_start = int(max_words * 0.7)
    keep_end = int(max_words * 0.3)
    return ' '.join(words[:keep_start]) + ' ... ' + ' '.join(words[-keep_end:])


def build_extract_prompt(
    chunks: List[Dict[str, Any]],
    task: str,
    schema_type: str,
    trim_chunks: bool = True
) -> str:
    """Build extraction prompt with optional chunk trimming for token reduction."""
    if trim_chunks:
        chunk_texts = "\n\n---\n\n".join([
            f"[Source: {chunk['doc_id']}_chunk_{chunk['chunk_id']}]\n{trim_chunk_text(chunk['text'], 100)}"
            for chunk in chunks
        ])
    else:
        chunk_texts = "\n\n---\n\n".join([
            f"[Source: {chunk['doc_id']}_chunk_{chunk['chunk_id']}]\n{chunk['text']}"
            for chunk in chunks
        ])
    
    schema_examples = {
        "tasks_v1": '{"tasks": [{"task": "Complete report", "priority": "high", "deadline": "May 5", "source": "doc1"}], "summary": "Summary"}',
        "summary_v1": '{"summary": "Brief summary", "key_points": ["Point 1"]}',
        "entities_v1": '{"entities": [{"name": "John Smith", "type": "person", "source": "doc1_chunk_2"}, {"name": "Acme Corp", "type": "organization", "source": "doc1_chunk_5"}]}'
    }
    
    example_output = schema_examples.get(schema_type, '{}')
    
    prompt = (
        "You are a JSON extractor. Return ONLY valid JSON matching schema.\n"
        "CRITICAL: No wrapper, NO markdown, NO extra fields.\n"
        f"TASK: {task}\n\n"
        "CHUNKS:\n"
        f"{chunk_texts}\n\n"
        "OUTPUT:\n"
        f"{example_output}\n\n"
        "IMPORTANT: For entities_v1, return entities with name/type/source, NOT tasks."
    )
    
    if schema_type == "entities_v1":
        prompt += (
            "\n\nSTRICT RULES FOR ENTITIES:\n"
            "- Return ONLY valid JSON with entities array: {\"entities\": [{\"name\": \"...\", \"type\": \"person|organization|date|location|other\", \"source\": \"...\"}]}\n"
            "- DO NOT return: task, task_id, description, priority, deadline, owner, notes, status, entity (use name), or raw list\n"
            "- DO NOT return tasks, issues, action items, tickets, or bugs\n"
            "- ONLY extract named entities like people, companies, dates, places\n"
            "- Valid types: person, organization, date, location, other"
        )
    
    return prompt


async def call_llm(
    prompt: str,
    schema_type: str,
    api_key: Optional[str] = None,
    model: str = None
) -> str:
    """Call LLM API for extraction with auto model selection."""
    if model is None:
        model = get_model(schema_type)
    
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
    model: str = "ministral-3:3b"
) -> str:
    """Call Ollama API (OpenAI-compatible endpoint)"""
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2000}
    }
    
    client = get_httpx_client()
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
    
    client = OllamaClient(host="https://ollama.com", headers={'Authorization': f'Bearer {api_key}'})
    
    messages = [
        {'role': 'system', 'content': 'You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown.'},
        {'role': 'user', 'content': prompt}
    ]
    
    response = client.chat(model=model, messages=messages, stream=False)
    return response['message']['content']


async def call_openai(
    prompt: str,
    api_key: str,
    model: str = "gpt-4o-mini"
) -> str:
    """Call OpenAI API"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON extractor. Return ONLY valid JSON. No prose, no markdown."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 2000
    }
    
    client = get_httpx_client()
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
        "messages": [{"role": "user", "content": prompt}]
    }
    
    client = get_httpx_client()
    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]


def parse_llm_response(response: str) -> Dict[str, Any]:
    """Parse LLM response, stripping markdown if present."""
    cleaned = response.strip()
    
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    cleaned = cleaned.strip()
    
    return json.loads(cleaned)


def cleanup_httpx_client():
    """Close the shared httpx client on shutdown"""
    global _httpx_client
    if _httpx_client is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_httpx_client.aclose())
            else:
                asyncio.run(_httpx_client.aclose())
        except Exception:
            pass
        _httpx_client = None
