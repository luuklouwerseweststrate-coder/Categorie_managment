"""Handle CSV/Excel file reading and column detection for product data."""

import io

import pandas as pd

from config import (
    BRAND_PATTERNS,
    DESCRIPTION_PATTERNS,
    IDENTIFIER_PATTERNS,
    NAME_PATTERNS,
)


def read_product_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    if filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_content))
    else:
        df = pd.read_csv(io.BytesIO(file_content), sep=None, engine="python")

    # Strip whitespace from column names
    df.columns = [str(col).strip() for col in df.columns]
    return df


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Auto-detect relevant columns based on name patterns.

    Returns a dict with keys: identifier, name, description, brand
    and values being the detected column name or None.
    """
    columns_lower = {col.lower(): col for col in df.columns}

    detected = {
        "identifier": _find_column(columns_lower, IDENTIFIER_PATTERNS),
        "name": _find_column(columns_lower, NAME_PATTERNS),
        "description": _find_column(columns_lower, DESCRIPTION_PATTERNS),
        "brand": _find_column(columns_lower, BRAND_PATTERNS),
    }
    return detected


def _find_column(columns_lower: dict[str, str], patterns: list[str]) -> str | None:
    """Find a column matching one of the given patterns."""
    # Exact match first
    for pattern in patterns:
        if pattern in columns_lower:
            return columns_lower[pattern]

    # Partial match
    for pattern in patterns:
        for col_lower, col_original in columns_lower.items():
            if pattern in col_lower:
                return col_original

    return None


def prepare_products_for_categorization(
    df: pd.DataFrame, column_mapping: dict[str, str | None]
) -> list[dict]:
    """Prepare product data for sending to Claude API.

    Returns a list of dicts with identifier, name, description, brand fields.
    """
    products = []
    for _, row in df.iterrows():
        product = {}

        identifier_col = column_mapping.get("identifier")
        if identifier_col and identifier_col in df.columns:
            product["identifier"] = str(row[identifier_col]).strip()
        else:
            continue  # Skip products without identifier

        name_col = column_mapping.get("name")
        if name_col and name_col in df.columns:
            val = row[name_col]
            product["name"] = str(val).strip() if pd.notna(val) else ""

        description_col = column_mapping.get("description")
        if description_col and description_col in df.columns:
            val = row[description_col]
            product["description"] = str(val).strip() if pd.notna(val) else ""

        brand_col = column_mapping.get("brand")
        if brand_col and brand_col in df.columns:
            val = row[brand_col]
            product["brand"] = str(val).strip() if pd.notna(val) else ""

        products.append(product)

    return products
