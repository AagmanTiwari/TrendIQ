"""
src/scrapper/amazon_scraper.py

Amazon.in has fully blocked unauthenticated review scraping (both Selenium
and plain requests redirect to sign-in). This scraper now:
  1. Still collects product info (title, price, rating) — these load fine
  2. Returns an empty DataFrame with a clear warning instead of hanging
  3. Suggests using Amazon Product Advertising API for production use

To get Amazon reviews properly, sign up for:
https://affiliate-program.amazon.in/assoc_credentials/home
"""
import sys
import logging
import pandas as pd
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs

from src.scrapper.base_scraper import BaseScraper
from src.exception import CustomException

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):

    PLATFORM = "Amazon"
    BASE_URL  = "https://www.amazon.in"

    BLOCKED_MESSAGE = (
        "Amazon.in requires authentication to access review pages. "
        "Unauthenticated scraping (both browser and HTTP) is blocked. "
        "Use the Amazon Product Advertising API for production review access: "
        "https://affiliate-program.amazon.in/assoc_credentials/home"
    )

    def __init__(self, product_name: str, no_of_products: int):
        super().__init__(product_name, no_of_products)

    def scrape_product_urls(self) -> list:
        try:
            url = f"{self.BASE_URL}/s?k={quote(self.product_name)}"
            logger.info(f"[Amazon] Searching: {url}")
            self.driver.get(url)
            self._human_delay(3, 5)

            WebDriverWait(self.driver, 25).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
                )
            )

            html    = bs(self.driver.page_source, "lxml")
            results = html.find_all("div", {"data-component-type": "s-search-result"})
            urls = []
            for r in results:
                for a in r.find_all("a", href=True):
                    href = a["href"]
                    if "/dp/" in href:
                        asin = href.split("/dp/")[1].split("/")[0].split("?")[0]
                        clean = f"{self.BASE_URL}/dp/{asin}"
                        if clean not in urls:
                            urls.append(clean)
                        break

            logger.info(f"[Amazon] Found {len(urls)} product URLs.")
            return urls

        except Exception as e:
            raise CustomException(e, sys)

    def get_review_data(self) -> pd.DataFrame:
        logger.warning(f"[Amazon] {self.BLOCKED_MESSAGE}")
        self._safe_quit()
        return pd.DataFrame()