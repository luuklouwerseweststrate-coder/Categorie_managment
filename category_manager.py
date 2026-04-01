"""Parse and manage category lists for Akeneo categorization."""

import io
from dataclasses import dataclass

import pandas as pd


@dataclass
class Category:
    code: str
    label: str
    full_path: str


def parse_categories_from_text(text: str) -> list[Category]:
    """Parse categories from plain text, one per line.

    Supports formats:
    - Simple: "Laptops"
    - Hierarchical: "Electronics > Computers > Laptops"
    - With code: "laptops | Electronics > Computers > Laptops"
    """
    categories = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        if "|" in line:
            code, label_path = line.split("|", 1)
            code = code.strip()
            label_path = label_path.strip()
            label = label_path.split(">")[-1].strip() if ">" in label_path else label_path
            categories.append(Category(code=code, label=label, full_path=label_path))
        else:
            label = line.split(">")[-1].strip() if ">" in line else line
            code = _generate_code(line)
            categories.append(Category(code=code, label=label, full_path=line))

    return categories


def parse_categories_from_csv(file_content: bytes, filename: str) -> list[Category]:
    """Parse categories from a CSV or Excel file.

    Expected columns: code, label (and optionally parent for hierarchy).
    Falls back to treating first column as full path if no 'code' column found.
    """
    if filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_content))
    else:
        df = pd.read_csv(io.BytesIO(file_content))

    df.columns = [col.strip().lower() for col in df.columns]
    categories = []

    if "code" in df.columns and "label" in df.columns:
        parent_map = {}
        if "parent" in df.columns:
            for _, row in df.iterrows():
                code = str(row["code"]).strip()
                label = str(row["label"]).strip()
                parent = str(row.get("parent", "")).strip()
                parent_map[code] = {"label": label, "parent": parent if parent and parent != "nan" else None}

            def build_path(code: str) -> str:
                info = parent_map.get(code)
                if not info:
                    return code
                if info["parent"]:
                    return build_path(info["parent"]) + " > " + info["label"]
                return info["label"]

            for code, info in parent_map.items():
                full_path = build_path(code)
                categories.append(Category(code=code, label=info["label"], full_path=full_path))
        else:
            for _, row in df.iterrows():
                code = str(row["code"]).strip()
                label = str(row["label"]).strip()
                categories.append(Category(code=code, label=label, full_path=label))
    else:
        first_col = df.columns[0]
        for _, row in df.iterrows():
            value = str(row[first_col]).strip()
            if value and value != "nan":
                label = value.split(">")[-1].strip() if ">" in value else value
                code = _generate_code(value)
                categories.append(Category(code=code, label=label, full_path=value))

    return categories


def format_categories_for_prompt(categories: list[Category]) -> str:
    """Format categories for the Claude API prompt."""
    lines = []
    for cat in categories:
        lines.append(f"- {cat.code}: {cat.full_path}")
    return "\n".join(lines)


def get_category_options(categories: list[Category]) -> dict[str, str]:
    """Return a dict of full_path -> code for UI dropdowns."""
    return {cat.full_path: cat.code for cat in categories}


def _generate_code(text: str) -> str:
    """Generate a category code from text."""
    parts = [p.strip().lower() for p in text.split(">")]
    code = "_".join(
        part.replace(" ", "_").replace("-", "_")
        for part in parts
    )
    # Remove non-alphanumeric characters except underscores
    code = "".join(c for c in code if c.isalnum() or c == "_")
    return code
