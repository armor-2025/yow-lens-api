"""
YOW - ASOS Product Import Script
================================
This script imports ASOS products into Vision API Product Search.

You can either:
1. Import from your PostgreSQL database
2. Import from ASOS API directly
3. Import from a CSV file

Project: Your Online Wardrobe
Project ID: gen-lang-client-0930631788
"""

import os
import csv
import json
import requests
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
PROJECT_ID = "gen-lang-client-0930631788"
LOCATION = "us-east1"
PRODUCT_SET_ID = "yow-asos-products"
BUCKET_NAME = f"{PROJECT_ID}-product-images"

# Set credentials
CREDENTIALS_PATH = os.path.expanduser("~/yow-vision-key.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH


@dataclass
class ASOSProduct:
    """Represents an ASOS product to import"""
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
            labels["color"] = self.color.lower()
        if self.category:
            labels["category"] = self.category.lower()
        if self.subcategory:
            labels["subcategory"] = self.subcategory.lower()
        if self.brand:
            labels["brand"] = self.brand.lower()
        if self.gender:
            labels["gender"] = self.gender.lower()
        return labels


class ASOSProductImporter:
    """
    Import ASOS products into Vision API Product Search.
    """
    
    def __init__(self):
        """Initialize the importer"""
        from google.cloud import storage
        from vision_product_search import VisionProductSearch
        
        self.storage_client = storage.Client()
        self.vision_search = VisionProductSearch()
        self.bucket = self.storage_client.bucket(BUCKET_NAME)
        
        print(f"✅ ASOSProductImporter initialized")
        print(f"   Bucket: gs://{BUCKET_NAME}")
    
    def download_and_upload_image(
        self, 
        image_url: str, 
        product_id: str
    ) -> Optional[str]:
        """
        Download image from URL and upload to Cloud Storage.
        
        Args:
            image_url: URL of the product image
            product_id: Product ID for naming the file
        
        Returns:
            Cloud Storage URI or None if failed
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=30)
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
            
            gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
            return gcs_uri
            
        except Exception as e:
            print(f"⚠️ Failed to upload image for {product_id}: {e}")
            return None
    
    def import_single_product(self, product: ASOSProduct) -> bool:
        """
        Import a single ASOS product.
        
        Args:
            product: ASOSProduct to import
        
        Returns:
            True if successful
        """
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
                display_name=product.name,
                labels=product.to_labels(),
                description=f"ASOS {product.category or 'Fashion'} - {product.name}"
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
        """
        Import multiple products in parallel.
        
        Args:
            products: List of ASOSProduct objects
            max_workers: Number of parallel workers
        
        Returns:
            Dict with success/failure counts
        """
        print(f"\n📤 Importing {len(products)} products...")
        
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
                    print(f"❌ Error importing {product.product_id}: {e}")
                
                # Progress update every 10 products
                if (i + 1) % 10 == 0:
                    print(f"   Progress: {i + 1}/{len(products)}")
        
        print(f"\n✅ Import complete!")
        print(f"   Success: {success_count}")
        print(f"   Failed: {failure_count}")
        
        return {
            "success": success_count,
            "failed": failure_count,
            "total": len(products)
        }
    
    def create_bulk_import_csv(
        self, 
        products: List[ASOSProduct],
        output_path: str = "./products_import.csv"
    ) -> str:
        """
        Create a CSV file for bulk import and upload to GCS.
        This is faster for large catalogs (1000+ products).
        
        Args:
            products: List of ASOSProduct objects
            output_path: Local path for CSV file
        
        Returns:
            GCS URI of the uploaded CSV
        """
        print(f"\n📝 Creating bulk import CSV for {len(products)} products...")
        
        # First upload all images
        product_gcs_uris = {}
        
        print("   Uploading images to Cloud Storage...")
        for i, product in enumerate(products):
            gcs_uri = self.download_and_upload_image(
                product.image_url,
                product.product_id
            )
            if gcs_uri:
                product_gcs_uris[product.product_id] = gcs_uri
            
            if (i + 1) % 50 == 0:
                print(f"   Uploaded {i + 1}/{len(products)} images")
        
        # Create CSV
        print("   Writing CSV file...")
        with open(output_path, 'w', newline='') as csvfile:
            for product in products:
                gcs_uri = product_gcs_uris.get(product.product_id)
                if not gcs_uri:
                    continue
                
                # Build labels string (key=value|key=value)
                labels = product.to_labels()
                labels_str = "|".join([f"{k}={v}" for k, v in labels.items()])
                
                # CSV format:
                # image-uri,image-id,product-set-id,product-id,product-category,product-display-name,labels,bounding-poly
                row = [
                    gcs_uri,                    # image-uri
                    f"img_{product.product_id}", # image-id
                    PRODUCT_SET_ID,              # product-set-id
                    product.product_id,          # product-id
                    "apparel",                   # product-category
                    product.name,                # product-display-name
                    labels_str,                  # labels
                    ""                           # bounding-poly (optional)
                ]
                csvfile.write(",".join([str(x) for x in row]) + "\n")
        
        # Upload CSV to GCS
        print("   Uploading CSV to Cloud Storage...")
        csv_blob = self.bucket.blob("import/products_bulk.csv")
        csv_blob.upload_from_filename(output_path)
        
        gcs_csv_uri = f"gs://{BUCKET_NAME}/import/products_bulk.csv"
        print(f"✅ CSV uploaded: {gcs_csv_uri}")
        
        return gcs_csv_uri
    
    def run_bulk_import(self, products: List[ASOSProduct]) -> dict:
        """
        Create CSV and run bulk import operation.
        
        Args:
            products: List of ASOSProduct objects
        
        Returns:
            Import operation status
        """
        # Create and upload CSV
        gcs_csv_uri = self.create_bulk_import_csv(products)
        
        # Run bulk import
        return self.vision_search.bulk_import_from_csv(gcs_csv_uri)


# =============================================================================
# Helper functions to load products from different sources
# =============================================================================

def load_products_from_json(json_path: str) -> List[ASOSProduct]:
    """
    Load products from a JSON file.
    
    Expected format:
    [
        {
            "id": "12345",
            "name": "Blue Midi Dress",
            "image_url": "https://...",
            "color": "blue",
            "category": "Dresses",
            "brand": "ASOS DESIGN"
        },
        ...
    ]
    """
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    products = []
    for item in data:
        products.append(ASOSProduct(
            product_id=str(item.get("id", item.get("product_id"))),
            name=item.get("name", item.get("title", "")),
            image_url=item.get("image_url", item.get("imageUrl", "")),
            color=item.get("color"),
            category=item.get("category"),
            subcategory=item.get("subcategory"),
            brand=item.get("brand"),
            price=item.get("price"),
            gender=item.get("gender")
        ))
    
    return products


def load_products_from_csv(csv_path: str) -> List[ASOSProduct]:
    """
    Load products from a CSV file.
    
    Expected columns: id, name, image_url, color, category, brand
    """
    products = []
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(ASOSProduct(
                product_id=row.get("id", row.get("product_id", "")),
                name=row.get("name", row.get("title", "")),
                image_url=row.get("image_url", row.get("imageUrl", "")),
                color=row.get("color"),
                category=row.get("category"),
                subcategory=row.get("subcategory"),
                brand=row.get("brand"),
                price=float(row.get("price", 0)) if row.get("price") else None,
                gender=row.get("gender")
            ))
    
    return products


def load_products_from_postgres(
    connection_string: str,
    query: str = None
) -> List[ASOSProduct]:
    """
    Load products from PostgreSQL database.
    
    Args:
        connection_string: PostgreSQL connection string
        query: Optional custom query (defaults to selecting all products)
    """
    import psycopg2
    
    if not query:
        query = """
            SELECT 
                id as product_id,
                name,
                image_url,
                color,
                category,
                subcategory,
                brand,
                price,
                gender
            FROM products
            WHERE image_url IS NOT NULL
            LIMIT 1000
        """
    
    products = []
    
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            
            for row in cur.fetchall():
                row_dict = dict(zip(columns, row))
                products.append(ASOSProduct(
                    product_id=str(row_dict.get("product_id", row_dict.get("id"))),
                    name=row_dict.get("name", ""),
                    image_url=row_dict.get("image_url", ""),
                    color=row_dict.get("color"),
                    category=row_dict.get("category"),
                    subcategory=row_dict.get("subcategory"),
                    brand=row_dict.get("brand"),
                    price=row_dict.get("price"),
                    gender=row_dict.get("gender")
                ))
    
    return products


# =============================================================================
# Sample products for testing
# =============================================================================

SAMPLE_PRODUCTS = [
    ASOSProduct(
        product_id="test_001",
        name="Blue Midi Wrap Dress",
        image_url="https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=400",
        color="blue",
        category="dresses",
        subcategory="midi",
        brand="ASOS DESIGN",
        gender="women"
    ),
    ASOSProduct(
        product_id="test_002", 
        name="Black Leather Jacket",
        image_url="https://images.unsplash.com/photo-1551028719-00167b16eac5?w=400",
        color="black",
        category="jackets",
        subcategory="leather",
        brand="ASOS DESIGN",
        gender="women"
    ),
    ASOSProduct(
        product_id="test_003",
        name="White Sneakers",
        image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400",
        color="white",
        category="shoes",
        subcategory="sneakers",
        brand="ASOS DESIGN",
        gender="unisex"
    ),
    ASOSProduct(
        product_id="test_004",
        name="Red Floral Maxi Dress",
        image_url="https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=400",
        color="red",
        category="dresses",
        subcategory="maxi",
        brand="ASOS DESIGN",
        gender="women"
    ),
    ASOSProduct(
        product_id="test_005",
        name="Denim Jeans Slim Fit",
        image_url="https://images.unsplash.com/photo-1542272604-787c3835535d?w=400",
        color="blue",
        category="jeans",
        subcategory="slim",
        brand="ASOS DESIGN",
        gender="men"
    ),
]


# =============================================================================
# Main entry point
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     YOW - ASOS Product Import                             ║
    ║     Vision API Product Search                             ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Initialize importer
    importer = ASOSProductImporter()
    
    # For testing, import sample products
    print("\n📦 Importing sample products for testing...")
    print("   (Replace with your actual ASOS products later)\n")
    
    result = importer.import_products(SAMPLE_PRODUCTS)
    
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
    1. Wait 30-60 minutes for indexing to complete
    
    2. Check index status:
       python -c "from vision_product_search import VisionProductSearch; VisionProductSearch().check_index_status()"
    
    3. Test a search:
       python test_search.py
    
    4. Import your real ASOS products:
       - From JSON: products = load_products_from_json('products.json')
       - From CSV:  products = load_products_from_csv('products.csv')
       - From DB:   products = load_products_from_postgres(connection_string)
       
       Then run: importer.import_products(products)
    """)
