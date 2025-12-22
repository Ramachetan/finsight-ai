"""Transaction models for bank statement extraction."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.amount import detect_negative, normalize_amount


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
    """Schema for extracting transactions from bank statements."""

    transactions: list[Transaction] = Field(
        ...,
        description="List of individual transaction records from the statement tables.",
        title="Transactions",
    )
