"""Configuration constants for the Akeneo Auto-Categorization Tool."""

# Claude API settings
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
AVAILABLE_MODELS = {
    "Claude Haiku 4.5 (Snel & Goedkoop)": "claude-haiku-4-5-20251001",
    "Claude Sonnet 4.6 (Gebalanceerd)": "claude-sonnet-4-6-20250514",
    "Claude Opus 4.6 (Meest Capabel)": "claude-opus-4-6-20250514",
}
DEFAULT_BATCH_SIZE = 10
MAX_TOKENS = 4096
BATCH_DELAY_SECONDS = 0.5

# Column detection patterns (case-insensitive)
IDENTIFIER_PATTERNS = ["sku", "identifier", "id", "artikelnummer", "product_id", "code"]
NAME_PATTERNS = ["name", "naam", "title", "titel", "product_name", "productnaam", "label"]
DESCRIPTION_PATTERNS = ["description", "beschrijving", "omschrijving", "desc", "product_description"]
BRAND_PATTERNS = ["brand", "merk", "manufacturer", "fabrikant"]

# Akeneo export settings
AKENEO_IDENTIFIER_COLUMN = "identifier"
AKENEO_CATEGORIES_COLUMN = "categories"
