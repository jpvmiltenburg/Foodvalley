#!/usr/bin/env python3
"""Runner voor de supermarkt scrapers.

Gebruik:
    python run.py              # Draai alle scrapers
    python run.py dirk         # Draai alleen Dirk
    python run.py jumbo ah     # Draai Jumbo en AH
"""

import sys
import logging

from scrapers.dirk import DirkScraper
from scrapers.jumbo import JumboScraper
from scrapers.ah import AHScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("runner")

SCRAPERS = {
    "dirk": DirkScraper,
    "jumbo": JumboScraper,
    "ah": AHScraper,
}


def run_scraper(name: str):
    """Draai een enkele scraper."""
    if name not in SCRAPERS:
        logger.error("Onbekende scraper: %s (beschikbaar: %s)", name, ", ".join(SCRAPERS))
        return

    logger.info("=== Start %s scraper ===", name.upper())
    scraper = SCRAPERS[name]()
    try:
        count = scraper.scrape()
        logger.info("=== %s klaar: %d producten ===", name.upper(), count or 0)
    except Exception:
        logger.exception("Fout bij %s scraper", name)


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(SCRAPERS.keys())

    logger.info("Scrapers om te draaien: %s", ", ".join(targets))

    for name in targets:
        run_scraper(name)

    # Toon statistieken
    from db import get_stats
    stats = get_stats()
    logger.info("--- Statistieken ---")
    logger.info("Totaal producten: %d", stats["totaal_producten"])
    logger.info("Met ingrediënten: %d", stats["met_ingredienten"])
    logger.info("Hybride producten: %d", stats["hybride_producten"])
    for sm, cnt in stats["per_supermarkt"].items():
        logger.info("  %s: %d", sm, cnt)


if __name__ == "__main__":
    main()
