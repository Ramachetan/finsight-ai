"""CSV conversion utilities for transaction data."""

import csv
import io
from typing import Any, Dict, List

from app.models.transaction import BankStatementFieldExtractionSchema


def convert_transactions_to_csv(
    extraction: BankStatementFieldExtractionSchema,
) -> str:
    """
    Convert Transaction objects to CSV format.

    Uses the standard Transaction schema fields:
    Date, Transaction ID, Description, Amount, Balance

    Args:
        extraction: BankStatementFieldExtractionSchema with transactions

    Returns:
        CSV string content
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    headers = ["Date", "Transaction ID", "Description", "Amount", "Balance"]
    writer.writerow(headers)

    # Write transactions
    for txn in extraction.transactions:
        writer.writerow(
            [txn.date, txn.transactionId, txn.remarks, txn.amount, txn.balance]
        )

    return output.getvalue()


def convert_dict_transactions_to_csv(
    transactions: List[Dict[str, Any]], schema: Dict[str, Any]
) -> str:
    """
    Convert extraction data to CSV dynamically based on schema fields.

    This function reads the schema to determine which columns to include
    in the CSV output, allowing users to customize which fields appear.

    Args:
        transactions: List of transaction dictionaries from extraction
        schema: JSON Schema that was used for extraction

    Returns:
        CSV string with columns matching the schema fields
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Extract field names from schema
    # Schema structure: {properties: {transactions: {items: {properties: {field1: ..., field2: ...}}}}}
    field_names = []

    # Navigate the JSON Schema to find transaction item properties
    if "$defs" in schema and "Transaction" in schema["$defs"]:
        # Standard Pydantic-generated schema format
        txn_props = schema["$defs"]["Transaction"].get("properties", {})
        field_names = list(txn_props.keys())
    elif "properties" in schema:
        if "transactions" in schema["properties"]:
            txn_schema = schema["properties"]["transactions"]
            if "items" in txn_schema and "properties" in txn_schema["items"]:
                field_names = list(txn_schema["items"]["properties"].keys())
            elif "$ref" in txn_schema.get("items", {}):
                # Handle $ref to $defs
                ref = txn_schema["items"]["$ref"]
                if ref.startswith("#/$defs/"):
                    def_name = ref.split("/")[-1]
                    if "$defs" in schema and def_name in schema["$defs"]:
                        txn_props = schema["$defs"][def_name].get("properties", {})
                        field_names = list(txn_props.keys())
        else:
            # Flat schema - fields are directly in properties
            field_names = list(schema["properties"].keys())

    # Filter out internal/computed fields that shouldn't be in CSV
    # These are fields used for normalization, not for output
    internal_fields = {"credit_amount", "debit_amount", "raw_amount", "type_indicator"}
    field_names = [f for f in field_names if f not in internal_fields]

    # If no fields found, use default
    if not field_names:
        field_names = ["date", "transactionId", "remarks", "amount", "balance"]

    # Create human-readable headers
    header_mapping = {
        "date": "Date",
        "transactionId": "Transaction ID",
        "remarks": "Description",
        "amount": "Amount",
        "balance": "Balance",
    }
    headers = [header_mapping.get(f, f.replace("_", " ").title()) for f in field_names]
    writer.writerow(headers)

    # Write transactions
    for txn in transactions:
        row = []
        for field in field_names:
            value = txn.get(field, "")
            # Handle None values
            if value is None:
                value = ""
            # Handle dict values (sometimes remarks comes as dict)
            if isinstance(value, dict):
                value = str(value.get("value", value.get("text", "")))
            row.append(value)
        writer.writerow(row)

    return output.getvalue()
