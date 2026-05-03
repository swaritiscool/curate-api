from typing import Dict, Any

# API Key and Rate Limiting removed as per requirements

class ErrorCode:
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    TIMEOUT = "TIMEOUT"
    DOCUMENT_LIMIT = "DOCUMENT_LIMIT"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"


ERROR_RESPONSES = {
    400: {"code": ErrorCode.VALIDATION_ERROR, "message": "Invalid request"},
    500: {"code": ErrorCode.PROCESSING_ERROR, "message": "Processing failed"},
    504: {"code": ErrorCode.TIMEOUT, "message": "Request timeout"}
}
