"""Dirk.nl scraper via GraphQL API."""

import logging

from .base import BaseScraper
from db import upsert_product, save_matches
from ingredients import find_matches

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://web-gateway.dirk.nl/graphql"


class DirkScraper(BaseScraper):
    name = "dirk"
    base_url = "https://www.dirk.nl"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Content-Type": "application/json",
        })

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        """Voer een GraphQL query uit."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self.session.post(GRAPHQL_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.warning("GraphQL errors: %s", data["errors"])
        return data.get("data", {})

    def get_categories(self) -> list[dict]:
        """Haal alle departments/webgroups/subgroups op."""
        data = self._gql("""
            {
                listDepartments {
                    departments {
                        id
                        description
                        webGroups {
                            webGroupId
                            description
                            webSubGroups {
                                webSubGroupId
                                description
                            }
                        }
                    }
                }
            }
        """)
        return data.get("listDepartments", {}).get("departments", [])

    def get_product_ids_for_subgroup(self, subgroup_id: int) -> list[int]:
        """Haal alle product IDs op voor een subgroep."""
        data = self._gql("""
            query($id: Int!) {
                listWebSubGroupProducts(webSubGroupId: $id) {
                    productIds
                }
            }
        """, {"id": subgroup_id})
        result = data.get("listWebSubGroupProducts", {})
        if result is None:
            return []
        product_ids = result.get("productIds") or []
        # productIds kan een lijst van lijsten zijn, flatten
        flat = []
        for item in product_ids:
            if isinstance(item, list):
                flat.extend(item)
            elif isinstance(item, int):
                flat.append(item)
        return flat

    def get_product_detail(self, product_id: int) -> dict | None:
        """Haal productdetails inclusief ingrediënten op."""
        data = self._gql("""
            query($id: Int!) {
                product(productId: $id) {
                    productId
                    headerText
                    brand
                    description
                    mainDescription
                    webgroup
                    declarations {
                        ingredients
                    }
                }
            }
        """, {"id": product_id})
        return data.get("product")

    def scrape(self):
        """Scrape alle Dirk producten."""
        logger.info("Start Dirk scraper...")

        # Stap 1: Haal categorieën op
        departments = self.get_categories()
        logger.info("Gevonden: %d departments", len(departments))

        # Stap 2: Verzamel alle product IDs per subgroep
        all_product_ids = set()
        subgroup_info = {}  # product_id -> category string

        for dept in departments:
            dept_name = dept["description"]
            for wg in dept.get("webGroups", []):
                wg_name = wg["description"]
                for sg in wg.get("webSubGroups", []):
                    sg_name = sg["description"]
                    sg_id = sg["webSubGroupId"]
                    category = f"{dept_name} > {wg_name} > {sg_name}"

                    product_ids = self.get_product_ids_for_subgroup(sg_id)
                    for pid in product_ids:
                        all_product_ids.add(pid)
                        subgroup_info[pid] = category

                    logger.info(
                        "  %s: %d producten", category, len(product_ids)
                    )
                    self.rate_limit(0.2)

        logger.info("Totaal unieke product IDs: %d", len(all_product_ids))

        # Stap 3: Haal productdetails op
        saved = 0
        for i, pid in enumerate(all_product_ids):
            if i % 100 == 0:
                logger.info("  Detail ophalen: %d/%d", i, len(all_product_ids))

            detail = self.get_product_detail(pid)
            if not detail:
                continue

            ingredients_raw = ""
            if detail.get("declarations") and detail["declarations"].get("ingredients"):
                ingredients_raw = detail["declarations"]["ingredients"]

            product_url = f"{self.base_url}/boodschappen/product/{pid}"
            category = subgroup_info.get(pid, detail.get("webgroup", ""))

            product_id = upsert_product(
                supermarket=self.name,
                name=detail.get("headerText", ""),
                url=product_url,
                category=category,
                ingredients_raw=ingredients_raw,
            )

            if ingredients_raw:
                matches = find_matches(ingredients_raw)
                save_matches(product_id, matches)

            saved += 1
            self.rate_limit(0.1)

        logger.info("Dirk scraper klaar. %d producten opgeslagen.", saved)
        return saved
