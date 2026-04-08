"""
debug_flipkart2.py — finds review structure by content, not class names
Run: python debug_flipkart2.py
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

    product_url = "https://www.flipkart.com/highlander-men-checkered-casual-multicolor-shirt/p/itm5d17c8f21bc9e"
    review_url  = product_url + "?aid=overall&certifiedBuyer=false&sortOrder=MOST_RECENT&page=1"

    print(f"Loading: {review_url}")
    driver.get(review_url)
    time.sleep(6)

    html = bs(driver.page_source, "lxml")

    # 1. Find divs containing a single digit 1-5 (star ratings)
    print("\n--- Divs whose direct text is a rating digit (1-5) ---")
    for el in html.find_all("div"):
        text = el.get_text(strip=True)
        if re.match(r'^[1-5](\.\d)?$', text) and el.get('class'):
            parent = el.parent
            gp     = parent.parent if parent else None
            print(f"  RATING el: <div class={el.get('class')}> text={text!r}")
            print(f"    parent:  <{parent.name} class={parent.get('class')}> text={parent.get_text(strip=True)[:80]!r}")
            if gp:
                print(f"    grandp:  <{gp.name} class={gp.get('class')}> text={gp.get_text(strip=True)[:80]!r}")
            print()

    # 2. Find elements with long text (likely review comments, >40 chars)
    print("\n--- Elements with long text (likely review comments) ---")
    count = 0
    for el in html.find_all(["p", "span", "div"]):
        text = el.get_text(strip=True)
        children = list(el.children)
        # Only leaf-ish elements with substantial text
        if 40 < len(text) < 500 and len([c for c in children if hasattr(c, 'get_text')]) <= 2:
            print(f"  <{el.name} class={el.get('class')}> {text[:100]!r}")
            count += 1
            if count >= 20:
                break

    # 3. Show the page title to confirm it loaded correctly
    print(f"\nPage title: {driver.title!r}")

    # 4. Count total divs on the page
    all_divs = html.find_all("div")
    print(f"Total divs: {len(all_divs)}")

    # 5. Print a sample section around where reviews would be
    print("\n--- Section of page HTML around 'Ratings & Reviews' ---")
    page_text = driver.page_source
    idx = page_text.lower().find("ratings")
    if idx > 0:
        print(page_text[idx:idx+3000])
    else:
        print("'Ratings' text not found in page source")

    driver.quit()
    print("\nDone.")

if __name__ == "__main__":
    main()