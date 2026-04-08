"""
debug_amazon.py  —  uses plain Selenium with anti-detection patches (no uc)
Run: python debug_amazon.py
"""
import time, re, subprocess, glob, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup as bs


def get_driver():
    raw = ChromeDriverManager().install()
    if os.path.basename(raw) == "chromedriver" and os.access(raw, os.X_OK):
        path = raw
    else:
        candidates = glob.glob(os.path.join(os.path.dirname(raw), "**/chromedriver"), recursive=True)
        path = next((p for p in candidates if os.access(p, os.X_OK)), raw)

    options = Options()
    # Anti-detection without uc
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )
    # Run visibly so Mac ARM doesn't crash
    # options.add_argument("--headless=new")  # uncomment on Linux

    driver = webdriver.Chrome(service=Service(path), options=options)
    # Patch navigator.webdriver to False
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    })
    driver.implicitly_wait(10)
    return driver


def main():
    print("Starting Chrome (visible — Mac ARM requirement)...")
    driver = get_driver()

    url = "https://www.amazon.in/dp/B08WPM5D99"
    print(f"Loading: {url}")
    driver.get(url)
    time.sleep(5)

    with open("amazon_product_debug.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("Saved: amazon_product_debug.html")

    html = bs(driver.page_source, "lxml")

    print("\n--- Links containing 'review' ---")
    for a in html.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if "review" in href.lower() or "review" in text.lower():
            print(f"  {text[:50]!r:52s}  {href[:80]}")

    print("\n--- data-hook values on page ---")
    hooks = sorted({el["data-hook"] for el in html.find_all(attrs={"data-hook": True})})
    for h in hooks:
        print(f"  {h}")

    print("\n--- divs/spans with 'review' in class ---")
    for el in html.find_all(["div","span"], {"class": lambda c: c and "review" in " ".join(c).lower()}):
        print(f"  <{el.name} class={el.get('class')}> {el.get_text(strip=True)[:60]!r}")

    driver.quit()
    print("\nDone. Paste the output above back to Claude.")

if __name__ == "__main__":
    main()