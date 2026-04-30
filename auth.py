import os
import time
from typing import Dict, Any
from functools import wraps
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

API_KEYS = {}

RATE_LIMITS = {
    "default": {"requests_per_minute": 60, "requests_per_day": 1000}
}

usage_data: Dict[str, Dict[str, Any]] = {}


def get_api_key_header():
    return os.getenv("API_KEY_HEADER", "X-API-Key")


def get_required_api_key():
    return os.getenv("REQUIRED_API_KEY")


def init_api_key():
    required_key = get_required_api_key()
    if required_key:
        API_KEYS[required_key] = {"name": "default", "tier": "standard"}


def check_rate_limit(api_key: str) -> bool:
    current_time = time.time()
    current_minute = int(current_time // 60)
    current_day = int(current_time // 86400)
    
    if api_key not in usage_data:
        usage_data[api_key] = {
            "minute_counts": {},
            "day_counts": {},
            "total_requests": 0
        }
    
    usage = usage_data[api_key]
    
    minute_key = str(current_minute)
    day_key = str(current_day)
    
    minute_count = usage["minute_counts"].get(minute_key, 0)
    day_count = usage["day_counts"].get(day_key, 0)
    
    limits = RATE_LIMITS["default"]
    
    if minute_count >= limits["requests_per_minute"]:
        return False
    
    if day_count >= limits["requests_per_day"]:
        return False
    
    usage["minute_counts"][minute_key] = minute_count + 1
    usage["day_counts"][day_key] = day_count + 1
    usage["total_requests"] += 1
    
    return True


def get_usage_stats(api_key: str) -> Dict[str, Any]:
    if api_key not in usage_data:
        return {"total_requests": 0, "requests_today": 0, "requests_this_minute": 0}
    
    current_time = time.time()
    current_minute = int(current_time // 60)
    current_day = int(current_time // 86400)
    
    usage = usage_data[api_key]
    
    return {
        "total_requests": usage["total_requests"],
        "requests_today": usage["day_counts"].get(str(current_day), 0),
        "requests_this_minute": usage["minute_counts"].get(str(current_minute), 0)
    }


async def validate_api_key(request: Request):
    if not get_required_api_key():
        return None
    
    api_key_header = get_api_key_header()
    api_key = request.headers.get(api_key_header)
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_API_KEY", "message": "API key required in header"}
        )
    
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_API_KEY", "message": "Invalid API key"}
        )
    
    if not check_rate_limit(api_key):
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"}
        )
    
    return api_key


class ErrorCode:
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_API_KEY = "INVALID_API_KEY"
    MISSING_API_KEY = "MISSING_API_KEY"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    TIMEOUT = "TIMEOUT"
    DOCUMENT_LIMIT = "DOCUMENT_LIMIT"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"


ERROR_RESPONSES = {
    400: {"code": ErrorCode.VALIDATION_ERROR, "message": "Invalid request"},
    401: {"code": ErrorCode.INVALID_API_KEY, "message": "Authentication failed"},
    429: {"code": ErrorCode.RATE_LIMIT_EXCEEDED, "message": "Rate limit exceeded"},
    500: {"code": ErrorCode.PROCESSING_ERROR, "message": "Processing failed"},
    504: {"code": ErrorCode.TIMEOUT, "message": "Request timeout"}
}
