"""Export categorization results to Akeneo-compatible Excel format."""

import io

import pandas as pd

from config import AKENEO_CATEGORIES_COLUMN, AKENEO_IDENTIFIER_COLUMN


def create_akeneo_export(
    results: list[dict],
    source_df: pd.DataFrame,
    identifier_column: str,
    include_context: bool = True,
    name_column: str | None = None,
) -> bytes:
    """Create an Akeneo-compatible Excel file from categorization results.

    Args:
        results: List of categorization result dicts from Claude.
        source_df: Original product DataFrame for context columns.
        identifier_column: Name of the identifier column in source_df.
        include_context: Whether to include name/description columns for reference.
        name_column: Name of the product name column in source_df.

    Returns:
        Excel file as bytes.
    """
    export_data = []

    # Build a lookup from identifier to result
    result_map = {r["identifier"]: r for r in results}

    for _, row in source_df.iterrows():
        identifier = str(row[identifier_column]).strip()
        result = result_map.get(identifier, {})

        record = {
            AKENEO_IDENTIFIER_COLUMN: identifier,
            AKENEO_CATEGORIES_COLUMN: result.get("category_code", ""),
        }

        if include_context:
            if name_column and name_column in source_df.columns:
                val = row[name_column]
                record["product_naam (referentie)"] = str(val) if pd.notna(val) else ""
            record["confidence"] = result.get("confidence", "")
            record["redenering"] = result.get("reasoning", "")

        export_data.append(record)

    export_df = pd.DataFrame(export_data)

    # Write to Excel bytes
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Akeneo Import")
    output.seek(0)
    return output.getvalue()
