"""
Input validation utilities
"""
import re
from typing import Optional

def sanitize_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize user input to prevent injection attacks.
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
        
    Raises:
        ValueError: If input exceeds max_length
    """
    if not text or not text.strip():
        raise ValueError("Input cannot be empty")
    
    text = text.strip()
    
    if len(text) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length} characters")
    
    # Remove potentially dangerous characters
    # Keep alphanumeric, spaces, and common punctuation
    text = re.sub(r'[^\w\s\.\,\?\!\-\'\"\:\;\(\)]', '', text)
    
    return text

def validate_uuid(uuid_string: str) -> bool:
    """
    Validate UUID format.
    
    Args:
        uuid_string: String to validate
        
    Returns:
        True if valid UUID, False otherwise
    """
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(uuid_string))

def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email to validate
        
    Returns:
        True if valid email, False otherwise
    """
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(email_pattern.match(email))
