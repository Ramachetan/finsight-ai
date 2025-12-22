"""Utilities for normalizing and validating amount values."""

import re


def normalize_amount(value: str) -> str:
    """
    Clean and normalize an amount string by removing currency symbols,
    whitespace, and extracting only the numeric value.

    Args:
        value: The amount string to normalize

    Returns:
        The cleaned numeric string (digits and decimal point only)
    """
    if not value:
        return ""
    # Remove common currency symbols and whitespace
    cleaned = re.sub(r"[$₹€£¥,\s]", "", value.strip())
    # Extract numeric value (digits and decimal point)
    match = re.search(r"[\d]+\.?\d*", cleaned)
    return match.group(0) if match else ""


def detect_negative(value: str) -> bool:
    """
    Detect if an amount string represents a negative value.
    Checks for parentheses (accounting notation), minus signs, or "Dr" indicator.

    Args:
        value: The amount string to check

    Returns:
        True if the amount is negative, False otherwise
    """
    if not value:
        return False
    value_lower = value.lower().strip()
    # Check for parentheses: (100.00) or (100)
    if value.startswith("(") and value.endswith(")"):
        return True
    # Check for leading minus sign
    if value.startswith("-"):
        return True
    # Check for trailing minus sign (some formats)
    if value.endswith("-"):
        return True
    # Check for "Dr" indicator (debit)
    if "dr" in value_lower:
        return True
    return False
