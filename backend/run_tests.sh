#!/bin/bash

# Credit Evaluation Engine - Test Runner

set -e

echo "================================"
echo "FastAPI Credit Evaluation Engine"
echo "Test Suite"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "Error: main.py not found. Please run this script from the project root."
    exit 1
fi

# Install test dependencies if needed
echo "📦 Checking dependencies..."
if ! python -c "import pytest" 2>/dev/null; then
    echo "Installing test dependencies..."
    pip install -e ".[test]"
fi

echo ""
echo "🧪 Running tests..."
echo ""

# Run tests with coverage
pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

echo ""
echo "✅ Test run complete!"
echo ""
echo "Coverage report generated in htmlcov/index.html"
