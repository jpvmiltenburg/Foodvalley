#!/usr/bin/env python3
import urllib.request
import ssl

ctx = ssl.create_default_context()

sites = [
    ("hoogvliet_home", "https://www.hoogvliet.com/"),
    ("spar_home", "https://www.spar.nl/"),
    ("plus_home", "https://www.plus.nl/"),
    ("ekoplaza_categories", "https://www.ekoplaza.nl/nl/categorieen"),
    ("ekoplaza_home", "https://www.ekoplaza.nl/"),
]

basedir = "/Users/jellevanmiltenburg/git/Foodvalley"

for name, url in sites:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        resp = urllib.request.urlopen(req, timeout=20, context=ctx)
        html = resp.read().decode("utf-8", errors="replace")

        outpath = f"{basedir}/{name}.html"
        with open(outpath, "w") as f:
            f.write(html)

        print(f"=== {name} ===")
        print(f"Status: {resp.status}")
        print(f"Size: {len(html)} bytes")
        print(f"URL: {resp.url}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        print(f"Server: {resp.headers.get('Server')}")
        print("Response Headers:")
        for k, v in resp.headers.items():
            print(f"  {k}: {v}")
        print(f"Saved to: {outpath}")
        print()
    except Exception as e:
        print(f"=== {name} === ERROR: {e}")
        import traceback
        traceback.print_exc()
        print()
