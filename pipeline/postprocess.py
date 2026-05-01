from typing import Dict, Any, List
import json
import re
from datetime import datetime


def dedup_extractions(
    extractions: List[Dict[str, Any]],
    key_field: str = "task"
) -> List[Dict[str, Any]]:
    """
    Remove duplicate extractions.
    
    Args:
        extractions: List of extracted items
        key_field: Field to use for dedup
    
    Returns:
        Deduplicated list
    """
    seen = set()
    unique = []
    
    for item in extractions:
        key_value = item.get(key_field, "")
        if key_value not in seen:
            seen.add(key_value)
            unique.append(item)
    
    return unique


def normalize_priority(priority: str) -> str:
    """Normalize priority to lowercase enum"""
    if not priority:
        return "medium"
    
    priority_lower = priority.lower().strip()
    
    if priority_lower in ["low", "medium", "high"]:
        return priority_lower
    
    if "urgent" in priority_lower or "critical" in priority_lower:
        return "high"
    elif "normal" in priority_lower or "regular" in priority_lower:
        return "medium"
    
    return "medium"


def normalize_date(date_str: str) -> str:
    """
    Normalize date to ISO format if possible.
    
    Args:
        date_str: Date string
    
    Returns:
        ISO formatted date or original string
    """
    if not date_str:
        return None
    
    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y"
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return date_str


def attach_source_references(
    extractions: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Ensure all extractions have source chunk references.
    
    Args:
        extractions: Extracted items
        chunks: Source chunks
    
    Returns:
        Extractions with source references
    """
    if not chunks:
        return extractions
    
    default_source = f"{chunks[0]['doc_id']}_chunk_{chunks[0]['chunk_id']}"
    
    for extraction in extractions:
        if "source" not in extraction or not extraction["source"]:
            extraction["source"] = default_source
    
    return extractions


def validate_against_schema(
    data: Dict[str, Any],
    schema_type: str
) -> bool:
    """
    Validate output against expected schema structure.
    Very lenient - accepts any reasonable format.
    
    Args:
        data: Output data (can be full response or just data field)
        schema_type: Schema type to validate against
    
    Returns:
        True if valid
    """
    # Handle list directly (LLM sometimes returns list of items)
    if isinstance(data, list):
        if schema_type == "entities_v1":
            # Entities should be object with entities array, not a list
            return False
        # Accept list for backward compatibility with tasks
        return True
    
    # Extract data field if full response is provided
    if "data" in data and isinstance(data["data"], dict):
        data = data["data"]
    
    if schema_type == "tasks_v1":
        # Accept tasks, action_items, actionItems, issues, etc.
        has_tasks = any(key in data for key in ["tasks", "action_items", "actionItems", "issues"])
        has_summary = any(key in data for key in ["summary", "documentSummaries", "documents"])
        return has_tasks and has_summary
        
    elif schema_type == "summary_v1":
        # Accept various summary formats
        has_summary = any(key in data for key in ["summary", "summaries", "documentSummaries", "documents"])
        has_points = any(key in data for key in ["key_points", "keyPoints", "points", "action_items", "actionItems"])
        return has_summary or has_points
        
    elif schema_type == "entities_v1":
        # Accept entities array wrapped in {"entities": [...]}
        has_entities = "entities" in data and isinstance(data.get("entities"), list)
        if has_entities:
            return True
        # Also accept list directly (LLM returned list of entities) - will be normalized
        if isinstance(data, list):
            return True
        return False
    
    # Default: accept any dict
    return isinstance(data, dict)


def normalize_entities(
    entities: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Normalize entity format - map various fields to standard schema.
    
    Accepts:
    - entities: [{"name": "...", "type": "...", "source": "..."}]
    - entities: [{"entity": "...", "type": "...", "source": "..."}]
    
    Only keeps: name, type, source (and maps entity → name)
    """
    normalized = []
    
    for entity in entities:
        normalized_entity = {}
        
        # Map name field (entity, name, entity_name, person, etc.)
        if "name" in entity:
            normalized_entity["name"] = entity["name"]
        elif "entity" in entity:
            normalized_entity["name"] = entity["entity"]
        else:
            continue  # Skip if no name
        
        # Map type field (only keep valid types)
        if "type" in entity:
            entity_type = entity["type"]
            valid_types = ["person", "organization", "date", "location", "other"]
            if entity_type in valid_types:
                normalized_entity["type"] = entity_type
            else:
                normalized_entity["type"] = "other"
        else:
            normalized_entity["type"] = "other"
        
        # Map source field
        if "source" in entity:
            normalized_entity["source"] = entity["source"]
        
        normalized.append(normalized_entity)
    
    return normalized


def postprocess_extraction(
    extraction: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    schema_type: str
) -> Dict[str, Any]:
    """
    Apply all post-processing to extraction.
    
    Args:
        extraction: Raw extraction from LLM
        chunks: Source chunks
        schema_type: Schema type
    
    Returns:
        Post-processed extraction
    """
    if schema_type == "tasks_v1":
        if "tasks" in extraction:
            for task_item in extraction["tasks"]:
                if "priority" in task_item:
                    task_item["priority"] = normalize_priority(task_item["priority"])
                if "deadline" in task_item and task_item["deadline"]:
                    task_item["deadline"] = normalize_date(task_item["deadline"])
            
            extraction["tasks"] = dedup_extractions(extraction["tasks"])
            extraction["tasks"] = attach_source_references(extraction["tasks"], chunks)
    
    elif schema_type == "entities_v1":
        # Handle both {"entities": [...]} and raw list formats
        if "entities" in extraction:
            extraction["entities"] = normalize_entities(extraction["entities"])
            extraction["entities"] = dedup_extractions(extraction["entities"], key_field="name")
            extraction["entities"] = attach_source_references(extraction["entities"], chunks)
        elif isinstance(extraction, list):
            # LLM returned raw list of entities - wrap in entities structure
            extracted_entities = normalize_entities(extraction)
            extracted_entities = dedup_extractions(extracted_entities, key_field="name")
            extraction = {"entities": extracted_entities}
    
    return extraction


def build_response(
    extraction: Dict[str, Any],
    chunks_used: int,
    tokens_used: int,
    docs_processed: int,
    schema_type: str,
    tokens_before: int = None,
    tokens_after: int = None,
    reduction_pct: float = None,
    doc_classifications: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Build final API response with meta information.
    
    Args:
        extraction: Processed extraction
        chunks_used: Number of chunks used
        tokens_used: Token count
        docs_processed: Number of documents processed
        schema_type: Schema type
        tokens_before: Tokens before filtering (optional)
        tokens_after: Tokens after filtering (optional)
        reduction_pct: Reduction percentage (optional)
    
    Returns:
        Complete API response
    """
    if schema_type == "tasks_v1":
        data = {
            "tasks": extraction.get("tasks", []),
            "summary": extraction.get("summary", "")
        }
    elif schema_type == "summary_v1":
        data = {
            "summary": extraction.get("summary", ""),
            "key_points": extraction.get("key_points", [])
        }
    elif schema_type == "entities_v1":
        data = {
            "entities": extraction.get("entities", [])
        }
    else:
        data = extraction
    
    meta = {
        "chunks_used": chunks_used,
        "tokens_used": tokens_used,
        "docs_processed": docs_processed
    }
    
    if tokens_before is not None:
        meta["tokens_before_filter"] = tokens_before
    if tokens_after is not None:
        meta["tokens_after_filter"] = tokens_after
    if reduction_pct is not None:
        meta["reduction_pct"] = reduction_pct
    if doc_classifications is not None:
        meta["doc_classifications"] = doc_classifications
    
    return {
        "status": "success",
        "data": data,
        "meta": meta
    }
