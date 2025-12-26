"""Document extraction service for parsing and data extraction."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from app.models.transaction import BankStatementFieldExtractionSchema, Transaction
from app.services.ade import AdeClientService
from app.services.storage import StorageService


class ExtractionService:
    """Service for document parsing and structured data extraction."""

    def __init__(self, ade_service: AdeClientService, storage_service: StorageService):
        self.ade_service = ade_service
        self.storage_service = storage_service
        # Thread pool for concurrent extraction (chunk extraction is I/O bound via HTTP)
        self.executor = ThreadPoolExecutor(max_workers=4)

    def shutdown(self, wait: bool = True) -> None:
        """
        Shut down the internal thread pool executor.

        Args:
            wait: If True, this call will block until all pending futures are done.
        """
        if self.executor is not None:
            self.executor.shutdown(wait=wait)
            self.executor = None

    def __enter__(self) -> "ExtractionService":
        """Allow use of ExtractionService as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ensure the executor is shut down when leaving a context manager scope."""
        self.shutdown(wait=True)

    def parse_document(
        self,
        file_content: bytes,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Parse a PDF document and extract markdown + chunks.

        Always uses Parse Jobs API which supports up to 6,000 pages / 1 GB.
        This avoids the 100-page limit of the standard parsing API.

        Args:
            file_content: The PDF file as bytes
            filename: Name of the file for logging
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            Dictionary with 'markdown' and 'chunks' keys
        """
        file_size_mb = len(file_content) / (1024 * 1024)
        
        # Always use Parse Jobs to support up to 6,000 pages / 1 GB
        # Standard parse is limited to 100 pages
        print(f"Parsing document with Parse Jobs: {filename} ({file_size_mb:.1f} MB)")
        if progress_callback:
            progress_callback(5, "Starting async parse job...")

        # Create parse job
        job_id = self.ade_service.create_parse_job(file_content)
        print(f"Created parse job: {job_id}")

        if progress_callback:
            progress_callback(10, f"Parse job created: {job_id}")

        # Wait for completion with progress updates
        raw_data = self.ade_service.wait_for_parse_job(
            job_id,
            progress_callback=progress_callback,
        )

        # Get markdown content
        markdown_content = raw_data.get("markdown", "")
        if not markdown_content:
            raise ValueError("No markdown content returned from parsing")

        # Serialize chunks for caching (handles both response objects and dicts)
        chunks = raw_data.get("chunks", [])
        if chunks and hasattr(chunks[0], "markdown"):
            # Response objects - need to serialize using ADE service
            # Create a mock response object for serialize_chunks
            class _ParseResponse:
                def __init__(self, chunks_list):
                    self.chunks = chunks_list
            
            response_obj = _ParseResponse(chunks)
            chunks_data = self.ade_service.serialize_chunks(response_obj)
        else:
            # Already serialized dicts
            chunks_data = chunks

        print(f"Parse completed. Chunks: {len(chunks_data)}")

        return {
            "markdown": markdown_content,
            "chunks": chunks_data,
        }

    def extract_transactions_from_parsed(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Transaction]:
        """
        Extract transactions from parsed markdown data using Pydantic validation.

        This is used for the default schema extraction with full Pydantic validation.
        Processes chunks concurrently for better performance on long documents.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of Transaction objects
        """
        # Run async extraction depending on whether an event loop is already running
        try:
            # If this does not raise, we're in an async context and must not block the loop.
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to create one and block until completion.
            return asyncio.run(
                self._extract_transactions_from_parsed_async(parsed_data, schema, progress_callback)
            )
        else:
            # In an async context: return the coroutine so the caller can await it.
            # This should not happen in the current codebase, but handles it correctly.
            raise RuntimeError(
                "extract_transactions_from_parsed called from async context. "
                "This method is synchronous. Use _extract_transactions_from_parsed_async directly."
            )

    async def _extract_transactions_from_parsed_async(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Transaction]:
        """
        Async helper for extracting transactions from parsed markdown data.

        Processes chunks concurrently using a thread pool executor.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of Transaction objects
        """
        client = self.ade_service.get_client()
        all_transactions = []
        chunks = parsed_data.get("chunks", [])
        markdown_content = parsed_data.get("markdown", "")

        # Process chunks individually for better handling of long documents
        if chunks and len(chunks) > 0:
            print(f"Processing {len(chunks)} chunks concurrently")
            total_chunks = len(chunks)

            # Create extraction tasks for all chunks using the current running event loop
            loop = asyncio.get_running_loop()
            tasks = []
            
            for i, chunk in enumerate(chunks):
                chunk_markdown = (
                    chunk.get("markdown")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "markdown", None)
                )
                if not chunk_markdown:
                    continue

                # Submit extraction task to thread pool
                task = loop.run_in_executor(
                    self.executor,
                    self._extract_single_chunk_pydantic,
                    client,
                    chunk_markdown,
                    schema,
                    i,
                    total_chunks,
                )
                tasks.append(task)

            # Track progress in real-time while preserving order with gather()
            completed_count = 0

            async def extract_with_tracking(task_coro, chunk_idx):
                nonlocal completed_count
                result = await task_coro
                completed_count += 1
                if progress_callback and total_chunks > 0:
                    progress_pct = 40 + (completed_count / total_chunks) * 35  # 40-75% for extraction
                    progress_callback(
                        progress_pct,
                        f"Extracted chunk {completed_count}/{total_chunks}"
                    )
                return (chunk_idx, result)

            # Wrap tasks with tracking and gather results in order
            tracked_tasks = [extract_with_tracking(task, i) for i, task in enumerate(tasks)]
            results = await asyncio.gather(*tracked_tasks, return_exceptions=True)

            # Process results in original chunk order
            # Separate successful results from exceptions before sorting
            successful_results = []
            failed_results = []
            
            for item in results:
                if isinstance(item, Exception):
                    failed_results.append(item)
                elif isinstance(item, tuple):
                    successful_results.append(item)
                else:
                    # Log unexpected result types for debugging
                    print(f"Warning: Unexpected result type {type(item)}: {item}")
            
            # Sort successful results by chunk index
            for chunk_idx, result in sorted(successful_results, key=lambda x: x[0]):
                if result is not None:
                    chunk_extraction = result
                    all_transactions.extend(chunk_extraction.transactions)
                    print(
                        f"Chunk {chunk_idx + 1}/{total_chunks}: Found {len(chunk_extraction.transactions)} transactions"
                    )
            
            # Log any failures
            for error in failed_results:
                print(f"Error extracting chunk: {error}")
        else:
            # Fallback to full markdown if no chunks available
            print("No chunks found, extracting from full markdown")
            if not markdown_content:
                raise ValueError("No markdown content available for extraction")

            extract_response = client.extract(
                markdown=markdown_content,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            extraction = BankStatementFieldExtractionSchema(**extraction_data)
            all_transactions = extraction.transactions

        return all_transactions

    def _extract_single_chunk_pydantic(
        self, client: Any, chunk_markdown: str, schema: dict, chunk_idx: int, total_chunks: int
    ) -> Optional[BankStatementFieldExtractionSchema]:
        """
        Extract transactions from a single chunk (runs in thread pool).

        Args:
            client: The ADE client
            chunk_markdown: The markdown content of the chunk
            schema: JSON Schema for extraction
            chunk_idx: Index of this chunk (for logging)
            total_chunks: Total number of chunks (for logging)

        Returns:
            BankStatementFieldExtractionSchema or None if error
        """
        try:
            print(f"Extracting from chunk {chunk_idx + 1}/{total_chunks}")
            extract_response = client.extract(
                markdown=chunk_markdown,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            return BankStatementFieldExtractionSchema(**extraction_data)

        except Exception as e:
            print(f"Error extracting chunk {chunk_idx + 1}: {e}")
            return None

    def extract_transactions_as_dicts(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract transactions from parsed markdown as raw dictionaries.

        This is used for dynamic CSV generation with custom schemas,
        without Pydantic validation to preserve user-defined fields.
        Processes chunks concurrently for better performance.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of transaction dictionaries
        """
        # Run async extraction depending on whether an event loop is already running
        try:
            # If this does not raise, we're in an async context and must not block the loop.
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to create one and block until completion.
            return asyncio.run(
                self._extract_transactions_as_dicts_async(parsed_data, schema, progress_callback)
            )
        else:
            # In an async context: return the coroutine so the caller can await it.
            # This should not happen in the current codebase, but handles it correctly.
            raise RuntimeError(
                "extract_transactions_as_dicts called from async context. "
                "This method is synchronous. Use _extract_transactions_as_dicts_async directly."
            )

    async def _extract_transactions_as_dicts_async(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Async helper for extracting transactions as dictionaries.

        Processes chunks concurrently using a thread pool executor.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of transaction dictionaries
        """
        client = self.ade_service.get_client()
        all_transactions = []
        chunks = parsed_data.get("chunks", [])
        markdown_content = parsed_data.get("markdown", "")

        if chunks and len(chunks) > 0:
            print(f"Processing {len(chunks)} chunks concurrently (dynamic schema)")
            total_chunks = len(chunks)

            # Create extraction tasks for all chunks using the current running event loop
            loop = asyncio.get_running_loop()
            tasks = []
            
            for i, chunk in enumerate(chunks):
                chunk_markdown = (
                    chunk.get("markdown")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "markdown", None)
                )
                if not chunk_markdown:
                    continue

                # Submit extraction task to thread pool
                task = loop.run_in_executor(
                    self.executor,
                    self._extract_single_chunk_dict,
                    client,
                    chunk_markdown,
                    schema,
                    i,
                    total_chunks,
                )
                tasks.append(task)

            # Track progress in real-time while preserving order with gather()
            completed_count = 0

            async def extract_with_tracking(task_coro, chunk_idx):
                nonlocal completed_count
                result = await task_coro
                completed_count += 1
                if progress_callback and total_chunks > 0:
                    progress_pct = 40 + (completed_count / total_chunks) * 35  # 40-75% for extraction
                    progress_callback(
                        progress_pct,
                        f"Extracted chunk {completed_count}/{total_chunks}"
                    )
                return (chunk_idx, result)

            # Wrap tasks with tracking and gather results in order
            tracked_tasks = [extract_with_tracking(task, i) for i, task in enumerate(tasks)]
            results = await asyncio.gather(*tracked_tasks, return_exceptions=True)

            # Process results in original chunk order
            # Separate successful results from exceptions before sorting
            successful_results = []
            failed_results = []
            
            for item in results:
                if isinstance(item, Exception):
                    failed_results.append(item)
                elif isinstance(item, tuple):
                    successful_results.append(item)
                else:
                    # Log unexpected result types for debugging
                    print(f"Warning: Unexpected result type {type(item)}: {item}")
            
            # Sort successful results by chunk index
            for chunk_idx, result in sorted(successful_results, key=lambda x: x[0]):
                if result is not None:
                    txns = result
                    all_transactions.extend(txns)
                    print(f"Chunk {chunk_idx + 1}/{total_chunks}: Found {len(txns)} transactions")
            
            # Log any failures
            for error in failed_results:
                print(f"Error extracting chunk: {error}")
        else:
            print("No chunks found, extracting from full markdown (dynamic schema)")
            if not markdown_content:
                raise ValueError("No markdown content available for extraction")

            extract_response = client.extract(
                markdown=markdown_content,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            txns = extraction_data.get("transactions", [])
            if isinstance(txns, list):
                all_transactions = txns

        return all_transactions

    def _extract_single_chunk_dict(
        self, client: Any, chunk_markdown: str, schema: dict, chunk_idx: int, total_chunks: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Extract transactions from a single chunk as dicts (runs in thread pool).

        Args:
            client: The ADE client
            chunk_markdown: The markdown content of the chunk
            schema: JSON Schema for extraction
            chunk_idx: Index of this chunk (for logging)
            total_chunks: Total number of chunks (for logging)

        Returns:
            List of transaction dictionaries or None if error
        """
        try:
            print(f"Extracting from chunk {chunk_idx + 1}/{total_chunks}")
            extract_response = client.extract(
                markdown=chunk_markdown,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            txns = extraction_data.get("transactions", [])
            if isinstance(txns, list):
                return txns
            return []

        except Exception as e:
            print(f"Error extracting chunk {chunk_idx + 1}: {e}")
            return None
