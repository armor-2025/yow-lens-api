"""
ASOS Full Category Scraper
Target: 10K+ products across all fashion categories
"""
import requests
import json
import time
import random
from pathlib import Path

# ASOS API endpoint
BASE_URL = "https://www.asos.com/api/product/search/v2/categories/{cat_id}"

# Categories with our internal category mapping
CATEGORIES = {
    # Tops
    'tops': {'asos_id': 4169, 'our_category': 'top', 'limit': 800},
    'tshirts': {'asos_id': 7616, 'our_category': 'top', 'limit': 400},
    'blouses': {'asos_id': 4335, 'our_category': 'top', 'limit': 300},
    'knitwear': {'asos_id': 5678, 'our_category': 'top', 'limit': 300},
    
    # Bottoms
    'trousers': {'asos_id': 4246, 'our_category': 'bottom', 'limit': 500},
    'jeans': {'asos_id': 3630, 'our_category': 'bottom', 'limit': 500},
    'skirts': {'asos_id': 2639, 'our_category': 'skirt', 'limit': 500},
    'shorts': {'asos_id': 9263, 'our_category': 'bottom', 'limit': 300},
    
    # Dresses
    'dresses': {'asos_id': 8799, 'our_category': 'dress', 'limit': 600},
    
    # Outerwear
    'jackets': {'asos_id': 2641, 'our_category': 'jacket', 'limit': 500},
    'coats': {'asos_id': 2640, 'our_category': 'coat', 'limit': 300},
    
    # Shoes
    'trainers': {'asos_id': 6456, 'our_category': 'shoes', 'limit': 400},
    'boots': {'asos_id': 4172, 'our_category': 'shoes', 'limit': 300},
    'heels': {'asos_id': 6461, 'our_category': 'shoes', 'limit': 300},
    'flat_shoes': {'asos_id': 4196, 'our_category': 'shoes', 'limit': 300},
    'sandals': {'asos_id': 6458, 'our_category': 'shoes', 'limit': 200},
    
    # Bags
    'bags': {'asos_id': 8730, 'our_category': 'bag', 'limit': 500},
    
    # Accessories
    'sunglasses': {'asos_id': 6519, 'our_category': 'sunglasses', 'limit': 300},
    'jewellery': {'asos_id': 5034, 'our_category': 'accessory', 'limit': 300},
    'belts': {'asos_id': 6448, 'our_category': 'accessory', 'limit': 200},
    'hats': {'asos_id': 6449, 'our_category': 'accessory', 'limit': 200},
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'application/json',
}

PARAMS_BASE = {
    'offset': 0,
    'limit': 72,
    'store': 'US',
    'lang': 'en-US',
    'currency': 'USD',
    'rowlength': 4,
    'channel': 'mobile-app',
    'country': 'US',
    'keyStoreDataversion': 'mhabj3s-41',
    'advertisementsPartnerId': '100712',
    'advertisementsVisitorId': 'null',
    'advertisementsOptInConsent': 'false',
}


def fetch_category(cat_name: str, cat_info: dict) -> list:
    """Fetch products from a single ASOS category"""
    asos_id = cat_info['asos_id']
    our_category = cat_info['our_category']
    limit = cat_info['limit']
    
    url = BASE_URL.format(cat_id=asos_id)
    products = []
    offset = 0
    
    print(f"\n📦 Fetching {cat_name} (ASOS:{asos_id} → {our_category})...")
    
    while len(products) < limit:
        params = PARAMS_BASE.copy()
        params['offset'] = offset
        
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=30)
            
            if response.status_code == 429:
                print(f"   ⚠️ Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            
            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                break
            
            data = response.json()
            items = data.get('products', [])
            
            if not items:
                print(f"   No more products at offset {offset}")
                break
            
            for item in items:
                if len(products) >= limit:
                    break
                    
                product = {
                    'id': f"asos_{item.get('id', '')}",
                    'name': item.get('name', ''),
                    'brand': item.get('brandName', ''),
                    'price': item.get('price', {}).get('current', {}).get('value', 0),
                    'category': our_category,
                    'subcategory': cat_name,
                    'color': item.get('colour', ''),
                    'image_url': f"https://{item.get('imageUrl', '')}",
                    'product_url': f"https://www.asos.com/{item.get('url', '')}",
                    'asos_id': item.get('id'),
                }
                products.append(product)
            
            print(f"   Fetched {len(products)}/{limit} products...")
            offset += 72
            
            # Random delay to avoid rate limiting
            time.sleep(random.uniform(1.5, 3.0))
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            time.sleep(5)
            continue
    
    print(f"   ✅ Got {len(products)} {cat_name} products")
    return products


def main():
    all_products = []
    
    print("="*60)
    print("ASOS Full Category Scraper")
    print("="*60)
    
    total_target = sum(c['limit'] for c in CATEGORIES.values())
    print(f"Target: {total_target} products across {len(CATEGORIES)} categories\n")
    
    for cat_name, cat_info in CATEGORIES.items():
        products = fetch_category(cat_name, cat_info)
        all_products.extend(products)
        
        # Save progress after each category
        with open('asos_products_full.json', 'w') as f:
            json.dump(all_products, f, indent=2)
        
        print(f"\n📊 Total so far: {len(all_products)} products")
        print("-"*40)
        
        # Longer delay between categories
        time.sleep(random.uniform(3, 5))
    
    # Final summary
    print("\n" + "="*60)
    print("SCRAPING COMPLETE")
    print("="*60)
    
    # Count by category
    from collections import Counter
    cat_counts = Counter(p['category'] for p in all_products)
    
    print(f"\nTotal products: {len(all_products)}")
    print("\nBy category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    print(f"\n✅ Saved to asos_products_full.json")


if __name__ == "__main__":
    main()
