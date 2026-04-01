"""Claude API integration for product categorization."""

import json
import time

import anthropic

from category_manager import Category, format_categories_for_prompt
from config import BATCH_DELAY_SECONDS, DEFAULT_BATCH_SIZE, MAX_TOKENS


def build_system_prompt(categories: list[Category]) -> str:
    """Build the system prompt with the full category list."""
    category_text = format_categories_for_prompt(categories)
    return f"""Je bent een expert in productcategorisatie voor Akeneo PIM. Je krijgt een lijst met productcategorieën en een batch producten. Voor elk product wijs je de best passende categorie toe uit de lijst.

BESCHIKBARE CATEGORIEËN:
{category_text}

Regels:
- Gebruik ALLEEN categorieën uit de bovenstaande lijst. Verzin nooit nieuwe categorieën.
- Wijs precies één categorie toe per product.
- Gebruik de category CODE (niet het label) in je antwoord.
- Analyseer de productnaam, beschrijving, merk en andere attributen.
- Als geen categorie goed past, kies de dichtstbijzijnde match en markeer confidence als "low".
- Geef een korte redenering in het Nederlands."""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "categorizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "Product identifier/SKU"},
                    "category_code": {"type": "string", "description": "The category code from the list"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level of the categorization",
                    },
                    "reasoning": {"type": "string", "description": "Brief explanation for the choice"},
                },
                "required": ["identifier", "category_code", "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["categorizations"],
    "additionalProperties": False,
}


def format_product_batch(products: list[dict]) -> str:
    """Format a batch of products for the user message."""
    lines = []
    for i, product in enumerate(products, 1):
        parts = [f"Product {i}:"]
        parts.append(f"  Identifier: {product['identifier']}")
        if product.get("name"):
            parts.append(f"  Naam: {product['name']}")
        if product.get("description"):
            desc = product["description"][:500]  # Limit description length
            parts.append(f"  Beschrijving: {desc}")
        if product.get("brand"):
            parts.append(f"  Merk: {product['brand']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def categorize_products(
    products: list[dict],
    categories: list[Category],
    api_key: str,
    model: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback=None,
) -> list[dict]:
    """Categorize all products using Claude API in batches.

    Args:
        products: List of product dicts with identifier, name, description, brand.
        categories: List of Category objects.
        api_key: Anthropic API key.
        model: Model ID to use.
        batch_size: Number of products per API call.
        progress_callback: Optional callback(current, total) for progress updates.

    Returns:
        List of categorization result dicts.
    """
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(categories)
    valid_codes = {cat.code for cat in categories}

    all_results = []
    total_batches = (len(products) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(products))
        batch = products[start:end]

        user_message = f"Categoriseer deze {len(batch)} producten:\n\n{format_product_batch(batch)}"

        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )

            result_text = response.content[0].text
            parsed = json.loads(result_text)
            batch_results = parsed.get("categorizations", [])

            # Validate category codes
            for result in batch_results:
                if result.get("category_code") not in valid_codes:
                    result["confidence"] = "low"
                    result["reasoning"] = (
                        f"(Onbekende categorie code: {result.get('category_code')}) "
                        + result.get("reasoning", "")
                    )

            all_results.extend(batch_results)

        except anthropic.APIError as e:
            # On API error, mark all products in batch as failed
            for product in batch:
                all_results.append(
                    {
                        "identifier": product["identifier"],
                        "category_code": "",
                        "confidence": "low",
                        "reasoning": f"API fout: {str(e)}",
                    }
                )

        except (json.JSONDecodeError, KeyError) as e:
            for product in batch:
                all_results.append(
                    {
                        "identifier": product["identifier"],
                        "category_code": "",
                        "confidence": "low",
                        "reasoning": f"Parse fout: {str(e)}",
                    }
                )

        if progress_callback:
            progress_callback(batch_idx + 1, total_batches)

        # Delay between batches to avoid rate limiting
        if batch_idx < total_batches - 1:
            time.sleep(BATCH_DELAY_SECONDS)

    return all_results
