#!/usr/bin/env python3
"""
Debug: show exactly what Goodreads returns for one book.
Run: python3 debug_goodreads.py
"""
import sys, json, re, random

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "-q"])
    import requests
    from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

# Test 1: ISBN direct
isbn = "9781631983016"   # Jamie Is Jamie
url1 = f"https://www.goodreads.com/book/isbn/{isbn}"
print(f"\n=== Test 1: ISBN lookup ===")
print(f"URL: {url1}")
r1 = s.get(url1, timeout=20, allow_redirects=True)
print(f"Status: {r1.status_code}")
print(f"Final URL: {r1.url}")
print(f"HTML length: {len(r1.text)}")
print(f"First 500 chars:\n{r1.text[:500]}")

# Check for rating in the response
soup1 = BeautifulSoup(r1.text, "html.parser")
for script in soup1.find_all("script", type="application/ld+json"):
    try:
        data = json.loads(script.string or "")
        if "aggregateRating" in data:
            print(f"\n✓ Found JSON-LD rating: {data['aggregateRating']}")
    except: pass

m = re.search(r'(\d\.\d{1,2})\s*avg rating', r1.text)
if m: print(f"✓ Found avg rating pattern: {m.group(0)}")

# Test 2: Search page
print(f"\n=== Test 2: Search ===")
url2 = "https://www.goodreads.com/search?q=Jabari+Jumps+Gaia+Cornwall&search_type=books"
r2 = s.get(url2, timeout=20)
print(f"Status: {r2.status_code}")
print(f"HTML length: {len(r2.text)}")
soup2 = BeautifulSoup(r2.text, "html.parser")
links = soup2.select("a[href*='/book/show/']")
print(f"Book links found: {len(links)}")
if links:
    print(f"First link: {links[0].get('href')} — text: {links[0].get_text(strip=True)[:60]}")

print("\nDone.")
