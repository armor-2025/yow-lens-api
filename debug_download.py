import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Show browser
        context = await browser.new_context()
        page = await context.new_page()
        
        # Visit ASOS first
        print("Visiting ASOS...")
        await page.goto("https://www.asos.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Try to load an image
        url = "https://images.asos-media.com/products/asos-design-oversized-shirt-with-pockets-in-washed-denim-blue/209310476-1-washeddenimblue"
        print(f"Loading image: {url}")
        
        response = await page.goto(url, wait_until="load", timeout=15000)
        print(f"Status: {response.status if response else 'No response'}")
        print(f"OK: {response.ok if response else 'N/A'}")
        
        if response:
            content_type = response.headers.get('content-type', '')
            print(f"Content-Type: {content_type}")
            
            body = await response.body()
            print(f"Body size: {len(body)} bytes")
            
            if len(body) > 1000:
                with open("test_image.jpg", "wb") as f:
                    f.write(body)
                print("Saved to test_image.jpg")
        
        await asyncio.sleep(5)  # Keep browser open to see
        await browser.close()

asyncio.run(test())
