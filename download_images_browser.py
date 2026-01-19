"""
Download ASOS images using Playwright (real browser, non-headless)
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

async def download_images(products_dir: Path, limit: int = None):
    data_dir = products_dir / "data"
    images_dir = products_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    with open(data_dir / "products.json") as f:
        products = json.load(f)["products"]
    
    if limit:
        products = products[:limit]
    
    logger.info(f"Downloading {len(products)} images...")
    
    async with async_playwright() as p:
        # Launch with anti-detection settings
        browser = await p.chromium.launch(
            headless=False,  # Must be visible to avoid detection
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Remove webdriver property
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        # First visit ASOS to get cookies
        logger.info("Visiting ASOS to get cookies...")
        await page.goto("https://www.asos.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        success = 0
        failed = 0
        
        for i, product in enumerate(products):
            url = product.get("image_url", "")
            if not url:
                failed += 1
                continue
            
            filepath = images_dir / f"{product['id']}.jpg"
            
            if filepath.exists():
                success += 1
                continue
            
            try:
                response = await page.goto(url, wait_until="load", timeout=15000)
                
                if response:
                    body = await response.body()
                    
                    if len(body) > 1000:
                        with open(filepath, "wb") as f:
                            f.write(body)
                        success += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
            
            if (i + 1) % 50 == 0:
                logger.info(f"Progress: {i+1}/{len(products)} (✓ {success}, ✗ {failed})")
            
            await asyncio.sleep(0.1)
        
        await browser.close()
    
    logger.info(f"Done! {success} downloaded, {failed} failed")
    return success

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--products-dir", default="./asos_products")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    asyncio.run(download_images(Path(args.products_dir), args.limit))
