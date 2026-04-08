"""
debug_flipkart.py — dumps Flipkart review page structure
Run: python debug_flipkart.py
"""
import time, glob, os, re
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
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(path), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    driver.implicitly_wait(10)
    return driver


def main():
    driver = get_driver()

    # Load a known Flipkart product with reviews
    product_url = "https://www.flipkart.com/highlander-men-checkered-casual-multicolor-shirt/p/itm5d17c8f21bc9e"
    review_url  = product_url + "?aid=overall&certifiedBuyer=false&sortOrder=MOST_RECENT&page=1"

    print(f"Loading review page: {review_url}")
    driver.get(review_url)
    time.sleep(5)

    # Dismiss login
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        btn = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'✕') or contains(text(),'×')]"))
        )
        btn.click()
        time.sleep(1)
        print("Dismissed login popup")
    except Exception:
        print("No login popup")

    with open("flipkart_review_debug.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("Saved: flipkart_review_debug.html")

    html = bs(driver.page_source, "lxml")

    print("\n--- divs with 'review' in class (first 30) ---")
    count = 0
    for el in html.find_all(["div","span","p"], {"class": lambda c: c and "review" in " ".join(c).lower()}):
        print(f"  <{el.name} class={el.get('class')}> {el.get_text(strip=True)[:80]!r}")
        count += 1
        if count >= 30:
            break

    print("\n--- divs with 'rating' in class (first 20) ---")
    count = 0
    for el in html.find_all(["div","span"], {"class": lambda c: c and "rating" in " ".join(c).lower()}):
        print(f"  <{el.name} class={el.get('class')}> {el.get_text(strip=True)[:60]!r}")
        count += 1
        if count >= 20:
            break

    print("\n--- Top-level divs containing star ratings (look for ★ or 'stars') ---")
    for el in html.find_all(["div","span"]):
        text = el.get_text(strip=True)
        if text and re.match(r'^[1-5]$', text) and el.get('class'):
            print(f"  <{el.name} class={el.get('class')}> text={text!r}")
            break

    print("\n--- Sample of all unique div classes on page (review-looking ones) ---")
    classes = set()
    for el in html.find_all("div", {"class": True}):
        for c in el.get("class", []):
            if any(k in c.lower() for k in ["review","rating","comment","user","star"]):
                classes.add(c)
    for c in sorted(classes):
        print(f"  {c}")

    driver.quit()
    print("\nDone.")

if __name__ == "__main__":
    main()