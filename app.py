"""Akeneo Auto-Categorization Tool - Streamlit UI."""

import streamlit as st
import pandas as pd

from category_manager import (
    parse_categories_from_csv,
    parse_categories_from_text,
    get_category_options,
)
from file_handler import prepare_products_for_categorization, read_product_file
from categorizer import categorize_products
from exporter import create_akeneo_export
from config import AVAILABLE_MODELS, DEFAULT_BATCH_SIZE, DEFAULT_MODEL

# Page config
st.set_page_config(
    page_title="Akeneo Categorisatie Tool",
    page_icon="📦",
    layout="wide",
)


# ── Cached helpers to avoid re-parsing on every rerun ──
@st.cache_data(show_spinner=False)
def cached_read_products(file_bytes: bytes, filename: str) -> pd.DataFrame:
    return read_product_file(file_bytes, filename)


@st.cache_data(show_spinner=False)
def cached_parse_categories_csv(file_bytes: bytes, filename: str):
    return parse_categories_from_csv(file_bytes, filename)


@st.cache_data(show_spinner=False)
def cached_parse_categories_text(text: str):
    return parse_categories_from_text(text)


@st.cache_data(show_spinner=False)
def cached_detect_columns(df_columns: tuple) -> dict:
    """Cache column detection based on column names (tuple for hashability)."""
    from config import IDENTIFIER_PATTERNS, NAME_PATTERNS, DESCRIPTION_PATTERNS, BRAND_PATTERNS
    columns_lower = {col.lower(): col for col in df_columns}

    def find_col(patterns):
        for p in patterns:
            if p in columns_lower:
                return columns_lower[p]
        for p in patterns:
            for cl, co in columns_lower.items():
                if p in cl:
                    return co
        return None

    return {
        "identifier": find_col(IDENTIFIER_PATTERNS),
        "name": find_col(NAME_PATTERNS),
        "description": find_col(DESCRIPTION_PATTERNS),
        "brand": find_col(BRAND_PATTERNS),
    }


# ── Initialise session state defaults ──
if "step" not in st.session_state:
    st.session_state["step"] = 1  # 1=upload, 2=categorise, 3=review


st.title("Akeneo Auto-Categorisatie Tool")
st.caption("Categoriseer producten automatisch met behulp van Claude AI")

# ──────────────────────────────────────────────
# SIDEBAR - Settings (always visible)
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Instellingen")

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        help="Je kunt een API key aanmaken op console.anthropic.com",
    )

    model_label = st.selectbox(
        "AI Model",
        options=list(AVAILABLE_MODELS.keys()),
        index=0,
        help="Haiku is snel en goedkoop, Opus is het meest capabel",
    )
    selected_model = AVAILABLE_MODELS[model_label]

    batch_size = st.slider(
        "Batch grootte",
        min_value=5,
        max_value=25,
        value=DEFAULT_BATCH_SIZE,
        help="Aantal producten per API call. Groter = sneller maar duurder per call.",
    )

    st.divider()

    # ── Category upload ──
    st.header("Categorieën")
    category_input_method = st.radio(
        "Hoe wil je categorieën invoeren?",
        ["Bestand uploaden", "Tekst plakken"],
        horizontal=True,
    )

    categories = st.session_state.get("categories")

    if category_input_method == "Bestand uploaden":
        cat_file = st.file_uploader(
            "Upload categorielijst",
            type=["csv", "xlsx", "xls", "txt"],
            help="CSV/Excel met code+label kolommen, of een tekstbestand met één categorie per regel",
        )
        if cat_file:
            try:
                file_bytes = cat_file.getvalue()
                if cat_file.name.endswith(".txt"):
                    text = file_bytes.decode("utf-8")
                    categories = cached_parse_categories_text(text)
                else:
                    categories = cached_parse_categories_csv(file_bytes, cat_file.name)
                st.session_state["categories"] = categories
            except Exception as e:
                st.error(f"Fout bij het lezen van categoriebestand: {e}")
    else:
        cat_text = st.text_area(
            "Plak je categorieën (één per regel)",
            height=200,
            placeholder="Electronics > Laptops\nElectronics > Smartphones\nClothing > Shirts\n...",
        )
        if cat_text.strip():
            try:
                categories = cached_parse_categories_text(cat_text)
                st.session_state["categories"] = categories
            except Exception as e:
                st.error(f"Fout bij het parsen van categorieën: {e}")

    if categories:
        st.success(f"{len(categories)} categorieën geladen")
        with st.expander("Categorieën bekijken"):
            cat_lines = "\n".join(f"{cat.code}: {cat.full_path}" for cat in categories)
            st.code(cat_lines, language=None)

# ──────────────────────────────────────────────
# MAIN AREA
# ──────────────────────────────────────────────

# ── Status overzicht ──
step = st.session_state["step"]
cols = st.columns(3)
labels = ["Upload Producten", "Categoriseren", "Review & Export"]
for i, (col, label) in enumerate(zip(cols, labels), 1):
    if i < step:
        col.success(f"**Stap {i}: {label}**")
    elif i == step:
        col.info(f"**Stap {i}: {label}**")
    else:
        col.markdown(f"**Stap {i}: {label}**")

st.divider()

# ══════════════════════════════════════════════
# STAP 1 — Upload producten
# ══════════════════════════════════════════════
st.header("1. Upload Producten")

product_file = st.file_uploader(
    "Upload je Akeneo productexport",
    type=["csv", "xlsx", "xls"],
    help="CSV of Excel bestand met productgegevens uit Akeneo",
)

if product_file:
    try:
        file_bytes = product_file.getvalue()
        df = cached_read_products(file_bytes, product_file.name)
        st.session_state["source_df"] = df
        st.session_state["filename"] = product_file.name

        st.success(f"{len(df)} producten geladen uit {product_file.name}")

        # Auto-detect columns (cached)
        detected = cached_detect_columns(tuple(df.columns))

        st.subheader("Kolom Mapping")
        st.caption("Controleer of de juiste kolommen zijn gedetecteerd en pas aan indien nodig.")

        col1, col2 = st.columns(2)
        all_columns = ["(niet geselecteerd)"] + list(df.columns)

        with col1:
            id_idx = all_columns.index(detected["identifier"]) if detected["identifier"] in all_columns else 0
            selected_id = st.selectbox("Identifier / SKU kolom", all_columns, index=id_idx)

            name_idx = all_columns.index(detected["name"]) if detected["name"] in all_columns else 0
            selected_name = st.selectbox("Product naam kolom", all_columns, index=name_idx)

        with col2:
            desc_idx = all_columns.index(detected["description"]) if detected["description"] in all_columns else 0
            selected_desc = st.selectbox("Beschrijving kolom", all_columns, index=desc_idx)

            brand_idx = all_columns.index(detected["brand"]) if detected["brand"] in all_columns else 0
            selected_brand = st.selectbox("Merk kolom", all_columns, index=brand_idx)

        column_mapping = {
            "identifier": selected_id if selected_id != "(niet geselecteerd)" else None,
            "name": selected_name if selected_name != "(niet geselecteerd)" else None,
            "description": selected_desc if selected_desc != "(niet geselecteerd)" else None,
            "brand": selected_brand if selected_brand != "(niet geselecteerd)" else None,
        }
        st.session_state["column_mapping"] = column_mapping

        with st.expander("Data preview (eerste 10 rijen)"):
            st.dataframe(df.head(10), use_container_width=True)

        # Advance step if ready
        if column_mapping.get("identifier") and st.session_state["step"] < 2:
            st.session_state["step"] = 2

    except Exception as e:
        st.error(f"Fout bij het lezen van bestand: {e}")


# ══════════════════════════════════════════════
# STAP 2 — Categoriseren
# ══════════════════════════════════════════════
if st.session_state["step"] >= 2:
    st.divider()
    st.header("2. Categoriseren")

    can_categorize = bool(
        api_key
        and st.session_state.get("categories")
        and st.session_state.get("source_df") is not None
        and st.session_state.get("column_mapping", {}).get("identifier")
    )

    if not can_categorize:
        missing = []
        if not api_key:
            missing.append("API key (sidebar)")
        if not st.session_state.get("categories"):
            missing.append("Categorieën (sidebar)")
        if st.session_state.get("source_df") is None:
            missing.append("Product bestand")
        elif not st.session_state.get("column_mapping", {}).get("identifier"):
            missing.append("Identifier kolom")
        st.info(f"Nog nodig: {', '.join(missing)}")

    if st.button("Start Categorisatie", disabled=not can_categorize, type="primary"):
        categories = st.session_state["categories"]
        df = st.session_state["source_df"]
        column_mapping = st.session_state["column_mapping"]

        products = prepare_products_for_categorization(df, column_mapping)

        if not products:
            st.error("Geen producten gevonden met een geldige identifier.")
        else:
            st.info(f"Categoriseren van {len(products)} producten in batches van {batch_size}...")

            progress_bar = st.progress(0, text="Bezig met categoriseren...")

            def update_progress(current, total):
                progress_bar.progress(current / total, text=f"Batch {current}/{total} verwerkt")

            try:
                results = categorize_products(
                    products=products,
                    categories=categories,
                    api_key=api_key,
                    model=selected_model,
                    batch_size=batch_size,
                    progress_callback=update_progress,
                )

                st.session_state["results"] = results
                st.session_state["step"] = 3
                progress_bar.progress(1.0, text="Categorisatie voltooid!")

                # Stats
                high = sum(1 for r in results if r.get("confidence") == "high")
                medium = sum(1 for r in results if r.get("confidence") == "medium")
                low = sum(1 for r in results if r.get("confidence") == "low")

                st.rerun()

            except Exception as e:
                st.error(f"Fout tijdens categorisatie: {e}")


@st.fragment
def review_and_export():
    """Stap 3 as a fragment — interactions here only rerun this section."""
    st.divider()
    st.header("3. Review & Export")

    results = st.session_state["results"]
    categories = st.session_state.get("categories", [])
    category_codes = [""] + [cat.code for cat in categories]
    code_to_path = {cat.code: cat.full_path for cat in categories}

    # Stats
    high = sum(1 for r in results if r.get("confidence") == "high")
    medium = sum(1 for r in results if r.get("confidence") == "medium")
    low = sum(1 for r in results if r.get("confidence") == "low")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal", len(results))
    c2.metric("Hoog vertrouwen", high)
    c3.metric("Gemiddeld", medium)
    c4.metric("Laag vertrouwen", low)

    # Build review DataFrame
    review_data = []
    for r in results:
        review_data.append(
            {
                "identifier": r.get("identifier", ""),
                "category_code": r.get("category_code", ""),
                "categorie": code_to_path.get(r.get("category_code", ""), r.get("category_code", "")),
                "confidence": r.get("confidence", ""),
                "redenering": r.get("reasoning", ""),
            }
        )

    review_df = pd.DataFrame(review_data)

    # Confidence filter
    filter_confidence = st.multiselect(
        "Filter op confidence",
        ["high", "medium", "low"],
        default=["high", "medium", "low"],
    )
    filtered_df = review_df[review_df["confidence"].isin(filter_confidence)]

    st.caption(f"{len(filtered_df)} van {len(review_df)} producten getoond")

    # Editable table
    edited_df = st.data_editor(
        filtered_df,
        column_config={
            "identifier": st.column_config.TextColumn("Identifier", disabled=True),
            "category_code": st.column_config.SelectboxColumn(
                "Category Code",
                options=category_codes,
                help="Selecteer de juiste categorie code",
            ),
            "categorie": st.column_config.TextColumn("Categorie Pad", disabled=True),
            "confidence": st.column_config.TextColumn("Confidence", disabled=True),
            "redenering": st.column_config.TextColumn("Redenering", disabled=True, width="large"),
        },
        use_container_width=True,
        num_rows="fixed",
        key="review_table",
    )

    # Merge edits back
    if edited_df is not None:
        edited_results = []
        for _, row in edited_df.iterrows():
            edited_results.append(
                {
                    "identifier": row["identifier"],
                    "category_code": row["category_code"],
                    "confidence": row["confidence"],
                    "reasoning": row["redenering"],
                }
            )
        result_map = {r["identifier"]: r for r in results}
        for er in edited_results:
            result_map[er["identifier"]] = er
        final_results = list(result_map.values())
    else:
        final_results = results

    # Export
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        include_context = st.checkbox(
            "Context kolommen toevoegen",
            value=True,
            help="Voeg productnaam, confidence en redenering toe als referentie",
        )

    if st.button("Genereer Akeneo Export", type="primary"):
        source_df = st.session_state["source_df"]
        column_mapping = st.session_state["column_mapping"]

        excel_bytes = create_akeneo_export(
            results=final_results,
            source_df=source_df,
            identifier_column=column_mapping["identifier"],
            include_context=include_context,
            name_column=column_mapping.get("name"),
        )

        st.download_button(
            label="Download Excel",
            data=excel_bytes,
            file_name="akeneo_categorisatie_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


# ══════════════════════════════════════════════
# STAP 3 — Review & Export
# ══════════════════════════════════════════════
if st.session_state["step"] >= 3 and st.session_state.get("results"):
    review_and_export()
elif st.session_state["step"] < 3:
    st.divider()
    st.header("3. Review & Export")
    st.info("Voer eerst stap 1 en 2 uit om resultaten te zien.")


if __name__ == "__main__":
    import sys
    from streamlit.web.cli import main

    sys.argv = ["streamlit", "run", __file__, "--server.headless", "true"]
    main()
