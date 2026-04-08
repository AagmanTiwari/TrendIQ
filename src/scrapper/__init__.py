"""
src/scrapper/__init__.py
Factory function — returns the right scraper for a given platform.

Usage:
    from src.scrapper import get_scraper
    scraper = get_scraper("amazon", product_name="blue jeans", no_of_products=3)
    df = scraper.get_review_data()
"""
from src.scrapper.scrape import ScrapeReviews
from src.scrapper.amazon_scraper import AmazonScraper
from src.scrapper.flipkart_scraper import FlipkartScraper
from src.scrapper.meesho_scraper import MeeshoScraper

SCRAPERS = {
    "myntra": ScrapeReviews,
    "amazon": AmazonScraper,
    "flipkart": FlipkartScraper,
    "meesho": MeeshoScraper,
}


def get_scraper(platform: str, product_name: str, no_of_products: int):
    """
    Return an initialised scraper for the requested platform.

    Args:
        platform: one of 'myntra', 'amazon', 'flipkart', 'meesho'
        product_name: search query string
        no_of_products: how many products to scrape

    Raises:
        ValueError: if platform is not supported
    """
    key = platform.strip().lower()
    cls = SCRAPERS.get(key)
    if cls is None:
        raise ValueError(
            f"Unsupported platform '{platform}'. "
            f"Choose from: {list(SCRAPERS.keys())}"
        )
    return cls(product_name=product_name, no_of_products=no_of_products)