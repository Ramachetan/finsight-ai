import csv
import io
import json
import os
import re
from typing import Dict, List, Optional

from ade import Ade
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.storage import StorageService

router = APIRouter(prefix="/process", tags=["process"])
storage_service = StorageService()

# In-memory progress tracker: {folder_id/filename: {"phase": str, "message": str, "progress": int}}
_processing_progress: Dict[str, dict] = {}


def _get_progress_key(folder_id: str, filename: str) -> str:
    """Generate a unique key for tracking progress of a specific file."""
    return f"{folder_id}/{filename}"


def _update_progress(
    folder_id: str, filename: str, phase: str, message: str, progress: int = 0
):
    """Update progress tracking for a file being processed."""
    key = _get_progress_key(folder_id, filename)
    _processing_progress[key] = {
        "phase": phase,
        "message": message,
        "progress": min(progress, 100),
    }


def _clear_progress(folder_id: str, filename: str):
    """Clear progress tracking after processing completes."""
    key = _get_progress_key(folder_id, filename)
    _processing_progress.pop(key, None)


def normalize_amount(value: str) -> str:
    """
    Clean and normalize an amount string by removing currency symbols,
    whitespace, and extracting only the numeric value.
    Returns the cleaned numeric string (digits and decimal point only).
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


# Pydantic models for LandingAI ADE
class Transaction(BaseModel):
    """
    Universal transaction model that handles multiple bank statement layouts.
    Supports: separate Debit/Credit columns, single Amount column, Dr/Cr indicators.
    """

    date: str = Field(
        default="",
        description="Date of the transaction in any format found (e.g., DD/MM/YYYY, MM-DD-YYYY, etc.).",
        title="Transaction Date",
    )

    # Primary output field - populated by validator from optional fields
    # Must be Optional to accept None from API before validator normalizes it
    amount: Optional[str] = Field(
        default=None,
        description=(
            "Final normalized transaction amount with sign. "
            "DO NOT extract directly - this is computed from other amount fields. "
            "Leave empty/null; the system will populate it from credit_amount, debit_amount, or raw_amount."
        ),
        title="Normalized Amount",
    )

    # Optional fields for polymorphic extraction based on statement layout
    credit_amount: Optional[str] = Field(
        default=None,
        description=(
            "Money coming INTO the account. Extract from columns labeled: "
            '"Credit", "Cr", "Deposits", "Money In", "Received", or similar. '
            "If separate columns exist for money in/out, map the incoming amount here. "
            "Leave null/empty if no separate credit column exists."
        ),
        title="Credit Amount",
    )

    debit_amount: Optional[str] = Field(
        default=None,
        description=(
            "Money going OUT of the account. Extract from columns labeled: "
            '"Debit", "Dr", "Withdrawals", "Money Out", "Paid", or similar. '
            "If separate columns exist for money in/out, map the outgoing amount here. "
            "Leave null/empty if no separate debit column exists."
        ),
        title="Debit Amount",
    )

    raw_amount: Optional[str] = Field(
        default=None,
        description=(
            "Generic transaction amount when only ONE amount column exists. "
            "Extract the value as-is including any signs, parentheses, or Dr/Cr text. "
            "Use this field ONLY when there are no separate credit/debit columns. "
            'Examples: "100.00", "-50.00", "(75.00)", "200.00 Cr", "150.00 Dr".'
        ),
        title="Raw Amount",
    )

    type_indicator: Optional[str] = Field(
        default=None,
        description=(
            "Transaction type indicator if shown in a SEPARATE column from the amount. "
            'Extract values like: "Dr", "Cr", "D", "C", "Debit", "Credit". '
            "Only populate if the indicator is in its own column, not embedded in the amount."
        ),
        title="Type Indicator",
    )

    balance: str = Field(
        default="",
        description="Account balance after the transaction. Extract the closing/running balance value.",
        title="Balance",
    )

    remarks: str = Field(
        default="",
        description=(
            "Description, narration, or remarks for the transaction. "
            "May include payee name, reference numbers, or transaction details."
        ),
        title="Remarks",
    )

    transactionId: str = Field(
        default="",
        description=(
            "Unique identifier for the transaction such as reference number, "
            "transaction ID, or cheque number. Leave empty if not available."
        ),
        title="Transaction ID",
    )

    @field_validator("date", mode="before")
    @classmethod
    def normalize_date(cls, v):
        """Handle None or missing date values."""
        if v is None:
            return ""
        return str(v)

    @field_validator("balance", mode="before")
    @classmethod
    def normalize_balance(cls, v):
        """Handle None or missing balance values."""
        if v is None:
            return ""
        return str(v)

    @field_validator("transactionId", mode="before")
    @classmethod
    def normalize_transaction_id(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("remarks", mode="before")
    @classmethod
    def normalize_remarks(cls, v):
        """
        Handle cases where the extraction model returns a dictionary or other type
        instead of a string for remarks.
        """
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # Handle specific artifact seen in logs: {'refs': []}
            if "refs" in v and len(v) == 1:
                return ""
            # Try to find a text-like field
            for key in ["value", "text", "content", "description"]:
                if key in v:
                    return str(v[key])
            # Fallback to string representation
            return str(v)
        return str(v)

    @model_validator(mode="after")
    def normalize_transaction_amount(self) -> "Transaction":
        """
        Normalize the amount field from various input formats:
        - Scenario A: Separate credit/debit columns -> use sign based on which is populated
        - Scenario B: Raw amount with sign detection -> parse and determine sign
        - Scenario C: Raw amount with type indicator -> use indicator for sign
        """
        # Skip if amount is already populated with a valid value
        if self.amount and self.amount not in ("", "0", "0.00"):
            # Still normalize the existing amount
            is_negative = detect_negative(self.amount)
            cleaned = normalize_amount(self.amount)
            if cleaned:
                self.amount = f"-{cleaned}" if is_negative else f"+{cleaned}"
            return self

        final_amount = ""
        sign = "+"

        # Scenario A: Separate credit/debit columns
        if self.debit_amount and self.debit_amount.strip():
            cleaned = normalize_amount(self.debit_amount)
            if cleaned and cleaned != "0" and cleaned != "0.00":
                final_amount = cleaned
                sign = "-"  # Debit = money out = negative

        if not final_amount and self.credit_amount and self.credit_amount.strip():
            cleaned = normalize_amount(self.credit_amount)
            if cleaned and cleaned != "0" and cleaned != "0.00":
                final_amount = cleaned
                sign = "+"  # Credit = money in = positive

        # Scenario B & C: Raw amount with optional type indicator
        if not final_amount and self.raw_amount and self.raw_amount.strip():
            cleaned = normalize_amount(self.raw_amount)
            if cleaned:
                final_amount = cleaned

                # Check type_indicator first (Scenario C)
                if self.type_indicator:
                    indicator = self.type_indicator.lower().strip()
                    if indicator in ("dr", "d", "debit", "withdrawal"):
                        sign = "-"
                    elif indicator in ("cr", "c", "credit", "deposit"):
                        sign = "+"
                    else:
                        # Fall back to detecting from raw_amount
                        sign = "-" if detect_negative(self.raw_amount) else "+"
                else:
                    # Scenario B: Detect sign from raw_amount itself
                    sign = "-" if detect_negative(self.raw_amount) else "+"

        # Set the final normalized amount (always a string, never None)
        if final_amount:
            self.amount = f"{sign}{final_amount}"
        else:
            self.amount = "+0.00"  # Default for empty/missing amounts

        return self


class BankStatementFieldExtractionSchema(BaseModel):
    transactions: List[Transaction] = Field(
        ...,
        description="List of individual transaction records from the statement tables.",
        title="Transactions",
    )


def convert_extraction_to_csv(extraction: BankStatementFieldExtractionSchema) -> str:
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


def convert_dynamic_extraction_to_csv(transactions: List[Dict], schema: Dict) -> str:
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


def get_ade_client():
    """
    Create and return an ADE client instance.
    Uses VISION_AGENT_API_KEY or ADE_API_KEY from environment.
    """

    # Support both old and new API key env vars for backwards compatibility
    api_key = os.environ.get("ADE_API_KEY") or os.environ.get("VISION_AGENT_API_KEY")
    if not api_key:
        raise ValueError(
            "ADE_API_KEY or VISION_AGENT_API_KEY environment variable is required"
        )

    return Ade(
        apikey=api_key,
        # Configure retries and timeout for long documents
        max_retries=3,
        timeout=300.0,  # 5 minutes for large documents
    )


def pydantic_to_json_schema(model: type[BaseModel]) -> dict:
    """Convert a Pydantic model to JSON schema for ADE extraction."""
    schema = model.model_json_schema()
    return schema


def process_extraction_response(
    extraction_data: dict,
) -> BankStatementFieldExtractionSchema:
    """
    Process extraction response from ADE and convert to our schema.
    Handles the 'extraction' wrapper if present.
    """
    # Check if wrapped in 'extraction' key
    if "extraction" in extraction_data:
        extraction_data = extraction_data["extraction"]

    return BankStatementFieldExtractionSchema(**extraction_data)


def extract_transactions_from_parsed_data(
    parsed_data: dict, client, schema: dict
) -> List[Transaction]:
    """
    Extract transactions from parsed markdown data.
    This is separated to allow re-extraction from cached parsed output.
    Returns Transaction objects for use with the default schema.
    """
    all_transactions = []
    chunks = parsed_data.get("chunks", [])
    markdown_content = parsed_data.get("markdown", "")

    # Check if we have chunks to process individually
    # This helps with long documents where the output might be cut short
    if chunks and len(chunks) > 0:
        print(f"Processing {len(chunks)} chunks individually")

        for i, chunk in enumerate(chunks):
            # Skip empty chunks
            chunk_markdown = (
                chunk.get("markdown")
                if isinstance(chunk, dict)
                else getattr(chunk, "markdown", None)
            )
            if not chunk_markdown:
                continue

            print(f"Extracting from chunk {i + 1}/{len(chunks)}")
            try:
                chunk_markdown_bytes = chunk_markdown.encode("utf-8")

                extract_response = client.ade.extract(
                    markdown=chunk_markdown_bytes,
                    schema=json.dumps(schema),
                )

                # Process the extraction response
                if hasattr(extract_response, "extraction"):
                    extraction_data = extract_response.extraction
                elif hasattr(extract_response, "to_dict"):
                    extraction_data = extract_response.to_dict()
                else:
                    extraction_data = dict(extract_response)

                # Handle if extraction is wrapped
                if (
                    isinstance(extraction_data, dict)
                    and "extraction" in extraction_data
                ):
                    extraction_data = extraction_data["extraction"]

                # Convert to our Pydantic model
                chunk_extraction = BankStatementFieldExtractionSchema(**extraction_data)
                all_transactions.extend(chunk_extraction.transactions)
                print(
                    f"Chunk {i + 1}: Found {len(chunk_extraction.transactions)} transactions"
                )

            except Exception as e:
                print(f"Error extracting chunk {i + 1}: {e}")
                # Continue to next chunk
    else:
        # Fallback to full markdown if no chunks available
        print("No chunks found, extracting from full markdown")
        if not markdown_content:
            raise ValueError("No markdown content available for extraction")

        markdown_bytes = markdown_content.encode("utf-8")

        extract_response = client.ade.extract(
            markdown=markdown_bytes,
            schema=json.dumps(schema),
        )

        if hasattr(extract_response, "extraction"):
            extraction_data = extract_response.extraction
        elif hasattr(extract_response, "to_dict"):
            extraction_data = extract_response.to_dict()
        else:
            extraction_data = dict(extract_response)

        if isinstance(extraction_data, dict) and "extraction" in extraction_data:
            extraction_data = extraction_data["extraction"]

        extraction = BankStatementFieldExtractionSchema(**extraction_data)
        all_transactions = extraction.transactions

    return all_transactions


def extract_transactions_as_dicts(
    parsed_data: dict, client, schema: dict
) -> List[Dict]:
    """
    Extract transactions from parsed markdown data as raw dictionaries.
    This is used for dynamic CSV generation with custom schemas.
    Returns raw dict data without Pydantic validation.
    """
    all_transactions = []
    chunks = parsed_data.get("chunks", [])
    markdown_content = parsed_data.get("markdown", "")

    if chunks and len(chunks) > 0:
        print(f"Processing {len(chunks)} chunks individually (dynamic schema)")

        for i, chunk in enumerate(chunks):
            chunk_markdown = (
                chunk.get("markdown")
                if isinstance(chunk, dict)
                else getattr(chunk, "markdown", None)
            )
            if not chunk_markdown:
                continue

            print(f"Extracting from chunk {i + 1}/{len(chunks)}")
            try:
                chunk_markdown_bytes = chunk_markdown.encode("utf-8")

                extract_response = client.ade.extract(
                    markdown=chunk_markdown_bytes,
                    schema=json.dumps(schema),
                )

                # Process the extraction response
                if hasattr(extract_response, "extraction"):
                    extraction_data = extract_response.extraction
                elif hasattr(extract_response, "to_dict"):
                    extraction_data = extract_response.to_dict()
                else:
                    extraction_data = dict(extract_response)

                # Handle if extraction is wrapped
                if (
                    isinstance(extraction_data, dict)
                    and "extraction" in extraction_data
                ):
                    extraction_data = extraction_data["extraction"]

                # Get transactions as raw dicts
                txns = extraction_data.get("transactions", [])
                if isinstance(txns, list):
                    all_transactions.extend(txns)
                print(f"Chunk {i + 1}: Found {len(txns)} transactions")

            except Exception as e:
                print(f"Error extracting chunk {i + 1}: {e}")
    else:
        print("No chunks found, extracting from full markdown (dynamic schema)")
        if not markdown_content:
            raise ValueError("No markdown content available for extraction")

        markdown_bytes = markdown_content.encode("utf-8")

        extract_response = client.ade.extract(
            markdown=markdown_bytes,
            schema=json.dumps(schema),
        )

        if hasattr(extract_response, "extraction"):
            extraction_data = extract_response.extraction
        elif hasattr(extract_response, "to_dict"):
            extraction_data = extract_response.to_dict()
        else:
            extraction_data = dict(extract_response)

        if isinstance(extraction_data, dict) and "extraction" in extraction_data:
            extraction_data = extraction_data["extraction"]

        txns = extraction_data.get("transactions", [])
        if isinstance(txns, list):
            all_transactions = txns

    return all_transactions


@router.post("/{folder_id}/{filename}")
def process_file(folder_id: str, filename: str, force_reparse: bool = False):
    """
    Process a file using LandingAI ADE (ade-python) and save the result as CSV.

    Uses the official ade-python library which provides:
    - Automatic retry logic (configurable via max_retries)
    - Proper error handling with typed exceptions
    - Support for both sync and async operations
    - Built-in timeout handling for long documents

    Args:
        folder_id: The folder containing the file
        filename: The file to process
        force_reparse: If True, re-parse the document even if cached parsed output exists.
                      Useful when the parsing model is updated. Default is False.

    Cost Optimization:
        - Parsed output (markdown + chunks) is cached to avoid re-parsing on extraction errors
        - Re-extraction from cache is much cheaper than re-parsing the full document
        - Use force_reparse=True only when the parsing model has been updated
    """
    try:
        # Initialize the ADE client
        client = get_ade_client()
        schema = pydantic_to_json_schema(BankStatementFieldExtractionSchema)

        parsed_data = None
        used_cache = False

        # Check for cached parsed output (unless force_reparse is requested)
        if not force_reparse:
            parsed_data = storage_service.get_parsed_output(folder_id, filename)
            if parsed_data:
                print(f"Using cached parsed output for: {filename}")
                used_cache = True
                _update_progress(
                    folder_id, filename, "Parsing", "Using cached parse (faster!)", 50
                )

        # Parse the document if no cache available
        if not parsed_data:
            _update_progress(
                folder_id, filename, "Parsing", "Reading and converting document...", 10
            )

            # Get file content as bytes
            file_content = storage_service.read_file_content(folder_id, filename)

            # Log processing start
            print(f"Parsing document: {filename} ({len(file_content)} bytes)")

            # Step 1: Parse the document (the expensive step)
            parse_response = client.ade.parse(document=file_content)

            print(
                f"Parse completed. Chunks: {len(parse_response.chunks) if parse_response.chunks else 0}"
            )

            # Get markdown content from parse response
            markdown_content = parse_response.markdown
            if not markdown_content:
                raise ValueError("No markdown content returned from parsing")

            # Convert chunks to serializable format for caching
            # New ADE API uses: id (not chunk_id), type, grounding.box, grounding.page
            chunks_data = []
            if parse_response.chunks:
                for chunk in parse_response.chunks:
                    chunk_dict = {}
                    if hasattr(chunk, "markdown"):
                        chunk_dict["markdown"] = chunk.markdown

                    # New API uses 'id' instead of 'chunk_id'
                    if hasattr(chunk, "id"):
                        chunk_dict["id"] = chunk.id
                    elif hasattr(chunk, "chunk_id"):
                        chunk_dict["id"] = chunk.chunk_id

                    # Chunk type (text, table, etc.)
                    if hasattr(chunk, "type"):
                        chunk_dict["type"] = chunk.type

                    # Grounding information (bounding box + page)
                    if hasattr(chunk, "grounding") and chunk.grounding:
                        grounding = chunk.grounding
                        grounding_dict = {}

                        # Page number from grounding
                        if hasattr(grounding, "page"):
                            grounding_dict["page"] = grounding.page
                            chunk_dict["page_number"] = (
                                grounding.page
                            )  # Keep for backwards compatibility

                        # Bounding box coordinates
                        if hasattr(grounding, "box") and grounding.box:
                            box = grounding.box
                            grounding_dict["box"] = {
                                "left": getattr(box, "left", None)
                                or getattr(box, "l", None),
                                "top": getattr(box, "top", None)
                                or getattr(box, "t", None),
                                "right": getattr(box, "right", None)
                                or getattr(box, "r", None),
                                "bottom": getattr(box, "bottom", None)
                                or getattr(box, "b", None),
                            }

                        chunk_dict["grounding"] = grounding_dict
                    elif hasattr(chunk, "page_number"):
                        # Fallback for legacy API
                        chunk_dict["page_number"] = chunk.page_number

                    chunks_data.append(chunk_dict)

            # Build parsed data structure
            parsed_data = {
                "markdown": markdown_content,
                "chunks": chunks_data,
            }

            # Save parsed output for future re-extraction (cost savings!)
            try:
                storage_service.save_parsed_output(folder_id, filename, parsed_data)
                print(f"Saved parsed output for: {filename}")
            except Exception as e:
                print(f"Warning: Failed to cache parsed output: {e}")
                # Continue processing even if caching fails

        # Step 2: Extract structured data using our schema
        print("Extracting structured data...")
        _update_progress(
            folder_id, filename, "Extracting", "Extracting transactions...", 75
        )
        all_transactions = extract_transactions_from_parsed_data(
            parsed_data, client, schema
        )

        # Create final extraction object with all transactions
        extraction = BankStatementFieldExtractionSchema(transactions=all_transactions)
        print(f"Total extracted {len(extraction.transactions)} transactions")

        # Convert to CSV
        csv_content = convert_extraction_to_csv(extraction)

        # Save CSV
        csv_filename = f"{filename}.csv"
        storage_service.save_processed_file(folder_id, csv_filename, csv_content)

        # Clear progress tracking when done
        _clear_progress(folder_id, filename)

        return {
            "message": "File processed successfully",
            "output_file": csv_filename,
            "transactions_count": len(extraction.transactions),
            "used_cached_parse": used_cache,
            "pages_processed": len(parsed_data.get("chunks", [])) if parsed_data else 0,
            "processing_metadata": {
                "chunks_count": len(parsed_data.get("chunks", []))
                if parsed_data
                else 0,
                "has_markdown": bool(parsed_data.get("markdown"))
                if parsed_data
                else False,
            },
        }

    except Exception as e:
        print(f"Error processing file: {e}")
        _clear_progress(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/{filename}/status")
def get_processing_status(folder_id: str, filename: str):
    """
    Get the current processing status for a file.
    Returns the phase, message, and progress percentage.
    If not processing, returns None.
    """
    key = _get_progress_key(folder_id, filename)
    status = _processing_progress.get(key)

    if status:
        return status

    # If not found, check if the file has already been processed
    # (no longer in progress)
    return {"phase": None, "message": "Not processing", "progress": 0}


@router.api_route("/{folder_id}/{filename}/download", methods=["GET", "HEAD"])
def download_processed_file(folder_id: str, filename: str):
    """
    Download the processed CSV file.
    Supports both GET (download) and HEAD (check existence) methods.
    """
    try:
        # Ensure filename ends with .csv if the user didn't provide it
        # But the user might request the original filename + .csv
        # The process_file returns output_file which is filename.csv

        content = storage_service.get_processed_file_content(folder_id, filename)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/{filename}/metadata")
def get_file_metadata(folder_id: str, filename: str):
    """
    Retrieve the parsed metadata for a file, including chunks and processing stats.
    """
    try:
        parsed_data = storage_service.get_parsed_output(folder_id, filename)
        if not parsed_data:
            raise HTTPException(
                status_code=404,
                detail="Parsed data not found. Please process the file first.",
            )

        chunks = parsed_data.get("chunks", [])

        # Calculate chunk type statistics
        type_counts = {}
        for chunk in chunks:
            chunk_type = chunk.get("type", "unknown")
            type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1

        # Get unique pages from grounding or page_number
        pages = set()
        for chunk in chunks:
            if "grounding" in chunk and "page" in chunk["grounding"]:
                pages.add(chunk["grounding"]["page"])
            elif "page_number" in chunk:
                pages.add(chunk["page_number"])

        # Return metadata without the full markdown content to save bandwidth
        # The markdown can be fetched separately if needed
        return {
            "filename": filename,
            "chunks_count": len(chunks),
            "pages_count": len(pages) if pages else 1,
            "pages": sorted(list(pages)) if pages else [0],
            "has_markdown": bool(parsed_data.get("markdown")),
            "chunk_types": type_counts,
            "chunks": chunks,
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/{filename}/markdown")
def get_file_markdown(folder_id: str, filename: str):
    """
    Retrieve the full markdown content of the parsed file.
    """
    try:
        parsed_data = storage_service.get_parsed_output(folder_id, filename)
        if not parsed_data or not parsed_data.get("markdown"):
            raise HTTPException(
                status_code=404,
                detail="Markdown content not found. Please process the file first.",
            )

        return Response(
            content=parsed_data["markdown"],
            media_type="text/markdown",
            headers={"Content-Disposition": f'inline; filename="{filename}.md"'},
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 1: Parse-only endpoint
# ============================================================================


@router.post("/{folder_id}/{filename}/parse")
def parse_file(folder_id: str, filename: str, force_reparse: bool = False):
    """
    Parse a document and return markdown + chunks without extracting data.

    This is the first step in the two-phase workflow:
    1. Parse: Convert PDF to markdown/chunks (this endpoint)
    2. Extract: Extract structured data using a schema (separate endpoint)

    Args:
        folder_id: The folder containing the file
        filename: The file to parse
        force_reparse: If True, re-parse even if cached output exists

    Returns:
        Parsed document metadata including chunks, pages, and availability of markdown
    """
    try:
        # Check for cached parsed output (unless force_reparse is requested)
        if not force_reparse:
            parsed_data = storage_service.get_parsed_output(folder_id, filename)
            if parsed_data:
                print(f"Using cached parsed output for: {filename}")
                chunks = parsed_data.get("chunks", [])

                # Calculate metadata
                type_counts = {}
                pages = set()
                for chunk in chunks:
                    chunk_type = chunk.get("type", "unknown")
                    type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
                    if "grounding" in chunk and "page" in chunk["grounding"]:
                        pages.add(chunk["grounding"]["page"])
                    elif "page_number" in chunk:
                        pages.add(chunk["page_number"])

                return {
                    "message": "Document already parsed (using cache)",
                    "filename": filename,
                    "chunks_count": len(chunks),
                    "pages_count": len(pages) if pages else 1,
                    "pages": sorted(list(pages)) if pages else [0],
                    "has_markdown": bool(parsed_data.get("markdown")),
                    "chunk_types": type_counts,
                    "used_cache": True,
                }

        # Initialize the ADE client
        client = get_ade_client()

        _update_progress(
            folder_id, filename, "Parsing", "Reading and converting document...", 10
        )

        # Get file content as bytes
        file_content = storage_service.read_file_content(folder_id, filename)
        print(f"Parsing document: {filename} ({len(file_content)} bytes)")

        # Parse the document
        parse_response = client.ade.parse(document=file_content)
        print(
            f"Parse completed. Chunks: {len(parse_response.chunks) if parse_response.chunks else 0}"
        )

        # Get markdown content from parse response
        markdown_content = parse_response.markdown
        if not markdown_content:
            raise ValueError("No markdown content returned from parsing")

        # Convert chunks to serializable format for caching
        chunks_data = []
        if parse_response.chunks:
            for chunk in parse_response.chunks:
                chunk_dict = {}
                if hasattr(chunk, "markdown"):
                    chunk_dict["markdown"] = chunk.markdown

                if hasattr(chunk, "id"):
                    chunk_dict["id"] = chunk.id
                elif hasattr(chunk, "chunk_id"):
                    chunk_dict["id"] = chunk.chunk_id

                if hasattr(chunk, "type"):
                    chunk_dict["type"] = chunk.type

                if hasattr(chunk, "grounding") and chunk.grounding:
                    grounding = chunk.grounding
                    grounding_dict = {}

                    if hasattr(grounding, "page"):
                        grounding_dict["page"] = grounding.page
                        chunk_dict["page_number"] = grounding.page

                    if hasattr(grounding, "box") and grounding.box:
                        box = grounding.box
                        grounding_dict["box"] = {
                            "left": getattr(box, "left", None)
                            or getattr(box, "l", None),
                            "top": getattr(box, "top", None) or getattr(box, "t", None),
                            "right": getattr(box, "right", None)
                            or getattr(box, "r", None),
                            "bottom": getattr(box, "bottom", None)
                            or getattr(box, "b", None),
                        }

                    chunk_dict["grounding"] = grounding_dict
                elif hasattr(chunk, "page_number"):
                    chunk_dict["page_number"] = chunk.page_number

                chunks_data.append(chunk_dict)

        # Build parsed data structure
        parsed_data = {
            "markdown": markdown_content,
            "chunks": chunks_data,
        }

        # Save parsed output for future use
        storage_service.save_parsed_output(folder_id, filename, parsed_data)
        print(f"Saved parsed output for: {filename}")

        _clear_progress(folder_id, filename)

        # Calculate metadata for response
        type_counts = {}
        pages = set()
        for chunk in chunks_data:
            chunk_type = chunk.get("type", "unknown")
            type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
            if "grounding" in chunk and "page" in chunk["grounding"]:
                pages.add(chunk["grounding"]["page"])
            elif "page_number" in chunk:
                pages.add(chunk["page_number"])

        return {
            "message": "Document parsed successfully",
            "filename": filename,
            "chunks_count": len(chunks_data),
            "pages_count": len(pages) if pages else 1,
            "pages": sorted(list(pages)) if pages else [0],
            "has_markdown": bool(markdown_content),
            "chunk_types": type_counts,
            "used_cache": False,
        }

    except Exception as e:
        print(f"Error parsing file: {e}")
        _clear_progress(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 2: Schema Management endpoints
# ============================================================================


class SchemaUpdateRequest(BaseModel):
    """Request body for updating an extraction schema."""

    schema_definition: dict = Field(
        ...,
        alias="schema",
        description="JSON Schema for extraction. Must be a valid JSON Schema object.",
    )


@router.get("/{folder_id}/{filename}/schema")
def get_extraction_schema(folder_id: str, filename: str):
    """
    Get the extraction schema for a file.

    Returns the custom schema if one has been saved, otherwise returns
    the default BankStatementFieldExtractionSchema.

    Args:
        folder_id: The folder containing the file
        filename: The file to get the schema for

    Returns:
        JSON Schema for extraction, plus metadata about whether it's custom or default
    """
    try:
        # Check for custom schema first
        custom_schema = storage_service.get_extraction_schema(folder_id, filename)
        if custom_schema:
            return {
                "schema": custom_schema,
                "is_custom": True,
                "message": "Custom schema found for this file",
            }

        # Return default schema
        default_schema = pydantic_to_json_schema(BankStatementFieldExtractionSchema)
        return {
            "schema": default_schema,
            "is_custom": False,
            "message": "Using default extraction schema",
        }

    except Exception as e:
        print(f"Error getting extraction schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{folder_id}/{filename}/schema")
def update_extraction_schema(
    folder_id: str, filename: str, request: SchemaUpdateRequest
):
    """
    Update the extraction schema for a file.

    The schema must be a valid JSON Schema object. It will be used for
    subsequent extractions instead of the default schema.

    Args:
        folder_id: The folder containing the file
        filename: The file to set the schema for
        request: The schema update request containing the new schema

    Returns:
        Confirmation of schema update
    """
    try:
        schema = request.schema_definition

        # Basic JSON Schema validation
        if not isinstance(schema, dict):
            raise HTTPException(
                status_code=400,
                detail="Schema must be a JSON object",
            )

        # Check for required JSON Schema properties
        if (
            "type" not in schema
            and "properties" not in schema
            and "$defs" not in schema
        ):
            raise HTTPException(
                status_code=400,
                detail="Schema must contain 'type', 'properties', or '$defs'",
            )

        # Save the schema
        storage_service.save_extraction_schema(folder_id, filename, schema)

        return {
            "message": "Schema updated successfully",
            "filename": filename,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating extraction schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{folder_id}/{filename}/schema")
def delete_extraction_schema(folder_id: str, filename: str):
    """
    Delete the custom extraction schema for a file.

    After deletion, the default schema will be used for extraction.

    Args:
        folder_id: The folder containing the file
        filename: The file to delete the schema for

    Returns:
        Confirmation of schema deletion
    """
    try:
        deleted = storage_service.delete_extraction_schema(folder_id, filename)

        if deleted:
            return {
                "message": "Custom schema deleted successfully",
                "filename": filename,
            }
        else:
            return {
                "message": "No custom schema found to delete",
                "filename": filename,
            }

    except Exception as e:
        print(f"Error deleting extraction schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 3: Extract with custom schema endpoint
# ============================================================================


@router.post("/{folder_id}/{filename}/extract")
def extract_transactions(folder_id: str, filename: str, use_custom_schema: bool = True):
    """
    Extract transactions from a parsed document using the stored schema.

    This is the second step in the two-phase workflow:
    1. Parse: Convert PDF to markdown/chunks (done previously)
    2. Extract: Extract structured data using a schema (this endpoint)

    Args:
        folder_id: The folder containing the file
        filename: The file to extract from
        use_custom_schema: If True, use custom schema if available; otherwise use default

    Returns:
        Extraction results including transaction count and CSV filename
    """
    try:
        # Check if parsed data exists
        parsed_data = storage_service.get_parsed_output(folder_id, filename)
        if not parsed_data:
            raise HTTPException(
                status_code=404,
                detail="Parsed data not found. Please parse the file first using POST /parse",
            )

        # Get the schema to use
        schema = None
        used_custom_schema = False

        if use_custom_schema:
            schema = storage_service.get_extraction_schema(folder_id, filename)
            if schema:
                used_custom_schema = True
                print(f"Using custom schema for extraction: {filename}")

        if not schema:
            schema = pydantic_to_json_schema(BankStatementFieldExtractionSchema)
            print(f"Using default schema for extraction: {filename}")

        # Initialize the ADE client
        client = get_ade_client()

        _update_progress(
            folder_id, filename, "Extracting", "Extracting transactions...", 50
        )

        # Extract transactions and convert to CSV
        # Use dynamic extraction for custom schemas to respect user's field selection
        if used_custom_schema:
            # Extract as raw dicts for dynamic CSV generation
            all_transactions = extract_transactions_as_dicts(
                parsed_data, client, schema
            )
            print(f"Total extracted {len(all_transactions)} transactions (dynamic)")

            # Convert to CSV dynamically based on schema fields
            csv_content = convert_dynamic_extraction_to_csv(all_transactions, schema)
            transactions_count = len(all_transactions)
        else:
            # Use original flow with Pydantic models for default schema
            all_transactions = extract_transactions_from_parsed_data(
                parsed_data, client, schema
            )

            # Create final extraction object with all transactions
            extraction = BankStatementFieldExtractionSchema(
                transactions=all_transactions
            )
            print(f"Total extracted {len(extraction.transactions)} transactions")

            # Convert to CSV
            csv_content = convert_extraction_to_csv(extraction)
            transactions_count = len(extraction.transactions)

        # Save CSV
        csv_filename = f"{filename}.csv"
        storage_service.save_processed_file(folder_id, csv_filename, csv_content)

        _clear_progress(folder_id, filename)

        return {
            "message": "Extraction completed successfully",
            "output_file": csv_filename,
            "transactions_count": transactions_count,
            "used_custom_schema": used_custom_schema,
            "csv_content": csv_content,  # Include CSV content in response for immediate use
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error extracting transactions: {e}")
        _clear_progress(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))
