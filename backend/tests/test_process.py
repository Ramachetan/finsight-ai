from unittest.mock import MagicMock, patch

import pytest
from app.models.transaction import (
    BankStatementFieldExtractionSchema,
    Transaction,
)
from app.utils.csv import convert_transactions_to_csv
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_extraction():
    """Create a sample extraction schema for testing."""
    return BankStatementFieldExtractionSchema(
        transactions=[
            Transaction(
                date="2024-01-01",
                amount="1000.00",
                balance="50000.00",
                remarks="Salary Deposit",
                transactionId="TXN001",
            ),
            Transaction(
                date="2024-01-02",
                amount="-500.00",
                balance="49500.00",
                remarks="Grocery Shopping",
                transactionId="TXN002",
            ),
        ]
    )


class TestProcessEndpoints:
    """Test suite for document processing endpoints."""

    @patch("app.services.ade.AdeClientService.get_client")
    @patch("app.routers.process.storage_service.read_file_content")
    @patch("app.routers.process.storage_service.save_processed_file")
    def test_process_file_success(
        self, mock_save, mock_read, mock_get_client, client, sample_extraction
    ):
        """Test successful file processing."""
        # Setup mocks
        mock_read.return_value = b"fake pdf content"

        # Mock Ade client and response
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_parse_response = MagicMock()
        mock_parse_response.markdown = "# Bank Statement\nSample markdown content"
        # Mock chunks for chunk-based processing
        mock_chunk = MagicMock()
        mock_chunk.markdown = "# Bank Statement\nSample markdown content"
        mock_chunk.id = "chunk-1"
        mock_chunk.type = "text"
        mock_chunk.grounding = None
        mock_parse_response.chunks = [mock_chunk]

        mock_client.ade.parse.return_value = mock_parse_response

        # Mock extract response - return dict that can be converted to schema
        extract_dict = {
            "transactions": [
                {
                    "date": "2024-01-01",
                    "amount": "1000.00",
                    "balance": "50000.00",
                    "remarks": "Salary",
                    "transactionId": "TXN001",
                }
            ]
        }
        mock_client.ade.extract.return_value = extract_dict

        response = client.post("/api/process/folder1/statement.pdf")

        assert response.status_code == 200
        assert "File processed successfully" in response.json()["message"]
        assert response.json()["output_file"] == "statement.pdf.csv"
        mock_save.assert_called_once()

    @patch("app.routers.process.storage_service.read_file_content")
    def test_process_file_read_error(self, mock_read, client):
        """Test processing file when read fails."""
        mock_read.side_effect = Exception("File not found")

        response = client.post("/api/process/folder1/nonexistent.pdf")

        assert response.status_code == 500
        assert "File not found" in response.json()["detail"]

    @patch("app.routers.process.storage_service.get_processed_file_content")
    def test_download_processed_file_success(self, mock_get, client):
        """Test successful file download."""
        csv_content = "Date,Transaction ID,Description,Amount,Balance\n2024-01-01,TXN001,Salary,1000.00,50000.00\n"
        mock_get.return_value = csv_content

        response = client.get("/api/process/folder1/statement.pdf.csv/download")

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "Date" in response.text
        assert "Salary" in response.text

    @patch("app.routers.process.storage_service.get_processed_file_content")
    def test_download_processed_file_not_found(self, mock_get, client):
        """Test downloading non-existent processed file."""
        mock_get.side_effect = Exception("File not found")

        response = client.get("/api/process/folder1/nonexistent.csv/download")

        assert response.status_code == 500


class TestCSVConversion:
    """Test suite for CSV conversion functionality."""

    def test_convert_extraction_to_csv(self, sample_extraction):
        """Test CSV conversion from extraction schema."""
        csv_content = convert_transactions_to_csv(sample_extraction)

        # Check headers
        assert "Date" in csv_content
        assert "Transaction ID" in csv_content
        assert "Description" in csv_content
        assert "Amount" in csv_content
        assert "Balance" in csv_content

        # Check data rows
        lines = csv_content.strip().split("\n")
        assert len(lines) == 3  # Header + 2 transactions
        assert "2024-01-01" in csv_content
        assert "TXN001" in csv_content
        assert "Salary Deposit" in csv_content

    def test_convert_extraction_to_csv_empty_transactions(self):
        """Test CSV conversion with no transactions."""
        extraction = BankStatementFieldExtractionSchema(transactions=[])

        csv_content = convert_transactions_to_csv(extraction)
        lines = csv_content.strip().split("\n")

        # Should only have header row
        assert len(lines) == 1
        assert "Date" in csv_content


class TestDynamicCSVConversion:
    """Test suite for dynamic CSV conversion with custom schemas."""

    def test_convert_dynamic_extraction_with_subset_fields(self):
        """Test dynamic CSV conversion with a schema that has fewer fields."""
        from app.utils.csv import convert_dict_transactions_to_csv

        # Transaction data as raw dicts
        transactions = [
            {"date": "2024-01-01", "amount": "+1000.00", "balance": "50000.00"},
            {"date": "2024-01-02", "amount": "-200.00", "balance": "49800.00"},
        ]

        # Schema with only date, amount, and balance (no transactionId, no remarks)
        schema = {
            "properties": {
                "transactions": {
                    "items": {
                        "properties": {
                            "date": {"type": "string"},
                            "amount": {"type": "string"},
                            "balance": {"type": "string"},
                        }
                    }
                }
            }
        }

        csv_content = convert_dict_transactions_to_csv(transactions, schema)

        # Should have 3 columns (Date, Amount, Balance)
        lines = csv_content.strip().split("\n")
        assert len(lines) == 3  # Header + 2 transactions

        # Check headers - should NOT have Transaction ID or Description
        header = lines[0]
        assert "Date" in header
        assert "Amount" in header
        assert "Balance" in header
        assert "Transaction ID" not in header
        assert "Description" not in header

        # Check data
        assert "2024-01-01" in csv_content
        assert "+1000.00" in csv_content

    def test_convert_dynamic_extraction_with_custom_field(self):
        """Test dynamic CSV conversion with custom field names."""
        from app.utils.csv import convert_dict_transactions_to_csv

        transactions = [
            {"date": "2024-01-01", "amount": "+500.00", "category": "Food"},
        ]

        schema = {
            "properties": {
                "transactions": {
                    "items": {
                        "properties": {
                            "date": {"type": "string"},
                            "amount": {"type": "string"},
                            "category": {"type": "string"},
                        }
                    }
                }
            }
        }

        csv_content = convert_dict_transactions_to_csv(transactions, schema)

        # Should have Category header (title-cased)
        assert "Category" in csv_content
        assert "Food" in csv_content

    def test_convert_dynamic_extraction_filters_internal_fields(self):
        """Test that internal fields like credit_amount are filtered out."""
        from app.utils.csv import convert_dict_transactions_to_csv

        transactions = [
            {
                "date": "2024-01-01",
                "amount": "+1000.00",
                "credit_amount": "1000.00",
                "debit_amount": "",
            },
        ]

        # Schema includes internal fields that should be filtered
        schema = {
            "$defs": {
                "Transaction": {
                    "properties": {
                        "date": {"type": "string"},
                        "amount": {"type": "string"},
                        "credit_amount": {"type": "string"},
                        "debit_amount": {"type": "string"},
                    }
                }
            },
            "properties": {"transactions": {"items": {"$ref": "#/$defs/Transaction"}}},
        }

        csv_content = convert_dict_transactions_to_csv(transactions, schema)

        # Internal fields should be filtered out
        header = csv_content.split("\n")[0]
        assert "credit_amount" not in header.lower()
        assert "debit_amount" not in header.lower()
        assert "Date" in header
        assert "Amount" in header


class TestBankStatementSchema:
    """Test suite for bank statement schema validation."""

    def test_transaction_creation(self):
        """Test Transaction schema creation."""
        txn = Transaction(
            date="2024-01-01",
            amount="1000.00",
            balance="50000.00",
            remarks="Salary",
            transactionId="TXN001",
        )

        assert txn.date == "2024-01-01"
        assert txn.amount == "+1000.00"
        assert txn.transactionId == "TXN001"

    def test_transaction_creation_with_none_id(self):
        """Test Transaction schema creation with None transactionId."""
        txn = Transaction(
            date="2024-01-01",
            amount="1000.00",
            balance="50000.00",
            remarks="Salary",
            transactionId=None,
        )

        assert txn.transactionId == ""

    def test_bank_statement_extraction_schema(self, sample_extraction):
        """Test complete BankStatementFieldExtractionSchema creation."""
        assert len(sample_extraction.transactions) == 2


class TestParseEndpoint:
    """Test suite for the parse-only endpoint."""

    @patch("app.services.ade.AdeClientService.get_client")
    @patch("app.routers.process.storage_service.read_file_content")
    @patch("app.routers.process.storage_service.save_parsed_output")
    @patch("app.routers.process.storage_service.get_parsed_output")
    def test_parse_file_success(
        self, mock_get_parsed, mock_save_parsed, mock_read, mock_get_client, client
    ):
        """Test successful file parsing."""
        # No cached data
        mock_get_parsed.return_value = None
        mock_read.return_value = b"fake pdf content"

        # Mock Ade client
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_parse_response = MagicMock()
        mock_parse_response.markdown = "# Bank Statement\nSample markdown content"
        mock_chunk = MagicMock()
        mock_chunk.markdown = "# Bank Statement"
        mock_chunk.id = "chunk-1"
        mock_chunk.type = "text"
        mock_chunk.grounding = MagicMock()
        mock_chunk.grounding.page = 0
        mock_chunk.grounding.box = None
        mock_parse_response.chunks = [mock_chunk]

        mock_client.ade.parse.return_value = mock_parse_response

        response = client.post("/api/process/folder1/statement.pdf/parse")

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "statement.pdf"
        assert data["chunks_count"] == 1
        assert data["has_markdown"] is True
        assert data["used_cache"] is False
        mock_save_parsed.assert_called_once()

    @patch("app.routers.process.storage_service.get_parsed_output")
    def test_parse_file_uses_cache(self, mock_get_parsed, client):
        """Test that parse returns cached data when available."""
        mock_get_parsed.return_value = {
            "markdown": "# Cached markdown",
            "chunks": [{"id": "chunk-1", "type": "text", "markdown": "Content"}],
        }

        response = client.post("/api/process/folder1/statement.pdf/parse")

        assert response.status_code == 200
        data = response.json()
        assert data["used_cache"] is True
        assert "using cache" in data["message"].lower()


class TestSchemaEndpoints:
    """Test suite for schema management endpoints."""

    @patch("app.routers.process.storage_service.get_extraction_schema")
    def test_get_schema_default(self, mock_get_schema, client):
        """Test getting default schema when no custom schema exists."""
        mock_get_schema.return_value = None

        response = client.get("/api/process/folder1/statement.pdf/schema")

        assert response.status_code == 200
        data = response.json()
        assert data["is_custom"] is False
        assert "schema" in data
        # Default schema should have transactions property
        assert "properties" in data["schema"] or "$defs" in data["schema"]

    @patch("app.routers.process.storage_service.get_extraction_schema")
    def test_get_schema_custom(self, mock_get_schema, client):
        """Test getting custom schema when one exists."""
        custom_schema = {
            "type": "object",
            "properties": {"custom_field": {"type": "string"}},
        }
        mock_get_schema.return_value = custom_schema

        response = client.get("/api/process/folder1/statement.pdf/schema")

        assert response.status_code == 200
        data = response.json()
        assert data["is_custom"] is True
        assert data["schema"] == custom_schema

    @patch("app.routers.process.storage_service.save_extraction_schema")
    def test_update_schema_success(self, mock_save_schema, client):
        """Test successfully updating extraction schema."""
        new_schema = {"type": "object", "properties": {"new_field": {"type": "string"}}}

        response = client.put(
            "/api/process/folder1/statement.pdf/schema", json={"schema": new_schema}
        )

        assert response.status_code == 200
        data = response.json()
        assert "updated" in data["message"].lower()
        mock_save_schema.assert_called_once()

    def test_update_schema_invalid_not_object(self, client):
        """Test that updating with invalid schema (not an object) fails."""
        response = client.put(
            "/api/process/folder1/statement.pdf/schema", json={"schema": "not a dict"}
        )

        # Pydantic returns 422 for type validation errors
        assert response.status_code == 422

    def test_update_schema_missing_required_keys(self, client):
        """Test that updating with schema missing required keys fails."""
        response = client.put(
            "/api/process/folder1/statement.pdf/schema",
            json={"schema": {"random_key": "value"}},
        )

        assert response.status_code == 400

    @patch("app.routers.process.storage_service.delete_extraction_schema")
    def test_delete_schema_success(self, mock_delete_schema, client):
        """Test successfully deleting custom schema."""
        mock_delete_schema.return_value = True

        response = client.delete("/api/process/folder1/statement.pdf/schema")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

    @patch("app.routers.process.storage_service.delete_extraction_schema")
    def test_delete_schema_not_found(self, mock_delete_schema, client):
        """Test deleting schema when none exists."""
        mock_delete_schema.return_value = False

        response = client.delete("/api/process/folder1/statement.pdf/schema")

        assert response.status_code == 200
        data = response.json()
        assert "no custom schema" in data["message"].lower()


class TestExtractEndpoint:
    """Test suite for the extract endpoint."""

    @patch("app.routers.process.storage_service.get_parsed_output")
    def test_extract_no_parsed_data(self, mock_get_parsed, client):
        """Test extraction fails when no parsed data exists."""
        mock_get_parsed.return_value = None

        response = client.post("/api/process/folder1/statement.pdf/extract")

        assert response.status_code == 404
        assert "parsed data not found" in response.json()["detail"].lower()

    @patch("app.services.ade.AdeClientService.get_client")
    @patch("app.routers.process.storage_service.get_parsed_output")
    @patch("app.routers.process.storage_service.get_extraction_schema")
    @patch("app.routers.process.storage_service.save_processed_file")
    def test_extract_with_default_schema(
        self, mock_save, mock_get_schema, mock_get_parsed, mock_get_client, client
    ):
        """Test extraction using default schema."""
        # Setup parsed data
        mock_get_parsed.return_value = {
            "markdown": "# Bank Statement",
            "chunks": [
                {"markdown": "| Date | Amount |\n| --- | --- |", "type": "table"}
            ],
        }

        # No custom schema
        mock_get_schema.return_value = None

        # Mock Ade client
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        extract_dict = {
            "transactions": [
                {
                    "date": "2024-01-01",
                    "amount": "100.00",
                    "balance": "1000.00",
                    "remarks": "Test",
                }
            ]
        }
        mock_client.ade.extract.return_value = extract_dict

        response = client.post("/api/process/folder1/statement.pdf/extract")

        assert response.status_code == 200
        data = response.json()
        assert data["transactions_count"] == 1
        assert data["used_custom_schema"] is False
        assert "csv_content" in data

    @patch("app.services.ade.AdeClientService.get_client")
    @patch("app.routers.process.storage_service.get_parsed_output")
    @patch("app.routers.process.storage_service.get_extraction_schema")
    @patch("app.routers.process.storage_service.save_processed_file")
    def test_extract_with_custom_schema(
        self, mock_save, mock_get_schema, mock_get_parsed, mock_get_client, client
    ):
        """Test extraction using custom schema."""
        mock_get_parsed.return_value = {
            "markdown": "# Bank Statement",
            "chunks": [{"markdown": "Data here", "type": "text"}],
        }

        # Custom schema exists
        mock_get_schema.return_value = {
            "type": "object",
            "properties": {"transactions": {"type": "array"}},
        }

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        extract_dict = {
            "transactions": [
                {
                    "date": "2024-01-01",
                    "amount": "200.00",
                    "balance": "2000.00",
                    "remarks": "Custom",
                }
            ]
        }
        mock_client.ade.extract.return_value = extract_dict

        response = client.post("/api/process/folder1/statement.pdf/extract")

        assert response.status_code == 200
        data = response.json()
        assert data["used_custom_schema"] is True
