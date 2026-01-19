"""
ASOS Scraper using Playwright browser automation
Extracts products by scrolling through category pages
"""
import asyncio
import json
import time
from playwright.async_api import async_playwright

CATEGORIES = {
    'tops': {'url': 'https://www.asos.com/women/tops/cat/?cid=4169', 'category': 'top', 'limit': 500},
    'tshirts': {'url': 'https://www.asos.com/women/tops/t-shirts-vests/cat/?cid=4718', 'category': 'top', 'limit': 300},
    'skirts': {'url': 'https://www.asos.com/women/skirts/cat/?cid=2639', 'category': 'skirt', 'limit': 400},
    'trousers': {'url': 'https://www.asos.com/women/trousers-leggings/cat/?cid=4246', 'category': 'bottom', 'limit': 400},
    'jeans': {'url': 'https://www.asos.com/women/jeans/cat/?cid=3630', 'category': 'bottom', 'limit': 400},
    'dresses': {'url': 'https://www.asos.com/women/dresses/cat/?cid=8799', 'category': 'dress', 'limit': 400},
    'jackets': {'url': 'https://www.asos.com/women/jackets-coats/cat/?cid=2641', 'category': 'jacket', 'limit': 400},
    'shoes': {'url': 'https://www.asos.com/women/shoes/cat/?cid=4172', 'category': 'shoes', 'limit': 400},
    'trainers': {'url': 'https://www.asos.com/women/shoes/trainers-sneakers/cat/?cid=6456', 'category': 'shoes', 'limit': 300},
    'bags': {'url': 'https://www.asos.com/women/accessories/bags-purses/cat/?cid=8730', 'category': 'bag', 'limit': 400},
    'sunglasses': {'url': 'https://www.asos.com/women/accessories/sunglasses/cat/?cid=6519', 'category': 'sunglasses', 'limit': 200},
    'jewellery': {'url': 'https://www.asos.com/women/accessories/jewellery/cat/?cid=5034', 'category': 'accessory', 'limit': 200},
}

async def scrape_category(page, cat_name, cat_info, all_products):
    """Scrape a single category by intercepting API calls"""
    
    url = cat_info['url']
    category = cat_info['category']
    limit = cat_info['limit']
    
    products = []
    
    print(f"\n{'='*60}")
    print(f"📦 Scraping {cat_name} → {category} (limit: {limit})")
    print(f"   URL: {url}")
    
    # Set up API response interception
    api_responses = []
    
    async def handle_response(response):
        if 'api/product/search' in response.url:
            try:
                data = await response.json()
                if 'products' in data:
                    api_responses.append(data['products'])
            except:
                pass
    
    page.on('response', handle_response)
    
    try:
        # Navigate to page
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Scroll to load more products
        scroll_count = 0
        max_scrolls = limit // 72 + 5  # ~72 products per page load
        
        while len(products) < limit and scroll_count < max_scrolls:
            # Scroll down
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)
            
            # Click "Load More" if present
            try:
                load_more = page.locator('text="Load more"')
                if await load_more.is_visible():
                    await load_more.click()
                    await page.wait_for_timeout(2000)
            except:
                pass
            
            # Process API responses
            for items in api_responses:
                for item in items:
                    product_id = f"asos_{item.get('id', '')}"
                    
                    # Skip duplicates
                    if any(p['id'] == product_id for p in products):
                        continue
                    
                    product = {
                        'id': product_id,
                        'name': item.get('name', ''),
                        'brand': item.get('brandName', ''),
                        'price': item.get('price', {}).get('current', {}).get('value', 0),
                        'category': category,
                        'subcategory': cat_name,
                        'color': item.get('colour', ''),
                        'image_url': f"https://{item.get('imageUrl', '')}" if item.get('imageUrl') else '',
                        'product_url': f"https://www.asos.com/{item.get('url', '')}",
                    }
                    
                    if product['name'] and product['image_url']:
                        products.append(product)
            
            api_responses.clear()
            scroll_count += 1
            
            print(f"   Scroll {scroll_count}: {len(products)} products", end='\r')
        
        print(f"\n   ✅ Got {len(products)} {cat_name} products")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    finally:
        page.remove_listener('response', handle_response)
    
    return products


async def main():
    all_products = []
    
    print("="*60)
    print("ASOS Browser Scraper")
    print("="*60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Show browser
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # First visit homepage to get cookies
        print("\n🌐 Visiting ASOS homepage first...")
        await page.goto('https://www.asos.com', wait_until='networkidle')
        await page.wait_for_timeout(3000)
        
        for cat_name, cat_info in CATEGORIES.items():
            products = await scrape_category(page, cat_name, cat_info, all_products)
            all_products.extend(products)
            
            # Save progress
            with open('asos_products_full.json', 'w') as f:
                json.dump(all_products, f, indent=2)
            
            # Summary
            from collections import Counter
            cats = Counter(p['category'] for p in all_products)
            print(f"\n📊 Total: {len(all_products)} products")
            print(f"   {dict(cats)}")
            
            # Delay between categories
            await page.wait_for_timeout(2000)
        
        await browser.close()
    
    # Final summary
    print("\n" + "="*60)
    print("SCRAPING COMPLETE")
    print("="*60)
    print(f"Total: {len(all_products)} products")
    
    from collections import Counter
    for cat, cnt in Counter(p['category'] for p in all_products).items():
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    asyncio.run(main())
