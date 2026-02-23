"""Base scraper class."""

import time
import logging

import requests

logger = logging.getLogger(__name__)


class BaseScraper:
    """Basis klasse voor alle supermarkt scrapers."""

    name: str = "base"
    base_url: str = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "nl-NL,nl;q=0.9",
        })

    def scrape(self):
        """Scrape alle producten. Te implementeren door subklassen."""
        raise NotImplementedError

    def rate_limit(self, seconds: float = 0.5):
        """Wacht even tussen requests om de server niet te belasten."""
        time.sleep(seconds)
