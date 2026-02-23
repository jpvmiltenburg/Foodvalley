"""Jumbo scraper via HTML scraping.

Jumbo's GraphQL API is beveiligd met Akamai, maar de HTML-pagina's zijn
toegankelijk. Strategie:
1. Crawl categoriepagina's om product-URLs te verzamelen
2. Haal per product de ingrediënten op van de productpagina
"""

import re
import json
import logging

from bs4 import BeautifulSoup

from .base import BaseScraper
from db import upsert_product, save_matches
from ingredients import find_matches

logger = logging.getLogger(__name__)

# Hoofdcategorieën op Jumbo die relevant zijn (bevatten voedsel)
CATEGORIES = [
    "aardappelen-groente-en-fruit",
    "vlees-vis-en-vega",
    "kaas-vleeswaren-en-tapas",
    "zuivel-eieren-en-boter",
    "brood-en-gebak",
    "ontbijt-broodbeleg-en-bakproducten",
    "pasta-rijst-en-wereldkeuken",
    "conserven-soepen-sauzen-en-olien",
    "diepvries",
    "snoep-koek-en-chips",
]


class JumboScraper(BaseScraper):
    """Scraper voor Jumbo producten via HTML scraping."""

    name = "jumbo"
    base_url = "https://www.jumbo.com"

    def _get_page(self, url: str) -> str:
        """Haal een HTML pagina op."""
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text

    def get_product_urls_from_category(self, category_slug: str) -> list[str]:
        """Haal alle product-URLs op uit een categoriepagina met paginering."""
        product_urls = set()
        start = 0
        page_size = 24

        while True:
            url = f"{self.base_url}/producten/{category_slug}/"
            if start > 0:
                url += f"?start={start}"

            try:
                html = self._get_page(url)
            except Exception as e:
                logger.warning("Fout bij ophalen %s: %s", url, e)
                break

            soup = BeautifulSoup(html, "html.parser")

            # Zoek productlinks via .title-link binnen product cards
            links_found = 0
            overview = soup.select_one('[data-testid="products-overview"]')
            container = overview or soup
            for a_tag in container.select(".title-link"):
                href = a_tag.get("href", "")
                if href and "/producten/" in href:
                    full_url = href if href.startswith("http") else self.base_url + href
                    product_urls.add(full_url)
                    links_found += 1

            if links_found == 0:
                break

            start += page_size
            self.rate_limit(0.5)

            # Veiligheidscheck: stop als we heel veel pagina's hebben
            if start > 2000:
                logger.warning("Meer dan 2000 producten in %s, stoppen", category_slug)
                break

        return list(product_urls)

    def get_product_detail(self, url: str) -> dict | None:
        """Haal productdetails en ingrediënten op van een productpagina."""
        try:
            html = self._get_page(url)
        except Exception as e:
            logger.warning("Fout bij ophalen product %s: %s", url, e)
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Naam en metadata uit JSON-LD
        name = ""
        category = ""
        ld_scripts = soup.select('script[type="application/ld+json"]')
        for script in ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "Product":
                    name = data.get("name", "")
                    category = data.get("category", "")
                    break
                # BreadcrumbList voor categorie
                if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
                    items = data.get("itemListElement", [])
                    if len(items) >= 2:
                        category = " > ".join(
                            item.get("name", "") for item in items[1:-1]
                        )
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: naam uit de <title> tag
        if not name:
            title_tag = soup.find("title")
            if title_tag:
                name = title_tag.text.split("|")[0].strip()

        # Ingrediënten
        ingredients_raw = ""
        ingredients_el = soup.select_one('[data-testid="ingredients-text-body"]')
        if ingredients_el:
            ingredients_raw = ingredients_el.get_text(strip=True)
        else:
            # Fallback: zoek een section/div met "Ingrediënten" als heading
            for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
                if "ingredi" in heading.get_text(strip=True).lower():
                    # Pak de volgende sibling of parent container
                    next_el = heading.find_next_sibling()
                    if next_el:
                        ingredients_raw = next_el.get_text(strip=True)
                    break

        return {
            "name": name,
            "category": category,
            "ingredients_raw": ingredients_raw,
            "url": url,
        }

    def scrape(self):
        """Scrape alle Jumbo producten."""
        logger.info("Start Jumbo scraper...")

        # Stap 1: Verzamel alle product-URLs per categorie
        all_urls = set()
        for cat_slug in CATEGORIES:
            urls = self.get_product_urls_from_category(cat_slug)
            all_urls.update(urls)
            logger.info("Categorie '%s': %d producten", cat_slug, len(urls))
            self.rate_limit(0.3)

        logger.info("Totaal unieke product-URLs: %d", len(all_urls))

        # Stap 2: Haal productdetails op
        saved = 0
        for i, url in enumerate(all_urls):
            if i % 50 == 0:
                logger.info("  Detail ophalen: %d/%d", i, len(all_urls))

            detail = self.get_product_detail(url)
            if not detail or not detail["name"]:
                continue

            product_id = upsert_product(
                supermarket=self.name,
                name=detail["name"],
                url=detail["url"],
                category=detail["category"],
                ingredients_raw=detail["ingredients_raw"],
            )

            if detail["ingredients_raw"]:
                matches = find_matches(detail["ingredients_raw"])
                save_matches(product_id, matches)

            saved += 1
            self.rate_limit(0.5)

        logger.info("Jumbo scraper klaar. %d producten opgeslagen.", saved)
        return saved
