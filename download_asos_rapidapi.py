"""
ASOS RapidAPI Scraper for YOW Lens Testing
==========================================

Downloads ~10K products from ASOS via RapidAPI, saves to JSON,
and optionally downloads images for embedding generation.

Usage:
    python download_asos_rapidapi.py --api-key YOUR_KEY --limit 10000
    python download_asos_rapidapi.py --api-key YOUR_KEY --limit 10000 --download-images
"""

import asyncio
import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import logging

import httpx
from PIL import Image
import io

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================

# RapidAPI endpoint (you've been using asos10.p.rapidapi.com)
BASE_URL = "https://asos10.p.rapidapi.com"

# Categories to scrape with search terms
# Each category will get ~equal share of the total limit
CATEGORIES = {
    # Women's
    "dresses": "dresses",
    "tops": "tops women",
    "blouses": "blouses",
    "jeans_women": "jeans women",
    "trousers_women": "trousers women",
    "skirts": "skirts",
    "jackets_women": "jackets women",
    "coats_women": "coats women",
    "knitwear_women": "sweaters women",
    "shoes_women": "shoes women",
    "heels": "heels",
    "boots_women": "boots women",
    "sneakers_women": "sneakers women",
    "bags": "bags women",
    
    # Men's
    "shirts_men": "shirts men",
    "tshirts_men": "t-shirts men",
    "jeans_men": "jeans men",
    "trousers_men": "trousers men",
    "jackets_men": "jackets men",
    "coats_men": "coats men",
    "knitwear_men": "sweaters men",
    "shoes_men": "shoes men",
    "sneakers_men": "sneakers men",
    "boots_men": "boots men",
}

# Map to normalized categories for YOW Lens
CATEGORY_MAPPING = {
    "dresses": ("dress", None),
    "tops": ("top", "blouse"),
    "blouses": ("top", "blouse"),
    "jeans_women": ("bottom", "jeans"),
    "jeans_men": ("bottom", "jeans"),
    "trousers_women": ("bottom", "trousers"),
    "trousers_men": ("bottom", "trousers"),
    "skirts": ("bottom", "skirt"),
    "jackets_women": ("jacket", None),
    "jackets_men": ("jacket", None),
    "coats_women": ("coat", None),
    "coats_men": ("coat", None),
    "knitwear_women": ("top", "sweater"),
    "knitwear_men": ("top", "sweater"),
    "shirts_men": ("top", "shirt"),
    "tshirts_men": ("top", "tshirt"),
    "shoes_women": ("shoes", None),
    "shoes_men": ("shoes", None),
    "heels": ("shoes", "heels"),
    "boots_women": ("shoes", "boots"),
    "boots_men": ("shoes", "boots"),
    "sneakers_women": ("shoes", "sneakers"),
    "sneakers_men": ("shoes", "sneakers"),
    "bags": ("bag", None),
}

@dataclass
class Product:
    """Normalized product structure"""
    id: str
    external_id: str
    name: str
    brand: str
    price: float
    sale_price: Optional[float]
    currency: str
    retailer: str
    product_url: str
    image_url: str
    additional_images: List[str]
    category: str
    subcategory: Optional[str]
    color: Optional[str]
    gender: Optional[str]
    is_selling_fast: bool
    raw_category: str

# ============================================================
# ASOS API Client
# ============================================================

class ASOSClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "asos10.p.rapidapi.com"
        }
        self.requests_made = 0
        self.rate_limit_delay = 0.5  # seconds between requests
    
    async def search_products(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        country: str = "US",
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """Search for products"""
        
        url = f"{BASE_URL}/api/v1/getProductListBySearchTerm"
        
        params = {
            "searchTerm": query,
            "limit": min(limit, 50),  # API max is 50 per request
            "offset": offset,
            "country": country,
            "currency": currency,
            "store": country,
            "sizeSchema": country,
            "languageShort": "en",
            "sort": "freshness"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers, params=params)
            self.requests_made += 1
            response.raise_for_status()
            
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
            
            result = response.json()
            
            # API wraps response in "data" object
            if isinstance(result, dict) and "data" in result:
                return result["data"]
            return result
    
    async def fetch_category(
        self,
        category_key: str,
        search_term: str,
        max_products: int = 500,
        country: str = "US",
        currency: str = "USD"
    ) -> List[Dict]:
        """Fetch all products for a category (paginated)"""
        
        all_products = []
        offset = 0
        batch_size = 50  # API max
        
        logger.info(f"  Fetching {category_key}: '{search_term}' (max {max_products})")
        
        while len(all_products) < max_products:
            try:
                result = await self.search_products(
                    query=search_term,
                    limit=batch_size,
                    offset=offset,
                    country=country,
                    currency=currency
                )
                
                products = result.get("products", [])
                
                if not products:
                    break
                
                # Add category key to each product
                for p in products:
                    p["_category_key"] = category_key
                    p["_gender"] = "women" if "women" in search_term or category_key in [
                        "dresses", "skirts", "heels", "blouses"
                    ] else "men" if "men" in search_term else "unisex"
                
                all_products.extend(products)
                offset += batch_size
                
                logger.info(f"    Got {len(products)} products (total: {len(all_products)})")
                
                # Stop if we got fewer than requested (end of results)
                if len(products) < batch_size:
                    break
                    
            except Exception as e:
                logger.error(f"    Error fetching {category_key} at offset {offset}: {e}")
                break
        
        return all_products[:max_products]

# ============================================================
# Product Formatter
# ============================================================

def format_product(raw: Dict, category_key: str) -> Optional[Product]:
    """Convert raw ASOS API response to Product"""
    
    try:
        product_id = raw.get("id")
        if not product_id:
            return None
        
        # Get price
        price_data = raw.get("price", {})
        current_price = price_data.get("current", {}).get("value")
        previous_price = price_data.get("previous", {}).get("value")
        
        if not current_price:
            return None
        
        # Get image URL (add https:// prefix)
        image_url = raw.get("imageUrl", "")
        if image_url and not image_url.startswith("http"):
            image_url = f"https://{image_url}"
        
        if not image_url:
            return None
        
        # Get additional images
        additional_images = []
        for img in raw.get("additionalImageUrls", []):
            if img and not img.startswith("http"):
                img = f"https://{img}"
            additional_images.append(img)
        
        # Get product URL
        product_url = raw.get("url", "")
        if product_url and not product_url.startswith("http"):
            product_url = f"https://www.asos.com/{product_url}"
        
        # Map category
        category, subcategory = CATEGORY_MAPPING.get(category_key, ("other", None))
        
        return Product(
            id=f"asos_{product_id}",
            external_id=str(product_id),
            name=raw.get("name", ""),
            brand=raw.get("brandName", "ASOS"),
            price=current_price,
            sale_price=previous_price if previous_price and previous_price != current_price else None,
            currency=price_data.get("currency", "USD"),
            retailer="asos",
            product_url=product_url,
            image_url=image_url,
            additional_images=additional_images,
            category=category,
            subcategory=subcategory,
            color=raw.get("colour"),
            gender=raw.get("_gender", "unisex"),
            is_selling_fast=raw.get("isSellingFast", False),
            raw_category=category_key
        )
        
    except Exception as e:
        logger.debug(f"Failed to format product: {e}")
        return None

# ============================================================
# Image Downloader
# ============================================================

class ImageDownloader:
    def __init__(self, images_dir: Path, max_concurrent: int = 10):
        self.images_dir = images_dir
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.stats = {'success': 0, 'failed': 0}
    
    async def download_image(self, product: Product, client: httpx.AsyncClient) -> Optional[Path]:
        """Download a single product image"""
        async with self.semaphore:
            try:
                filename = f"{product.id}.jpg"
                filepath = self.images_dir / filename
                
                # Skip if already exists
                if filepath.exists():
                    self.stats['success'] += 1
                    return filepath
                
                # Download
                response = await client.get(product.image_url)
                response.raise_for_status()
                
                # Validate it's an image
                img = Image.open(io.BytesIO(response.content))
                
                # Convert to RGB and save as JPEG
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(filepath, 'JPEG', quality=85)
                
                self.stats['success'] += 1
                return filepath
                
            except Exception as e:
                self.stats['failed'] += 1
                logger.debug(f"Failed to download {product.image_url}: {e}")
                return None
    
    async def download_all(self, products: List[Product]) -> dict:
        """Download all product images"""
        logger.info(f"Downloading images for {len(products)} products...")
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            tasks = [self.download_image(p, client) for p in products]
            
            # Process in batches for progress reporting
            batch_size = 100
            
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                await asyncio.gather(*batch, return_exceptions=True)
                
                logger.info(f"  Progress: {min(i + batch_size, len(products))}/{len(products)} "
                           f"(✓ {self.stats['success']}, ✗ {self.stats['failed']})")
        
        logger.info(f"Image download complete: {self.stats['success']} success, {self.stats['failed']} failed")
        return self.stats

# ============================================================
# Main Scraper
# ============================================================

async def scrape_asos(
    api_key: str,
    output_dir: Path,
    total_limit: int = 10000,
    download_images: bool = False,
    country: str = "US",
    currency: str = "USD"
):
    """Main scraping function"""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    client = ASOSClient(api_key)
    
    # Calculate products per category
    num_categories = len(CATEGORIES)
    products_per_category = total_limit // num_categories
    
    logger.info(f"Scraping ~{total_limit} products across {num_categories} categories")
    logger.info(f"~{products_per_category} products per category")
    logger.info("="*60)
    
    # Fetch all categories
    all_raw_products = []
    
    for category_key, search_term in CATEGORIES.items():
        products = await client.fetch_category(
            category_key=category_key,
            search_term=search_term,
            max_products=products_per_category,
            country=country,
            currency=currency
        )
        all_raw_products.extend(products)
        
        logger.info(f"  ✅ {category_key}: {len(products)} products")
    
    logger.info("="*60)
    logger.info(f"Total raw products: {len(all_raw_products)}")
    logger.info(f"API requests made: {client.requests_made}")
    
    # Format products
    logger.info("\nFormatting products...")
    formatted_products = []
    
    for raw in all_raw_products:
        product = format_product(raw, raw.get("_category_key", "other"))
        if product:
            formatted_products.append(product)
    
    # Deduplicate by ID
    seen_ids = set()
    unique_products = []
    for p in formatted_products:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique_products.append(p)
    
    logger.info(f"Unique products after deduplication: {len(unique_products)}")
    
    # Save products to JSON
    products_file = data_dir / "products.json"
    
    output_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "count": len(unique_products),
            "retailer": "asos",
            "source": "rapidapi",
            "api_requests": client.requests_made
        },
        "products": [asdict(p) for p in unique_products]
    }
    
    with open(products_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"Saved {len(unique_products)} products to {products_file}")
    
    # Category breakdown
    logger.info("\n📊 Category breakdown:")
    category_counts = {}
    for p in unique_products:
        cat = p.category
        category_counts[cat] = category_counts.get(cat, 0) + 1
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {count}")
    
    # Download images if requested
    if download_images:
        images_dir = output_dir / "images"
        downloader = ImageDownloader(images_dir)
        await downloader.download_all(unique_products)
    
    # Summary
    print("\n" + "="*60)
    print("ASOS SCRAPE COMPLETE")
    print("="*60)
    print(f"Products scraped: {len(unique_products)}")
    print(f"API requests: {client.requests_made}")
    print(f"Output directory: {output_dir.absolute()}")
    print(f"  - data/products.json")
    if download_images:
        print(f"  - images/ ({downloader.stats['success']} images)")
    print("\nNext steps:")
    print("  1. python generate_embeddings.py --products-dir ./asos_products")
    print("  2. python load_to_postgres.py --products-dir ./asos_products --db-url '...'")
    print("="*60)
    
    return unique_products

# ============================================================
# CLI
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description='Scrape ASOS products via RapidAPI')
    parser.add_argument('--api-key', type=str, help='RapidAPI key (or set RAPIDAPI_KEY env var)')
    parser.add_argument('--limit', type=int, default=10000, help='Total products to scrape')
    parser.add_argument('--output-dir', type=str, default='./asos_products', help='Output directory')
    parser.add_argument('--download-images', action='store_true', help='Also download product images')
    parser.add_argument('--country', type=str, default='US', help='Country code (US, UK, etc)')
    parser.add_argument('--currency', type=str, default='USD', help='Currency (USD, GBP, etc)')
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.environ.get('RAPIDAPI_KEY')
    if not api_key:
        print("Error: Must provide --api-key or set RAPIDAPI_KEY environment variable")
        return
    
    await scrape_asos(
        api_key=api_key,
        output_dir=Path(args.output_dir),
        total_limit=args.limit,
        download_images=args.download_images,
        country=args.country,
        currency=args.currency
    )

if __name__ == "__main__":
    asyncio.run(main())
