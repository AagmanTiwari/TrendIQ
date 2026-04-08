"""
src/scrapper/flipkart_scraper.py
Fix: detect dead Chrome session and auto-reinitialise driver.
     Use Selenium for everything — no requests (Flipkart blocks it).
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
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    InvalidSessionIdException, WebDriverException
)
from bs4 import BeautifulSoup as bs

from src.scrapper.base_scraper import BaseScraper
from src.exception import CustomException

logger = logging.getLogger(__name__)


class FlipkartScraper(BaseScraper):

    PLATFORM = "Flipkart"
    BASE_URL  = "https://www.flipkart.com"

    def __init__(self, product_name: str, no_of_products: int):
        super().__init__(product_name, no_of_products)
        self.product_title        = ""
        self.product_price        = "N/A"
        self.product_rating_value = "N/A"

    # ── session guard ──────────────────────────────────────────────────

    def _is_session_alive(self) -> bool:
        try:
            _ = self.driver.title
            return True
        except Exception:
            return False

    def _ensure_driver(self):
        """Reinitialise driver if Chrome has crashed."""
        if not self._is_session_alive():
            logger.warning("[Flipkart] Session dead — reinitialising Chrome.")
            self._safe_quit()
            self.driver = self._init_driver()

    def _dismiss_login(self):
        try:
            btn = WebDriverWait(self.driver, 4).until(
                EC.element_to_be_clickable(
                    (By.XPATH,
                     "//button[contains(text(),'✕') or contains(text(),'×')] | "
                     "//*[@class='_2KpZ6l _2doB4z']")
                )
            )
            btn.click()
            time.sleep(1)
        except Exception:
            pass

    def _safe_get(self, url: str, wait: float = 3.0) -> bool:
        """Navigate to URL, reinitialising driver if needed. Returns False if failed."""
        self._ensure_driver()
        try:
            self.driver.get(url)
            time.sleep(wait)
            self._dismiss_login()
            return True
        except Exception as e:
            logger.warning(f"[Flipkart] Navigation failed: {e}")
            return False

    # ── search ─────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(4))
    def scrape_product_urls(self) -> list:
        try:
            url = f"{self.BASE_URL}/search?q={quote(self.product_name)}&marketplace=FLIPKART"
            logger.info(f"[Flipkart] Searching: {url}")

            if not self._safe_get(url, wait=4):
                return []

            html = bs(self.driver.page_source, "lxml")
            urls = []
            for a in html.find_all("a", href=True):
                href = a["href"]
                if "/p/" in href and ("pid=" in href or "/p/itm" in href or "/p/it" in href):
                    if href.startswith("http"):
                        full = href
                    elif href.startswith("/"):
                        full = self.BASE_URL + href
                    else:
                        full = self.BASE_URL + "/" + href
                    clean = full.split("?")[0]
                    if "flipkart.com" in clean and clean not in urls:
                        urls.append(clean)

            logger.info(f"[Flipkart] Found {len(urls)} product URLs.")
            return urls

        except Exception as e:
            logger.error(f"[Flipkart] Search failed: {e}")
            raise CustomException(e, sys)

    # ── product page ───────────────────────────────────────────────────

    def _load_product(self, url: str) -> bool:
        if not self._safe_get(url, wait=4):
            return False

        html = bs(self.driver.page_source, "lxml")

        title_el = (
            html.find("span", {"class": "B_NuCI"}) or
            html.find("h1",   {"class": "yhB1nd"}) or
            html.find("span", {"class": "_35KyD6"}) or
            html.find("h1") or html.find("h2")
        )
        self.product_title = title_el.get_text(strip=True) if title_el else ""
        if not self.product_title:
            return False

        import re as _re

        # Price: find first standalone ₹NNN text leaf
        self.product_price = "N/A"
        for el in html.find_all(["div", "span"]):
            t = el.get_text(strip=True)
            if t.startswith("₹") and _re.match(r'^₹[\d,]+$', t):
                child_tags = [c for c in el.children if hasattr(c, "name") and c.name]
                if len(child_tags) == 0:
                    self.product_price = t
                    break

        # Overall rating from _1psv1zekr container (confirmed in debug)
        self.product_rating_value = "N/A"
        rating_container = html.find(
            "div", {"class": lambda c: c and "_1psv1zekr" in c}
        )
        if rating_container:
            for child in rating_container.find_all("div"):
                t = child.get_text(strip=True)
                if _re.match(r'^[1-5](\.[0-9])?$', t):
                    self.product_rating_value = t
                    break
        if self.product_rating_value == "N/A":
            for el in html.find_all("div", {"class": "css-g5y9jx"}):
                t = el.get_text(strip=True)
                if _re.match(r'^[1-5](\.[0-9])?$', t):
                    self.product_rating_value = t
                    break

        logger.info(
            f"[Flipkart] Product: '{self.product_title[:60]}' "
            f"| {self.product_price} | ⭐{self.product_rating_value}"
        )
        return True

    # ── review extraction ───────────────────────────────────────────────

    def _parse_reviews(self, html) -> list:
        import re as _re

        # New Flipkart structure (2025): obfuscated classes, identified by
        # the stable class combo _1psv1zee9 + _1psv1zel0 on the review card.
        # Each card contains:
        #   rating div  → class has _7dzyg26       e.g. text="5"
        #   title div   → class has _1psv1zefr     e.g. text="5Great product"  (rating+title merged)
        #   body spans  → longer text paragraphs below title
        #   reviewer    → text like "Name•Date"

        containers = html.find_all(
            "div",
            {"class": lambda c: c and "_1psv1zee9" in c and "_1psv1zel0" in c}
        )
        logger.info(f"[Flipkart] New-style containers found: {len(containers)}")

        # Fallback: old class names still used on some pages
        if not containers:
            containers = (
                html.find_all("div", {"class": "_27M-vq"}) or
                html.find_all("div", {"class": "col _2wzgFH"}) or
                html.find_all("div", {"class": "RcXBOT"})
            )
            logger.info(f"[Flipkart] Old-style containers found: {len(containers)}")

        reviews = []
        for div in containers:
            # Rating: div with _7dzyg26 in class
            rating_el = div.find(
                "div", {"class": lambda c: c and "_7dzyg26" in c}
            )
            rating = rating_el.get_text(strip=True) if rating_el else "N/A"
            # Validate it's actually a number
            if rating and not _re.match(r'^[1-5](\.\d)?$', rating):
                rating = "N/A"

            # Title: div with _1psv1zefr in class — text is "5Great product",
            # strip the leading digit to get just the title
            title_el = div.find(
                "div", {"class": lambda c: c and "_1psv1zefr" in c}
            )
            title_text = title_el.get_text(strip=True) if title_el else ""
            # Remove leading rating digit if present e.g. "5Great product" → "Great product"
            title_clean = _re.sub(r'^[1-5](\.[0-9])? ?', '', title_text).strip()

            # Comment body: find all text-heavy spans/divs that are NOT the title/rating
            comment_parts = []
            for el in div.find_all(["span", "div", "p"]):
                t = el.get_text(strip=True)
                # Skip short strings, the rating digit, and the title we already have
                if (len(t) > 15
                        and t != title_text
                        and t != rating
                        and not _re.match(r'^[1-5](\.[0-9])?$', t)
                        and t not in comment_parts):
                    # Only take leaf-ish elements
                    child_tags = [c for c in el.children if hasattr(c, 'name') and c.name]
                    if len(child_tags) <= 1:
                        comment_parts.append(t)

            # Use title as comment if no body found, otherwise use longest body part
            if comment_parts:
                comment = max(comment_parts, key=len)
            elif title_clean:
                comment = title_clean
            else:
                continue

            # Skip if comment is clearly navigation/UI noise
            if any(k in comment.lower() for k in ["flipkart", "add to cart", "wishlist", "buy now"]):
                continue

            reviews.append({
                "Product Name":    self.product_title,
                "Over_All_Rating": self.product_rating_value,
                "Price":           self.product_price,
                "Date":    "No Date",
                "Rating":  rating,
                "Name":    "Anonymous",
                "Comment": comment,
            })
        return reviews

    def _collect_reviews(self, product_url: str) -> list:
        all_reviews = []
        seen        = set()

        for page in range(1, 7):
            review_url = (
                f"{product_url}?aid=overall"
                f"&certifiedBuyer=false&sortOrder=MOST_RECENT&page={page}"
            )

            if not self._safe_get(review_url, wait=3):
                logger.warning(f"[Flipkart] Could not load review page {page}.")
                break

            html = bs(self.driver.page_source, "lxml")
            page_reviews = self._parse_reviews(html)
            logger.info(f"[Flipkart] Review page {page}: {len(page_reviews)} reviews.")

            new = 0
            for r in page_reviews:
                if r["Comment"] not in seen:
                    seen.add(r["Comment"])
                    all_reviews.append(r)
                    new += 1

            if new == 0:
                break

        return all_reviews

    # ── main ───────────────────────────────────────────────────────────

    def get_review_data(self) -> pd.DataFrame:
        try:
            urls = self.scrape_product_urls()
            if not urls:
                return pd.DataFrame()

            frames  = []
            scraped = 0
            idx     = 0

            while scraped < self.no_of_products and idx < len(urls):
                product_url = urls[idx]; idx += 1

                if not self._load_product(product_url):
                    logger.info(f"[Flipkart] Skipping {product_url}")
                    continue

                reviews = self._collect_reviews(product_url)
                logger.info(f"[Flipkart] Total reviews: {len(reviews)}")

                if reviews:
                    frames.append(pd.DataFrame(reviews))
                    scraped += 1
                    logger.info(f"[Flipkart] Done {scraped}/{self.no_of_products}.")
                else:
                    logger.info("[Flipkart] 0 reviews — trying next.")

            self._safe_quit()
            return self._finalise(frames)

        except Exception as e:
            self._safe_quit()
            raise CustomException(e, sys)