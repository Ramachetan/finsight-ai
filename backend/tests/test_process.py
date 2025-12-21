from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.routers.process import (
    BankStatementFieldExtractionSchema,
    Transaction,
    convert_extraction_to_csv,
)
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
                transactionId="TXN001"
            ),
            Transaction(
                date="2024-01-02",
                amount="-500.00",
                balance="49500.00",
                remarks="Grocery Shopping",
                transactionId="TXN002"
            )
        ]
    )


class TestProcessEndpoints:
    """Test suite for document processing endpoints."""
    
    @patch('app.routers.process.storage_service.read_file_content')
    @patch('app.routers.process.Ade')
    @patch('app.routers.process.storage_service.save_processed_file')
    def test_process_file_success(self, mock_save, mock_ade_class, mock_read, client, sample_extraction):
        """Test successful file processing."""
        # Setup mocks
        mock_read.return_value = b"fake pdf content"
        
        # Mock Ade client and response
        mock_client = MagicMock()
        mock_ade_class.return_value = mock_client
        
        mock_parse_response = MagicMock()
        mock_parse_response.markdown = "# Bank Statement\nSample markdown content"
        # Mock chunks for chunk-based processing
        mock_chunk = MagicMock()
        mock_chunk.markdown = "# Bank Statement\nSample markdown content"
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
                    "transactionId": "TXN001"
                }
            ]
        }
        mock_client.ade.extract.return_value = extract_dict
        
        response = client.post("/process/folder1/statement.pdf")
        
        assert response.status_code == 200
        assert "File processed successfully" in response.json()["message"]
        assert response.json()["output_file"] == "statement.pdf.csv"
        mock_save.assert_called_once()
    
    @patch('app.routers.process.storage_service.read_file_content')
    def test_process_file_read_error(self, mock_read, client):
        """Test processing file when read fails."""
        mock_read.side_effect = Exception("File not found")
        
        response = client.post("/process/folder1/nonexistent.pdf")
        
        assert response.status_code == 500
        assert "File not found" in response.json()["detail"]
    
    @patch('app.routers.process.storage_service.get_processed_file_content')
    def test_download_processed_file_success(self, mock_get, client):
        """Test successful file download."""
        csv_content = "Date,Transaction ID,Description,Amount,Balance\n2024-01-01,TXN001,Salary,1000.00,50000.00\n"
        mock_get.return_value = csv_content
        
        response = client.get("/process/folder1/statement.pdf.csv/download")
        
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "Date" in response.text
        assert "Salary" in response.text
    
    @patch('app.routers.process.storage_service.get_processed_file_content')
    def test_download_processed_file_not_found(self, mock_get, client):
        """Test downloading non-existent processed file."""
        mock_get.side_effect = Exception("File not found")
        
        response = client.get("/process/folder1/nonexistent.csv/download")
        
        assert response.status_code == 500


class TestCSVConversion:
    """Test suite for CSV conversion functionality."""
    
    def test_convert_extraction_to_csv(self, sample_extraction):
        """Test CSV conversion from extraction schema."""
        csv_content = convert_extraction_to_csv(sample_extraction)
        
        # Check headers
        assert "Date" in csv_content
        assert "Transaction ID" in csv_content
        assert "Description" in csv_content
        assert "Amount" in csv_content
        assert "Balance" in csv_content
        
        # Check data rows
        lines = csv_content.strip().split('\n')
        assert len(lines) == 3  # Header + 2 transactions
        assert "2024-01-01" in csv_content
        assert "TXN001" in csv_content
        assert "Salary Deposit" in csv_content
    
    def test_convert_extraction_to_csv_empty_transactions(self):
        """Test CSV conversion with no transactions."""
        extraction = BankStatementFieldExtractionSchema(
            transactions=[]
        )
        
        csv_content = convert_extraction_to_csv(extraction)
        lines = csv_content.strip().split('\n')
        
        # Should only have header row
        assert len(lines) == 1
        assert "Date" in csv_content


class TestBankStatementSchema:
    """Test suite for bank statement schema validation."""
    
    def test_transaction_creation(self):
        """Test Transaction schema creation."""
        txn = Transaction(
            date="2024-01-01",
            amount="1000.00",
            balance="50000.00",
            remarks="Salary",
            transactionId="TXN001"
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
            transactionId=None
        )
        
        assert txn.transactionId == ""
    
    def test_bank_statement_extraction_schema(self, sample_extraction):
        """Test complete BankStatementFieldExtractionSchema creation."""
        assert len(sample_extraction.transactions) == 2
