"""
ASOS Scraper via RapidAPI
Uses the working API from yesterday
"""
import requests
import json
import time
import os

RAPIDAPI_KEY = "6b07df1199mshac1029ebcab9bf5p1fd595jsn07fabec323e5"
RAPIDAPI_HOST = "asos2.p.rapidapi.com"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST
}

# Categories to scrape with ASOS category IDs
CATEGORIES = {
    'tops': {'asos_id': 4169, 'category': 'top', 'limit': 500},
    'tshirts': {'asos_id': 4718, 'category': 'top', 'limit': 300},
    'skirts': {'asos_id': 2639, 'category': 'skirt', 'limit': 400},
    'trousers': {'asos_id': 4246, 'category': 'bottom', 'limit': 400},
    'jeans': {'asos_id': 3630, 'category': 'bottom', 'limit': 400},
    'dresses': {'asos_id': 8799, 'category': 'dress', 'limit': 400},
    'jackets': {'asos_id': 2641, 'category': 'jacket', 'limit': 400},
    'coats': {'asos_id': 2640, 'category': 'coat', 'limit': 200},
    'shoes': {'asos_id': 4172, 'category': 'shoes', 'limit': 400},
    'trainers': {'asos_id': 6456, 'category': 'shoes', 'limit': 300},
    'boots': {'asos_id': 6455, 'category': 'shoes', 'limit': 200},
    'heels': {'asos_id': 6461, 'category': 'shoes', 'limit': 200},
    'bags': {'asos_id': 8730, 'category': 'bag', 'limit': 400},
    'sunglasses': {'asos_id': 6519, 'category': 'sunglasses', 'limit': 200},
    'jewellery': {'asos_id': 5034, 'category': 'accessory', 'limit': 200},
}


def fetch_category(cat_name: str, cat_info: dict) -> list:
    """Fetch products from ASOS via RapidAPI"""
    
    asos_id = cat_info['asos_id']
    our_category = cat_info['category']
    limit = cat_info['limit']
    
    url = "https://asos2.p.rapidapi.com/products/v2/list"
    
    products = []
    offset = 0
    batch_size = 48
    
    print(f"\n📦 Fetching {cat_name} (→ {our_category}, limit: {limit})...")
    
    while len(products) < limit:
        params = {
            "store": "US",
            "offset": str(offset),
            "categoryId": str(asos_id),
            "limit": str(batch_size),
            "country": "US",
            "sort": "freshness",
            "currency": "USD",
            "sizeSchema": "US",
            "lang": "en-US"
        }
        
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=30)
            
            if response.status_code == 429:
                print(f"   ⚠️ Rate limited! Waiting 60s...")
                time.sleep(60)
                continue
            
            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}: {response.text[:200]}")
                break
            
            data = response.json()
            items = data.get('products', [])
            
            if not items:
                print(f"   No more products at offset {offset}")
                break
            
            for item in items:
                if len(products) >= limit:
                    break
                
                image_url = item.get('imageUrl', '')
                if image_url and not image_url.startswith('http'):
                    image_url = f"https://{image_url}"
                
                product = {
                    'id': f"asos_{item.get('id', '')}",
                    'name': item.get('name', ''),
                    'brand': item.get('brandName', ''),
                    'price': item.get('price', {}).get('current', {}).get('value', 0),
                    'category': our_category,
                    'subcategory': cat_name,
                    'color': item.get('colour', ''),
                    'image_url': image_url,
                    'product_url': f"https://www.asos.com/{item.get('url', '')}",
                    'asos_id': item.get('id'),
                }
                
                if product['name'] and product['image_url']:
                    products.append(product)
            
            print(f"   {len(products)}/{limit} products...", end='\r')
            offset += batch_size
            
            # Rate limiting - be gentle
            time.sleep(1.0)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            time.sleep(5)
            continue
    
    print(f"   ✅ Got {len(products)} {cat_name} products")
    return products


def main():
    all_products = []
    
    print("="*60)
    print("ASOS RapidAPI Scraper")
    print("="*60)
    
    total_target = sum(c['limit'] for c in CATEGORIES.values())
    print(f"Target: ~{total_target} products across {len(CATEGORIES)} categories")
    
    for cat_name, cat_info in CATEGORIES.items():
        products = fetch_category(cat_name, cat_info)
        all_products.extend(products)
        
        # Save progress after each category
        with open('asos_products_full.json', 'w') as f:
            json.dump(all_products, f, indent=2)
        
        # Summary
        from collections import Counter
        cats = Counter(p['category'] for p in all_products)
        print(f"\n📊 Total: {len(all_products)} products")
        print(f"   By category: {dict(cats)}")
        print("-"*40)
        
        # Pause between categories
        time.sleep(2)
    
    # Final summary
    print("\n" + "="*60)
    print("SCRAPING COMPLETE")
    print("="*60)
    print(f"Total: {len(all_products)} products")
    print(f"Saved to: asos_products_full.json")


if __name__ == "__main__":
    main()
