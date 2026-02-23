"""Hybride Producten Zoeker - Streamlit web app.

Tool voor Foodvalley / The Protein Community om supermarktproducten te vinden
die zowel plantaardige als dierlijke eiwitbronnen bevatten.
"""

import io
import streamlit as st
import pandas as pd

from db import get_stats, search_products
from ingredients import PLANTAARDIG, DIERLIJK

st.set_page_config(
    page_title="Hybride Producten Zoeker",
    page_icon="🔬",
    layout="wide",
)

st.title("Hybride Producten Zoeker")
st.markdown(
    "Vind supermarktproducten die **zowel plantaardige als dierlijke** "
    "eiwitbronnen bevatten."
)

# --- Sidebar filters ---
st.sidebar.header("Filters")

# Statistieken ophalen
stats = get_stats()

# Supermarkt filter
supermarkten = list(stats["per_supermarkt"].keys())
geselecteerde_supermarkten = st.sidebar.multiselect(
    "Supermarkten",
    options=supermarkten,
    default=supermarkten,
    help="Selecteer welke supermarkten je wilt doorzoeken",
)

# Alleen hybride producten
alleen_hybride = st.sidebar.checkbox(
    "Alleen hybride producten",
    value=True,
    help="Toon alleen producten met zowel plantaardige als dierlijke ingrediënten",
)

# Zoekterm
zoekterm = st.sidebar.text_input(
    "Zoekterm",
    placeholder="bijv. hamburger, gehakt...",
    help="Zoek in productnaam of ingrediëntenlijst",
)

# Plantaardige ingrediënten filter
st.sidebar.subheader("Plantaardige ingrediënten")
plantaardig_groepen = st.sidebar.multiselect(
    "Filter op plantaardig ingrediënt",
    options=sorted(PLANTAARDIG.keys()),
    help="Laat leeg om alle plantaardige ingrediënten te tonen",
)

# Dierlijke ingrediënten filter
st.sidebar.subheader("Dierlijke ingrediënten")
dierlijk_groepen = st.sidebar.multiselect(
    "Filter op dierlijk ingrediënt",
    options=sorted(DIERLIJK.keys()),
    help="Laat leeg om alle dierlijke ingrediënten te tonen",
)

# --- Dashboard statistieken ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Totaal producten", stats["totaal_producten"])
col2.metric("Met ingrediënten", stats["met_ingredienten"])
col3.metric("Hybride producten", stats["hybride_producten"])
col4.metric("Supermarkten", len(stats["per_supermarkt"]))

# Per supermarkt tabel
if stats["per_supermarkt"]:
    with st.expander("Producten per supermarkt"):
        for sm, count in stats["per_supermarkt"].items():
            st.write(f"**{sm.capitalize()}**: {count} producten")

# --- Zoekresultaten ---
st.divider()

results = search_products(
    supermarkets=geselecteerde_supermarkten or None,
    plantaardig_groepen=plantaardig_groepen or None,
    dierlijk_groepen=dierlijk_groepen or None,
    alleen_hybride=alleen_hybride,
    zoekterm=zoekterm or None,
)

st.subheader(f"Resultaten ({len(results)} producten)")

if not results:
    st.info(
        "Geen producten gevonden. Pas de filters aan of draai eerst een scraper "
        "via `python run.py`."
    )
else:
    # Bouw DataFrame voor weergave en export
    rows = []
    for p in results:
        rows.append({
            "Supermarkt": p["supermarket"].capitalize(),
            "Product": p["name"],
            "Categorie": p.get("category", ""),
            "Plantaardig": ", ".join(p.get("matches_plantaardig", [])),
            "Dierlijk": ", ".join(p.get("matches_dierlijk", [])),
            "Ingrediënten": p.get("ingredients_raw", ""),
            "URL": p.get("url", ""),
        })

    df = pd.DataFrame(rows)

    # Export knop
    col_export1, col_export2, _ = st.columns([1, 1, 4])

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    col_export1.download_button(
        label="Download Excel",
        data=buffer.getvalue(),
        file_name="hybride_producten.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    csv_data = df.to_csv(index=False).encode("utf-8")
    col_export2.download_button(
        label="Download CSV",
        data=csv_data,
        file_name="hybride_producten.csv",
        mime="text/csv",
    )

    # Tabel weergave
    st.dataframe(
        df[["Supermarkt", "Product", "Categorie", "Plantaardig", "Dierlijk"]],
        use_container_width=True,
        hide_index=True,
    )

    # Detail weergave per product
    st.divider()
    st.subheader("Productdetails")

    for i, p in enumerate(results):
        with st.expander(
            f"{p['supermarket'].capitalize()} — {p['name']}"
        ):
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**Plantaardige ingrediënten:**")
                if p.get("matches_plantaardig"):
                    for m in p["matches_plantaardig"]:
                        st.write(f"- 🌱 {m}")
                else:
                    st.write("Geen gevonden")

            with col_b:
                st.markdown("**Dierlijke ingrediënten:**")
                if p.get("matches_dierlijk"):
                    for m in p["matches_dierlijk"]:
                        st.write(f"- 🥩 {m}")
                else:
                    st.write("Geen gevonden")

            if p.get("category"):
                st.write(f"**Categorie:** {p['category']}")
            if p.get("url"):
                st.write(f"**Link:** {p['url']}")

            if p.get("ingredients_raw"):
                st.markdown("**Volledige ingrediëntenlijst:**")
                st.text(p["ingredients_raw"])
