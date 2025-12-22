"""Router for document processing endpoints."""

import json
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.models.transaction import BankStatementFieldExtractionSchema
from app.services.ade import get_ade_service
from app.services.extraction import ExtractionService
from app.services.progress import get_progress_tracker
from app.services.storage import StorageService
from app.utils.csv import convert_dict_transactions_to_csv, convert_transactions_to_csv

router = APIRouter(prefix="/process", tags=["process"])
storage_service = StorageService()
ade_service = get_ade_service()
extraction_service = ExtractionService(ade_service, storage_service)
progress_tracker = get_progress_tracker()


class SchemaUpdateRequest(BaseModel):
    """Request body for updating an extraction schema."""

    schema_definition: dict = Field(
        ...,
        alias="schema",
        description="JSON Schema for extraction. Must be a valid JSON Schema object.",
    )


# =============================================================================
# Legacy Endpoint: Combined Parse + Extract
# =============================================================================


@router.post("/{folder_id}/{filename}")
def process_file(folder_id: str, filename: str, force_reparse: bool = False):
    """
    Process a file using LandingAI ADE and save the result as CSV.

    LEGACY ENDPOINT: Use the two-phase workflow instead:
    1. POST /parse to parse the document
    2. POST /extract to extract with a schema

    This endpoint combines both for backward compatibility.

    Args:
        folder_id: The folder containing the file
        filename: The file to process
        force_reparse: If True, re-parse even if cached parsed output exists.
                      Useful when the parsing model is updated. Default is False.

    Cost Optimization:
        - Parsed output (markdown + chunks) is cached to avoid re-parsing
        - Re-extraction from cache is much cheaper than re-parsing
        - Use force_reparse=True only when the parsing model updates
    """
    try:
        schema = ade_service.pydantic_to_json_schema(
            BankStatementFieldExtractionSchema
        )

        parsed_data = None
        used_cache = False

        # Check for cached parsed output (unless force_reparse is requested)
        if not force_reparse:
            parsed_data = storage_service.get_parsed_output(folder_id, filename)
            if parsed_data:
                print(f"Using cached parsed output for: {filename}")
                used_cache = True
                progress_tracker.update(
                    folder_id, filename, "Parsing", "Using cached parse (faster!)", 50
                )

        # Parse the document if no cache available
        if not parsed_data:
            progress_tracker.update(
                folder_id, filename, "Parsing", "Reading and converting document...", 10
            )

            file_content = storage_service.read_file_content(folder_id, filename)
            parsed_data = extraction_service.parse_document(file_content, filename)

            # Save parsed output for future use
            try:
                storage_service.save_parsed_output(folder_id, filename, parsed_data)
                print(f"Saved parsed output for: {filename}")
            except Exception as e:
                print(f"Warning: Failed to cache parsed output: {e}")

        # Step 2: Extract structured data using default schema
        print("Extracting structured data...")
        progress_tracker.update(
            folder_id, filename, "Extracting", "Extracting transactions...", 75
        )
        
        all_transactions = extraction_service.extract_transactions_from_parsed(
            parsed_data, schema
        )

        # Create final extraction object
        extraction = BankStatementFieldExtractionSchema(transactions=all_transactions)
        print(f"Total extracted {len(extraction.transactions)} transactions")

        # Convert to CSV and save
        csv_content = convert_transactions_to_csv(extraction)
        csv_filename = f"{filename}.csv"
        storage_service.save_processed_file(folder_id, csv_filename, csv_content)

        progress_tracker.clear(folder_id, filename)

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
        progress_tracker.clear(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/{filename}/status")
def get_processing_status(folder_id: str, filename: str):
    """
    Get the current processing status for a file.
    
    Returns the phase, message, and progress percentage.
    If not processing, returns a neutral status.
    """
    status = progress_tracker.get(folder_id, filename)

    if status:
        return status

    return {"phase": None, "message": "Not processing", "progress": 0}


@router.api_route("/{folder_id}/{filename}/download", methods=["GET", "HEAD"])
def download_processed_file(folder_id: str, filename: str):
    """
    Download the processed CSV file.
    
    Supports both GET (download) and HEAD (check existence) methods.
    """
    try:
        content = storage_service.get_processed_file_content(folder_id, filename)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
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

        # Get unique pages
        pages = set()
        for chunk in chunks:
            if "grounding" in chunk and "page" in chunk["grounding"]:
                pages.add(chunk["grounding"]["page"])
            elif "page_number" in chunk:
                pages.add(chunk["page_number"])

        return {
            "filename": filename,
            "chunks_count": len(chunks),
            "pages_count": len(pages) if pages else 1,
            "pages": sorted(list(pages)) if pages else [0],
            "has_markdown": bool(parsed_data.get("markdown")),
            "chunk_types": type_counts,
            "chunks": chunks,
        }
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 1: Parse-only endpoint
# =============================================================================


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
        Parsed document metadata including chunks, pages, and markdown availability
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

        progress_tracker.update(
            folder_id, filename, "Parsing", "Reading and converting document...", 10
        )

        # Get file content and parse
        file_content = storage_service.read_file_content(folder_id, filename)
        parsed_data = extraction_service.parse_document(file_content, filename)

        # Save parsed output
        storage_service.save_parsed_output(folder_id, filename, parsed_data)
        print(f"Saved parsed output for: {filename}")

        progress_tracker.clear(folder_id, filename)

        # Calculate metadata for response
        chunks_data = parsed_data.get("chunks", [])
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
            "has_markdown": bool(parsed_data.get("markdown")),
            "chunk_types": type_counts,
            "used_cache": False,
        }

    except Exception as e:
        print(f"Error parsing file: {e}")
        progress_tracker.clear(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 2: Schema Management endpoints
# =============================================================================


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
        default_schema = ade_service.pydantic_to_json_schema(
            BankStatementFieldExtractionSchema
        )
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


# =============================================================================
# Phase 3: Extract with custom schema endpoint
# =============================================================================


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
            schema = ade_service.pydantic_to_json_schema(
                BankStatementFieldExtractionSchema
            )
            print(f"Using default schema for extraction: {filename}")

        progress_tracker.update(
            folder_id, filename, "Extracting", "Starting extraction...", 10
        )

        # Extract transactions and convert to CSV
        # Use dynamic extraction for custom schemas to respect user's field selection
        if used_custom_schema:
            progress_tracker.update(
                folder_id, filename, "Extracting", "Extracting with custom schema...", 40
            )
            all_transactions = extraction_service.extract_transactions_as_dicts(
                parsed_data, schema
            )
            print(f"Total extracted {len(all_transactions)} transactions (dynamic)")

            progress_tracker.update(
                folder_id, filename, "Extracting", "Generating CSV...", 80
            )
            csv_content = convert_dict_transactions_to_csv(all_transactions, schema)
            transactions_count = len(all_transactions)
        else:
            progress_tracker.update(
                folder_id, filename, "Extracting", "Extracting with default schema...", 40
            )
            all_transactions = extraction_service.extract_transactions_from_parsed(
                parsed_data, schema
            )

            extraction = BankStatementFieldExtractionSchema(
                transactions=all_transactions
            )
            print(f"Total extracted {len(extraction.transactions)} transactions")

            progress_tracker.update(
                folder_id, filename, "Extracting", "Generating CSV...", 80
            )
            csv_content = convert_transactions_to_csv(extraction)
            transactions_count = len(extraction.transactions)

        # Save CSV
        progress_tracker.update(
            folder_id, filename, "Extracting", "Saving results...", 95
        )
        csv_filename = f"{filename}.csv"
        storage_service.save_processed_file(folder_id, csv_filename, csv_content)

        progress_tracker.clear(folder_id, filename)

        return {
            "message": "Extraction completed successfully",
            "output_file": csv_filename,
            "transactions_count": transactions_count,
            "used_custom_schema": used_custom_schema,
            "csv_content": csv_content,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error extracting transactions: {e}")
        progress_tracker.clear(folder_id, filename)
        raise HTTPException(status_code=500, detail=str(e))
