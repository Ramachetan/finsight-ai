"""Document extraction service for parsing and data extraction."""

import json
from typing import Any, Dict, List

from app.models.transaction import BankStatementFieldExtractionSchema, Transaction
from app.services.ade import AdeClientService
from app.services.storage import StorageService


class ExtractionService:
    """Service for document parsing and structured data extraction."""

    def __init__(self, ade_service: AdeClientService, storage_service: StorageService):
        self.ade_service = ade_service
        self.storage_service = storage_service

    def parse_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Parse a PDF document and extract markdown + chunks.

        Args:
            file_content: The PDF file as bytes
            filename: Name of the file for logging

        Returns:
            Dictionary with 'markdown' and 'chunks' keys
        """
        client = self.ade_service.get_client()

        print(f"Parsing document: {filename} ({len(file_content)} bytes)")
        parse_response = client.ade.parse(document=file_content)
        print(
            f"Parse completed. Chunks: {len(parse_response.chunks) if parse_response.chunks else 0}"
        )

        # Get markdown content from parse response
        markdown_content = parse_response.markdown
        if not markdown_content:
            raise ValueError("No markdown content returned from parsing")

        # Serialize chunks for caching
        chunks_data = AdeClientService.serialize_chunks(parse_response)

        # Build parsed data structure
        parsed_data = {
            "markdown": markdown_content,
            "chunks": chunks_data,
        }

        return parsed_data

    def extract_transactions_from_parsed(
        self, parsed_data: dict, schema: dict
    ) -> List[Transaction]:
        """
        Extract transactions from parsed markdown data using Pydantic validation.

        This is used for the default schema extraction with full Pydantic validation.
        Processes chunks individually for long documents to prevent cutoff.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction

        Returns:
            List of Transaction objects
        """
        client = self.ade_service.get_client()
        all_transactions = []
        chunks = parsed_data.get("chunks", [])
        markdown_content = parsed_data.get("markdown", "")

        # Process chunks individually for better handling of long documents
        if chunks and len(chunks) > 0:
            print(f"Processing {len(chunks)} chunks individually")

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

                    extraction_data = AdeClientService.extract_response_data(
                        extract_response
                    )
                    chunk_extraction = BankStatementFieldExtractionSchema(
                        **extraction_data
                    )
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

            extraction_data = AdeClientService.extract_response_data(extract_response)
            extraction = BankStatementFieldExtractionSchema(**extraction_data)
            all_transactions = extraction.transactions

        return all_transactions

    def extract_transactions_as_dicts(
        self, parsed_data: dict, schema: dict
    ) -> List[Dict[str, Any]]:
        """
        Extract transactions from parsed markdown as raw dictionaries.

        This is used for dynamic CSV generation with custom schemas,
        without Pydantic validation to preserve user-defined fields.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction

        Returns:
            List of transaction dictionaries
        """
        client = self.ade_service.get_client()
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

                    extraction_data = AdeClientService.extract_response_data(
                        extract_response
                    )
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

            extraction_data = AdeClientService.extract_response_data(extract_response)
            txns = extraction_data.get("transactions", [])
            if isinstance(txns, list):
                all_transactions = txns

        return all_transactions
