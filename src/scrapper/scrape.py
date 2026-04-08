"""
src/scrapper/scrape.py  (Myntra)
Updated to inherit from BaseScraper for consistency.
"""
import sys
import time
import logging
import pandas as pd
from urllib.parse import quote
from tenacity import retry, stop_after_attempt, wait_fixed

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs

from src.scrapper.base_scraper import BaseScraper
from src.exception import CustomException

logger = logging.getLogger(__name__)


class ScrapeReviews(BaseScraper):

    PLATFORM = "Myntra"

    def __init__(self, product_name: str, no_of_products: int):
        super().__init__(product_name, no_of_products)
        self.product_title = ""
        self.product_price = "N/A"
        self.product_rating_value = "N/A"

    # ── URL scraping ────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def scrape_product_urls(self) -> list:
        try:
            search_string = self.product_name.replace(" ", "-")
            encoded_query = quote(self.product_name)
            url = f"https://www.myntra.com/{search_string}?rawQuery={encoded_query}"

            logger.info(f"[Myntra] Navigating to: {url}")
            self.driver.get(url)

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "results-base"))
            )

            html = bs(self.driver.page_source, "lxml")
            pclass = html.find_all("ul", {"class": "results-base"})
            product_urls = [
                a["href"]
                for ul in pclass
                for a in ul.find_all("a", href=True)
            ]
            logger.info(f"[Myntra] Found {len(product_urls)} product URLs.")
            return product_urls

        except Exception as e:
            logger.error(f"[Myntra] Error scraping URLs: {e}")
            raise CustomException(e, sys)

    # ── Product info ────────────────────────────────────────────────────

    def extract_reviews(self, product_link: str):
        """Load product page and return review anchor tag (or None)."""
        try:
            self.driver.get(f"https://www.myntra.com/{product_link}")
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "title"))
            )
            html = bs(self.driver.page_source, "lxml")

            title_tag = html.find("title")
            self.product_title = title_tag.text if title_tag else "Unknown"

            rating_div = html.find("div", {"class": "index-overallRating"})
            self.product_rating_value = (
                rating_div.find("div").text if rating_div else "N/A"
            )

            price_span = html.find("span", {"class": "pdp-price"})
            self.product_price = price_span.text if price_span else "N/A"

            review_link = html.find("a", {"class": "detailed-reviews-allReviews"})
            return review_link if review_link else None

        except Exception as e:
            raise CustomException(e, sys)

    # ── Review extraction ───────────────────────────────────────────────

    def extract_products(self, product_reviews) -> pd.DataFrame:
        try:
            review_url = "https://www.myntra.com" + product_reviews["href"]
            self.driver.get(review_url)
            self._scroll_to_bottom()

            html = bs(self.driver.page_source, "lxml")
            containers = html.find_all(
                "div", {"class": "detailed-reviews-userReviewsContainer"}
            )

            reviews = []
            for container in containers:
                user_ratings = container.find_all(
                    "div", {"class": "user-review-main user-review-showRating"}
                )
                user_comments = container.find_all(
                    "div", {"class": "user-review-reviewTextWrapper"}
                )
                user_names = container.find_all("div", {"class": "user-review-left"})

                for i in range(len(user_ratings)):
                    reviews.append({
                        "Product Name": self.product_title,
                        "Over_All_Rating": self.product_rating_value,
                        "Price": self.product_price,
                        "Date": self._safe_get(
                            user_names, i,
                            lambda el: el.find_all("span")[1].text, "No Date"
                        ),
                        "Rating": self._safe_get(
                            user_ratings, i,
                            lambda el: el.find("span", class_="user-review-starRating").get_text(strip=True),
                            "N/A"
                        ),
                        "Name": self._safe_get(
                            user_names, i,
                            lambda el: el.find("span").text, "Anonymous"
                        ),
                        "Comment": self._safe_get(
                            user_comments, i,
                            lambda el: el.get_text(strip=True), "No Comment"
                        ),
                    })
            return pd.DataFrame(reviews)

        except Exception as e:
            raise CustomException(e, sys)

    # ── Main method ─────────────────────────────────────────────────────

    def get_review_data(self) -> pd.DataFrame:
        try:
            urls = self.scrape_product_urls()
            if not urls:
                return pd.DataFrame()

            frames = []
            scraped, idx = 0, 0

            while scraped < self.no_of_products and idx < len(urls):
                url = urls[idx]
                idx += 1
                review_anchor = self.extract_reviews(url)
                if review_anchor:
                    df = self.extract_products(review_anchor)
                    if not df.empty:
                        frames.append(df)
                        scraped += 1
                        logger.info(f"[Myntra] Scraped product {scraped}/{self.no_of_products}.")

            self._safe_quit()
            return self._finalise(frames)

        except Exception as e:
            self._safe_quit()
            raise CustomException(e, sys)