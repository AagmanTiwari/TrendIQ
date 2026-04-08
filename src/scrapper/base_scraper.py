"""
src/scrapper/base_scraper.py
Drops undetected-chromedriver entirely (broken on Mac ARM M1/M2/M3).
Uses plain Selenium with CDP patches to remove automation fingerprints.
Chrome runs visibly on Mac ARM — this is required and cannot be avoided.
"""
import os
import re
import sys
import glob
import time
import logging
import platform
import subprocess
import pandas as pd
from abc import ABC, abstractmethod

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from src.exception import CustomException

logger = logging.getLogger(__name__)

STANDARD_COLUMNS = [
    "Platform", "Product Name", "Over_All_Rating",
    "Price", "Date", "Rating", "Name", "Comment",
]


def _is_mac_arm() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _real_chromedriver_path() -> str:
    raw = ChromeDriverManager().install()
    if os.path.basename(raw) == "chromedriver" and os.access(raw, os.X_OK):
        return raw
    candidates = glob.glob(
        os.path.join(os.path.dirname(raw), "**/chromedriver"), recursive=True
    )
    executables = [p for p in candidates if os.access(p, os.X_OK)]
    if executables:
        return executables[0]
    raise FileNotFoundError(f"chromedriver not found in {os.path.dirname(raw)}")


class BaseScraper(ABC):

    PLATFORM = "Unknown"

    def __init__(self, product_name: str, no_of_products: int):
        self.product_name = product_name
        self.no_of_products = no_of_products
        self.driver = self._init_driver()

    def _init_driver(self):
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-IN")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )

        mac_arm = _is_mac_arm()
        if not mac_arm:
            # Headless works fine on Linux/Windows
            options.add_argument("--headless=new")

        path = _real_chromedriver_path()
        driver = webdriver.Chrome(service=Service(path), options=options)

        # Patch navigator.webdriver → undefined (main bot-detection signal)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        })

        driver.implicitly_wait(10)
        logger.info(
            f"[{self.PLATFORM}] Chrome ready "
            f"({'visible' if mac_arm else 'headless'}, CDP anti-detection patched)."
        )
        return driver

    def _is_session_alive(self) -> bool:
        """Check if the Chrome session is still active."""
        try:
            _ = self.driver.title
            return True
        except Exception:
            return False

    def _ensure_driver(self):
        """Reinitialise driver if Chrome has crashed or session is dead."""
        if not self._is_session_alive():
            logger.warning(f"[{self.PLATFORM}] Session dead — reinitialising Chrome.")
            self._safe_quit()
            self.driver = self._init_driver()

    def _safe_quit(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def _scroll_to_bottom(self, pause: float = 2.0, max_scrolls: int = 10):
        last = self.driver.execute_script("return document.body.scrollHeight")
        for _ in range(max_scrolls):
            self.driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(pause)
            new = self.driver.execute_script("return document.body.scrollHeight")
            if new == last:
                break
            last = new

    def _human_delay(self, lo: float = 1.5, hi: float = 3.5):
        import random
        time.sleep(random.uniform(lo, hi))

    @staticmethod
    def _safe_get(lst, index, extractor, default="N/A"):
        try:
            return extractor(lst[index])
        except (IndexError, AttributeError, TypeError):
            return default

    @abstractmethod
    def scrape_product_urls(self) -> list: ...

    @abstractmethod
    def get_review_data(self) -> pd.DataFrame: ...

    def _finalise(self, frames: list) -> pd.DataFrame:
        if not frames:
            return pd.DataFrame(columns=STANDARD_COLUMNS)
        data = pd.concat(frames, axis=0, ignore_index=True)
        data["Platform"] = self.PLATFORM
        for col in STANDARD_COLUMNS:
            if col not in data.columns:
                data[col] = "N/A"
        data = data[STANDARD_COLUMNS]
        data.to_csv(f"data_{self.PLATFORM.lower()}.csv", index=False)
        logger.info(f"[{self.PLATFORM}] Saved {len(data)} reviews.")
        return data