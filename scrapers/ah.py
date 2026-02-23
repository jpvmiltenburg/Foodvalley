"""Albert Heijn scraper via mobile API + product page scraping.

Strategie:
1. Haal een anoniem token op via de mobile-auth API.
2. Gebruik het token om categorieën en subcategorieën op te halen.
3. Zoek producten per subcategorie via de search API (max 100 per pagina).
4. Scrape de ingrediëntenlijst van de productpagina op ah.nl (de search API
   bevat geen ingrediënten, die staan alleen op de productpagina zelf).
"""

import re
import logging

from .base import BaseScraper
from db import upsert_product, save_matches
from ingredients import find_matches

logger = logging.getLogger(__name__)

AUTH_URL = "https://api.ah.nl/mobile-auth/v1/auth/token/anonymous"
SEARCH_URL = "https://api.ah.nl/mobile-services/product/search/v2"
CATEGORIES_URL = "https://api.ah.nl/mobile-services/v1/product-shelves/categories"
SUBCATEGORIES_URL = (
    "https://api.ah.nl/mobile-services/v1/product-shelves/categories/{category_id}/sub-categories"
)

PRODUCT_PAGE_URL = "https://www.ah.nl/producten/product/wi{webshop_id}"

# Regex om de ingrediëntenlijst uit de HTML te halen.
# De ingrediënten staan in een <span> direct na een <p> in een div met
# data-testid="pdp-ingredients-list".
INGREDIENTS_PATTERN = re.compile(
    r'data-testid="pdp-ingredients-list".*?<span>(.*?)</span>',
    re.DOTALL,
)

# Alternatief: soms staat de ruwe tekst zonder HTML-tags in een JSON-fragment
# in de pagina, bijv.  "...rundvlees, tomaat, ..."
INGREDIENTS_FALLBACK_PATTERN = re.compile(
    r'Ingredi[eë]nten:\s*(.+?)(?:\\n|</)',
    re.DOTALL,
)


class AHScraper(BaseScraper):
    """Scraper voor Albert Heijn (ah.nl) producten."""

    name = "ah"
    base_url = "https://www.ah.nl"

    def __init__(self):
        super().__init__()
        self._token = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self):
        """Haal een anoniem bearer token op."""
        resp = self.session.post(
            AUTH_URL,
            json={"clientId": "appie"},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Appie/8.22.3",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        logger.info(
            "AH anoniem token verkregen (verloopt over %d seconden)",
            data.get("expires_in", 0),
        )

    def _api_headers(self) -> dict:
        """Geef de headers terug die nodig zijn voor de mobile API."""
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "Appie/8.22.3",
            "x-application": "AHWEBSHOP",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def get_categories(self) -> list[dict]:
        """Haal de hoofdcategorieën op.

        Returns een lijst van dicts met 'id', 'name', 'slugifiedName'.
        Voorbeeld:
            [
                {"id": 9344, "name": "Vlees", "slugifiedName": "vlees"},
                {"id": 1355, "name": "Bakkerij", "slugifiedName": "bakkerij"},
                ...
            ]
        """
        resp = self.session.get(CATEGORIES_URL, headers=self._api_headers())
        resp.raise_for_status()
        return resp.json()

    def get_subcategories(self, category_id: int) -> list[dict]:
        """Haal subcategorieën op voor een hoofdcategorie.

        Returns een dict met 'parent' en 'children', waar children een
        lijst is van sub-categorie dicts met 'id', 'name', 'slugifiedName'.
        """
        url = SUBCATEGORIES_URL.format(category_id=category_id)
        resp = self.session.get(url, headers=self._api_headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("children", [])

    # ------------------------------------------------------------------
    # Product search
    # ------------------------------------------------------------------

    def search_products(
        self,
        query: str | None = None,
        taxonomy_id: int | None = None,
        page: int = 0,
        size: int = 100,
    ) -> dict:
        """Zoek producten via de mobile search API.

        Geeft een dict terug met:
            - 'page': {'size', 'totalElements', 'totalPages', 'number'}
            - 'products': lijst van productdicts
            - 'filters': beschikbare filters
            - 'links': paginatie-links

        Elk product bevat o.a.:
            webshopId, hqId, title, salesUnitSize, unitPriceDescription,
            images, priceBeforeBonus, mainCategory, subCategory, brand,
            nutriscore, descriptionHighlights, descriptionFull,
            propertyIcons, availableOnline, isBonus, ...

        NB: Ingrediënten staan NIET in de search resultaten.
        Gebruik get_product_ingredients() om die apart op te halen.
        """
        params = {
            "page": page,
            "size": size,
            "sortBy": "RELEVANCE",
        }
        if query:
            params["query"] = query
        if taxonomy_id:
            params["taxonomyId"] = taxonomy_id

        resp = self.session.get(
            SEARCH_URL, params=params, headers=self._api_headers()
        )
        resp.raise_for_status()
        return resp.json()

    def get_all_products_for_taxonomy(self, taxonomy_id: int) -> list[dict]:
        """Haal alle producten op voor een taxonomie-ID (subcategorie).

        Pagineert automatisch door alle resultaten.
        """
        all_products = []
        page = 0
        while True:
            data = self.search_products(taxonomy_id=taxonomy_id, page=page)
            products = data.get("products", [])
            all_products.extend(products)

            page_info = data.get("page", {})
            total_pages = page_info.get("totalPages", 1)
            if page + 1 >= total_pages:
                break
            page += 1
            self.rate_limit(0.3)

        return all_products

    # ------------------------------------------------------------------
    # Product detail (ingredients + nutrition)
    # ------------------------------------------------------------------

    def get_product_ingredients(self, webshop_id: int) -> str:
        """Haal de ingrediëntenlijst op van de productpagina.

        De AH mobile API bevat geen ingrediënten in de search resultaten.
        We moeten de productpagina op ah.nl bezoeken en de ingrediënten
        uit de HTML parsen.

        De pagina https://www.ah.nl/producten/product/wi{id} redirect
        automatisch (307) naar de volledige URL met slug.

        Returns de ruwe ingrediëntentekst, of een lege string als er
        geen ingrediënten gevonden worden.
        """
        url = PRODUCT_PAGE_URL.format(webshop_id=webshop_id)
        resp = self.session.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "nl-NL,nl;q=0.9",
            },
            allow_redirects=True,
        )
        if resp.status_code != 200:
            logger.warning(
                "Product pagina %s gaf status %d", url, resp.status_code
            )
            return ""

        html = resp.text

        # Probeer eerst het data-testid patroon (meest betrouwbaar)
        match = INGREDIENTS_PATTERN.search(html)
        if match:
            raw = match.group(1)
            # Strip HTML-tags uit de ingrediëntenlijst
            clean = re.sub(r"<[^>]+>", "", raw).strip()
            # Verwijder het label "Ingrediënten: " als dat er nog in staat
            clean = re.sub(r"^Ingredi[eë]nten:\s*", "", clean)
            return clean

        # Fallback: zoek in de ruwe tekst / JSON in de HTML
        match = INGREDIENTS_FALLBACK_PATTERN.search(html)
        if match:
            raw = match.group(1)
            clean = re.sub(r"<[^>]+>", "", raw).strip()
            return clean

        return ""

    # ------------------------------------------------------------------
    # Volledige scrape
    # ------------------------------------------------------------------

    def scrape(self):
        """Scrape alle AH producten met ingrediënten.

        Stappen:
        1. Authenticatie (anoniem token)
        2. Haal alle hoofdcategorieën op
        3. Haal per categorie de subcategorieën op
        4. Zoek per subcategorie alle producten
        5. Haal per product de ingrediënten op van de productpagina
        6. Sla op in de database en doe ingrediënt-matching
        """
        logger.info("Start AH scraper...")

        # Stap 1: Authenticatie
        self._authenticate()

        # Stap 2: Categorieën ophalen
        categories = self.get_categories()
        logger.info("Gevonden: %d hoofdcategorieën", len(categories))

        # Stap 3+4: Per subcategorie producten ophalen
        seen_webshop_ids = set()
        all_products = []

        for cat in categories:
            cat_name = cat["name"]
            cat_id = cat["id"]

            subcategories = self.get_subcategories(cat_id)
            logger.info(
                "Categorie '%s' (id=%d): %d subcategorieën",
                cat_name, cat_id, len(subcategories),
            )
            self.rate_limit(0.2)

            for subcat in subcategories:
                subcat_name = subcat["name"]
                subcat_id = subcat["id"]
                category_path = f"{cat_name} > {subcat_name}"

                products = self.get_all_products_for_taxonomy(subcat_id)
                new_count = 0
                for product in products:
                    wid = product["webshopId"]
                    if wid not in seen_webshop_ids:
                        seen_webshop_ids.add(wid)
                        product["_category_path"] = category_path
                        all_products.append(product)
                        new_count += 1

                logger.info(
                    "  %s: %d producten (%d nieuw)",
                    category_path, len(products), new_count,
                )
                self.rate_limit(0.3)

        logger.info(
            "Totaal unieke producten gevonden: %d", len(all_products)
        )

        # Stap 5+6: Ingrediënten ophalen en opslaan
        saved = 0
        for i, product in enumerate(all_products):
            if i % 50 == 0:
                logger.info(
                    "  Ingrediënten ophalen: %d/%d", i, len(all_products)
                )

            webshop_id = product["webshopId"]
            title = product.get("title", "")
            category = product.get("_category_path", "")
            product_url = (
                f"{self.base_url}/producten/product/wi{webshop_id}"
            )

            # Haal ingrediënten op
            ingredients_raw = self.get_product_ingredients(webshop_id)
            self.rate_limit(0.5)

            # Sla op in database
            product_id = upsert_product(
                supermarket=self.name,
                name=title,
                url=product_url,
                category=category,
                ingredients_raw=ingredients_raw,
            )

            if ingredients_raw:
                matches = find_matches(ingredients_raw)
                save_matches(product_id, matches)

            saved += 1

        logger.info("AH scraper klaar. %d producten opgeslagen.", saved)
        return saved
