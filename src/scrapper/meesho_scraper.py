"""
src/scrapper/meesho_scraper.py
Meesho uses Akamai bot protection that blocks both plain requests and Selenium
(even real Chrome) without residential proxies or a logged-in session.
This scraper returns an empty DataFrame with a clear message.
"""
import sys
import logging
import pandas as pd
from urllib.parse import quote

from src.scrapper.base_scraper import BaseScraper
from src.exception import CustomException

logger = logging.getLogger(__name__)


class MeeshoScraper(BaseScraper):

    PLATFORM = "Meesho"
    BASE_URL  = "https://meesho.com"

    BLOCKED_MESSAGE = (
        "Meesho uses Akamai bot protection that blocks automated scraping "
        "(both plain HTTP requests and real Chrome via Selenium). "
        "Scraping Meesho reliably requires residential proxies or a logged-in browser session. "
        "This platform is currently not supported."
    )

    def __init__(self, product_name: str, no_of_products: int):
        super().__init__(product_name, no_of_products)

    def scrape_product_urls(self) -> list:
        return []

    def get_review_data(self) -> pd.DataFrame:
        logger.warning(f"[Meesho] {self.BLOCKED_MESSAGE}")
        self._safe_quit()
        return pd.DataFrame()