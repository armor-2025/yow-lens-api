"""
YOW - Import 1000 ASOS Products to Vision API Product Search
=============================================================
Fetches products from ASOS RapidAPI and imports them for visual search testing.

Usage:
    python import_1000_asos.py

Requirements:
    - RAPIDAPI_KEY environment variable set
    - Google Cloud credentials set up (run setup_vision_search.py first)

Project: Your Online Wardrobe
Project ID: gen-lang-client-0930631788
"""

import os
import sys
import json
import time
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
PROJECT_ID = "gen-lang-client-0930631788"
LOCATION = "us-east1"
PRODUCT_SET_ID = "yow-asos-products"
BUCKET_NAME = f"{PROJECT_ID}-product-images"

# ASOS API Configuration
ASOS_BASE_URL = "https://asos2.p.rapidapi.com"

# Set credentials
CREDENTIALS_PATH = os.path.expanduser("~/yow-vision-key.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH


@dataclass
class ASOSProduct:
    """Represents an ASOS product"""
    product_id: str
    name: str
    image_url: str
    color: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    gender: Optional[str] = None
    
    def to_labels(self) -> Dict[str, str]:
        """Convert product attributes to Vision API labels"""
        labels = {}
        if self.color:
            labels["color"] = self.color.lower()[:128]  # Vision API limit
        if self.category:
            labels["category"] = self.category.lower()[:128]
        if self.subcategory:
            labels["subcategory"] = self.subcategory.lower()[:128]
        if self.brand:
            labels["brand"] = self.brand.lower()[:128]
        if self.gender:
            labels["gender"] = self.gender.lower()[:128]
        return labels


class ASOSFetcher:
    """Fetches products from ASOS RapidAPI"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "asos2.p.rapidapi.com"
        }
        self.requests_made = 0
    
    def search_products(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        country: str = "US",
        currency: str = "USD",
        sort: str = "freshness"
    ) -> Dict[str, Any]:
        """Search ASOS for products"""
        url = f"{ASOS_BASE_URL}/products/v2/list"
        params = {
            "store": country,
            "offset": offset,
            "limit": min(limit, 50),  # API max is 50
            "country": country,
            "currency": currency,
            "sort": sort,
            "q": query,
            "lang": "en-US",
            "sizeSchema": country
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        self.requests_made += 1
        response.raise_for_status()
        return response.json()
    
    def fetch_category_products(
        self,
        category_id: int,
        limit: int = 50,
        offset: int = 0,
        country: str = "US"
    ) -> Dict[str, Any]:
        """Fetch products by category ID"""
        url = f"{ASOS_BASE_URL}/products/v2/list"
        params = {
            "store": country,
            "offset": offset,
            "categoryId": category_id,
            "limit": min(limit, 50),
            "country": country,
            "currency": "USD",
            "sort": "freshness",
            "lang": "en-US"
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        self.requests_made += 1
        response.raise_for_status()
        return response.json()
    
    def parse_product(self, item: Dict, gender: str = "women") -> Optional[ASOSProduct]:
        """Parse ASOS API response into ASOSProduct"""
        try:
            # Check if item is actually a dict
            if not isinstance(item, dict):
                print(f"⚠️ Item is not a dict: {type(item)}")
                return None
            
            # Get image URL
            image_url = item.get("imageUrl", "")
            if image_url and not image_url.startswith("http"):
                image_url = f"https://{image_url}"
            
            if not image_url:
                return None
            
            # Get price
            price_data = item.get("price", {})
            if isinstance(price_data, dict):
                current_price = price_data.get("current", {})
                price = current_price.get("value", 0) if isinstance(current_price, dict) else 0
            else:
                price = 0
            
            # Extract color from name or use colour field
            name = item.get("name", "")
            color = item.get("colour", "")  # ASOS uses British spelling
            if not color:
                # Try to extract color from name
                common_colors = ["black", "white", "blue", "red", "green", "pink", 
                               "yellow", "orange", "purple", "brown", "grey", "gray",
                               "navy", "cream", "beige", "nude", "silver", "gold",
                               "khaki", "olive", "burgundy", "coral", "teal", "mint"]
                name_lower = name.lower()
                for c in common_colors:
                    if c in name_lower:
                        color = c
                        break
            
            # Extract category from name (productType is just "Product" string)
            category = "clothing"
            name_lower = name.lower()
            if "dress" in name_lower:
                category = "dresses"
            elif "top" in name_lower or "blouse" in name_lower or "shirt" in name_lower:
                category = "tops"
            elif "jean" in name_lower or "trouser" in name_lower or "pant" in name_lower:
                category = "bottoms"
            elif "jacket" in name_lower or "coat" in name_lower or "blazer" in name_lower:
                category = "outerwear"
            elif "skirt" in name_lower:
                category = "skirts"
            elif "shoe" in name_lower or "sneaker" in name_lower or "boot" in name_lower or "heel" in name_lower:
                category = "shoes"
            elif "bag" in name_lower or "purse" in name_lower:
                category = "bags"
            elif "sweater" in name_lower or "jumper" in name_lower or "cardigan" in name_lower:
                category = "knitwear"
            
            return ASOSProduct(
                product_id=f"asos_{item.get('id', '')}",
                name=name,
                image_url=image_url,
                color=color or "multicolor",
                category=category,
                subcategory=category,
                brand=item.get("brandName", "ASOS"),
                price=price,
                gender=gender
            )
        except Exception as e:
            print(f"⚠️ Failed to parse product: {e}")
            return None
    
    def fetch_products(self, target_count: int = 1000) -> List[ASOSProduct]:
        """
        Fetch products from multiple categories to get diverse results.
        
        Args:
            target_count: Target number of products to fetch
        
        Returns:
            List of ASOSProduct objects
        """
        products = []
        seen_ids = set()
        
        # Search queries to get diverse products
        search_queries = [
            # Women's clothing
            ("dresses", "women"),
            ("tops", "women"),
            ("jeans", "women"),
            ("skirts", "women"),
            ("jackets", "women"),
            ("coats", "women"),
            ("blouses", "women"),
            ("sweaters", "women"),
            ("shorts", "women"),
            ("jumpsuits", "women"),
            # Men's clothing
            ("shirts", "men"),
            ("t-shirts", "men"),
            ("jeans", "men"),
            ("jackets", "men"),
            ("suits", "men"),
            ("sweaters", "men"),
            ("shorts", "men"),
            ("coats", "men"),
            # Accessories
            ("bags", "women"),
            ("shoes", "women"),
            ("sneakers", "men"),
            ("boots", "women"),
            # More women's
            ("midi dress", "women"),
            ("maxi dress", "women"),
            ("mini dress", "women"),
            ("blazer", "women"),
            ("cardigan", "women"),
        ]
        
        products_per_query = (target_count // len(search_queries)) + 20
        
        print(f"\n📥 Fetching ~{target_count} products from ASOS...")
        print(f"   Using {len(search_queries)} search queries")
        print(f"   ~{products_per_query} products per query\n")
        
        for query, gender in search_queries:
            if len(products) >= target_count:
                break
            
            print(f"🔍 Searching: '{query}' ({gender})...")
            
            offset = 0
            query_products = 0
            
            while query_products < products_per_query and len(products) < target_count:
                try:
                    data = self.search_products(
                        query=query,
                        limit=50,
                        offset=offset
                    )
                    
                    items = data.get("products", [])
                    if not items:
                        break
                    
                    for item in items:
                        product = self.parse_product(item, gender)
                        if product and product.product_id not in seen_ids:
                            products.append(product)
                            seen_ids.add(product.product_id)
                            query_products += 1
                    
                    offset += 50
                    time.sleep(0.3)  # Rate limiting
                    
                except Exception as e:
                    print(f"   ⚠️ Error fetching {query}: {e}")
                    break
            
            print(f"   ✅ Got {query_products} products (Total: {len(products)})")
        
        print(f"\n📦 Total products fetched: {len(products)}")
        print(f"📊 API requests made: {self.requests_made}")
        
        return products[:target_count]


class VisionProductImporter:
    """Imports products into Vision API Product Search"""
    
    def __init__(self):
        """Initialize the importer"""
        from google.cloud import storage
        from vision_product_search import VisionProductSearch
        
        self.storage_client = storage.Client()
        self.vision_search = VisionProductSearch()
        self.bucket = self.storage_client.bucket(BUCKET_NAME)
        
        # Ensure bucket exists
        if not self.bucket.exists():
            print(f"❌ Bucket {BUCKET_NAME} does not exist!")
            print("   Run setup_vision_search.py first")
            sys.exit(1)
        
        print(f"✅ VisionProductImporter initialized")
        print(f"   Bucket: gs://{BUCKET_NAME}")
    
    def download_and_upload_image(
        self, 
        image_url: str, 
        product_id: str,
        max_retries: int = 3
    ) -> Optional[str]:
        """Download image and upload to Cloud Storage with retries"""
        import time
        
        for attempt in range(max_retries):
            try:
                # Add small delay to avoid rate limiting
                time.sleep(0.2)
                
                # Download image with longer timeout
                response = requests.get(
                    image_url, 
                    timeout=60,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()
                
                # Determine file extension
                content_type = response.headers.get('content-type', 'image/jpeg')
                ext = 'jpg' if 'jpeg' in content_type else 'png' if 'png' in content_type else 'jpg'
                
                # Upload to GCS
                blob_name = f"products/{product_id}.{ext}"
                blob = self.bucket.blob(blob_name)
                blob.upload_from_string(
                    response.content,
                    content_type=content_type
                )
                
                return f"gs://{BUCKET_NAME}/{blob_name}"
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    print(f"⚠️ Failed to upload image for {product_id}: {e}")
                    return None
        
        return None
    
    def import_single_product(self, product: ASOSProduct) -> bool:
        """Import a single product to Vision API"""
        try:
            # Upload image to Cloud Storage
            gcs_uri = self.download_and_upload_image(
                product.image_url, 
                product.product_id
            )
            
            if not gcs_uri:
                return False
            
            # Add product to Vision API
            self.vision_search.add_product(
                product_id=product.product_id,
                display_name=product.name[:128],  # Vision API limit
                labels=product.to_labels(),
                description=f"ASOS {product.category or 'Fashion'} - {product.name}"[:4096]
            )
            
            # Add reference image
            self.vision_search.add_reference_image(
                product_id=product.product_id,
                gcs_uri=gcs_uri,
                reference_image_id=f"img_{product.product_id}"
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to import {product.product_id}: {e}")
            return False
    
    def import_products(
        self, 
        products: List[ASOSProduct],
        max_workers: int = 5
    ) -> Dict[str, int]:
        """Import multiple products in parallel"""
        print(f"\n📤 Importing {len(products)} products to Vision API...")
        print(f"   Using {max_workers} parallel workers")
        
        success_count = 0
        failure_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.import_single_product, product): product
                for product in products
            }
            
            for i, future in enumerate(as_completed(futures)):
                product = futures[future]
                try:
                    if future.result():
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    failure_count += 1
                
                # Progress update every 50 products
                if (i + 1) % 50 == 0:
                    print(f"   Progress: {i + 1}/{len(products)} "
                          f"(✅ {success_count} / ❌ {failure_count})")
        
        return {
            "success": success_count,
            "failed": failure_count,
            "total": len(products)
        }


def save_products_json(products: List[ASOSProduct], filepath: str):
    """Save products to JSON file for reference"""
    data = []
    for p in products:
        data.append({
            "product_id": p.product_id,
            "name": p.name,
            "image_url": p.image_url,
            "color": p.color,
            "category": p.category,
            "subcategory": p.subcategory,
            "brand": p.brand,
            "price": p.price,
            "gender": p.gender
        })
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"💾 Products saved to: {filepath}")


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     YOW - Import 1000 ASOS Products                       ║
    ║     Vision API Product Search                             ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check for RapidAPI key
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        print("❌ RAPIDAPI_KEY environment variable not set!")
        print("\nSet it with:")
        print("  export RAPIDAPI_KEY=your_key_here")
        print("\nOr pass as argument:")
        print("  python import_1000_asos.py YOUR_RAPIDAPI_KEY")
        
        if len(sys.argv) > 1:
            api_key = sys.argv[1]
            print(f"\n✅ Using API key from argument")
        else:
            sys.exit(1)
    
    # Step 1: Fetch products from ASOS
    print("\n" + "="*60)
    print("STEP 1: Fetch Products from ASOS API")
    print("="*60)
    
    fetcher = ASOSFetcher(api_key)
    products = fetcher.fetch_products(target_count=1000)
    
    if not products:
        print("❌ No products fetched!")
        sys.exit(1)
    
    # Save to JSON for reference
    save_products_json(products, "asos_products_1000.json")
    
    # Step 2: Import to Vision API
    print("\n" + "="*60)
    print("STEP 2: Import to Vision API Product Search")
    print("="*60)
    
    importer = VisionProductImporter()
    result = importer.import_products(products, max_workers=2)
    
    # Summary
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║     IMPORT COMPLETE                                       ║
    ╚═══════════════════════════════════════════════════════════╝
    
    Results:
    --------
    ✅ Success: {result['success']}
    ❌ Failed:  {result['failed']}
    📦 Total:   {result['total']}
    
    NEXT STEPS:
    -----------
    1. ⏳ WAIT 30-60 MINUTES for indexing to complete
       (This is required by Vision API)
    
    2. Check index status:
       python -c "from vision_product_search import VisionProductSearch; VisionProductSearch().check_index_status()"
    
    3. Test visual search:
       python test_search.py
    
    4. Start the API server:
       python shop_the_look_api.py
    
    📁 Products saved to: asos_products_1000.json
    """)


if __name__ == "__main__":
    main()
