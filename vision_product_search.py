"""
YOW - Vision API Product Search Client
======================================
This module provides the core functionality for Shop the Look visual search.

Project: Your Online Wardrobe
Project ID: gen-lang-client-0930631788
"""

import os
import base64
from typing import List, Dict, Optional
from dataclasses import dataclass

# Configuration
PROJECT_ID = "gen-lang-client-0930631788"
LOCATION = "us-east1"
PRODUCT_SET_ID = "yow-asos-products"
PRODUCT_CATEGORY = "apparel"  # Perfect for fashion!
BUCKET_NAME = f"{PROJECT_ID}-product-images"

# Set credentials path
CREDENTIALS_PATH = os.path.expanduser("~/yow-vision-key.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH


@dataclass
class SearchResult:
    """A single search result from Vision Product Search"""
    product_id: str
    display_name: str
    score: float
    image_uri: str
    labels: Dict[str, str]
    
    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "display_name": self.display_name,
            "score": self.score,
            "image_uri": self.image_uri,
            "labels": self.labels
        }


class VisionProductSearch:
    """
    Vision API Product Search client for YOW Shop the Look feature.
    
    Usage:
        search = VisionProductSearch()
        
        # Setup (run once)
        search.create_product_set()
        
        # Add products
        search.add_product("prod_123", "Blue Dress", labels={"color": "blue"})
        search.add_reference_image("prod_123", "gs://bucket/image.jpg")
        
        # Search
        results = search.search_by_image_base64(image_base64)
    """
    
    def __init__(self):
        """Initialize the Vision Product Search client"""
        try:
            from google.cloud import vision
            from google.cloud.vision_v1 import ProductSearchClient
            
            self.vision = vision
            self.product_search_client = ProductSearchClient()
            self.image_annotator_client = vision.ImageAnnotatorClient()
            
            self.location_path = f"projects/{PROJECT_ID}/locations/{LOCATION}"
            self.product_set_path = f"{self.location_path}/productSets/{PRODUCT_SET_ID}"
            
            print(f"✅ VisionProductSearch initialized")
            print(f"   Project: {PROJECT_ID}")
            print(f"   Location: {LOCATION}")
            print(f"   Product Set: {PRODUCT_SET_ID}")
            
        except ImportError:
            raise ImportError(
                "google-cloud-vision is not installed. Run:\n"
                "pip install google-cloud-vision --break-system-packages"
            )
    
    # =========================================================================
    # SETUP METHODS - Run these once to create your catalog
    # =========================================================================
    
    def create_product_set(self) -> dict:
        """
        Create a product set to hold all ASOS products.
        Run this once before adding products.
        """
        from google.cloud.vision_v1.types import ProductSet
        from google.api_core.exceptions import AlreadyExists
        
        product_set = ProductSet(
            display_name="YOW ASOS Fashion Products"
        )
        
        try:
            response = self.product_search_client.create_product_set(
                parent=self.location_path,
                product_set=product_set,
                product_set_id=PRODUCT_SET_ID
            )
            print(f"✅ Product set created: {response.name}")
            return {"status": "created", "name": response.name}
            
        except AlreadyExists:
            print(f"ℹ️ Product set already exists: {self.product_set_path}")
            return {"status": "exists", "name": self.product_set_path}
    
    def add_product(
        self, 
        product_id: str, 
        display_name: str,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> dict:
        """
        Add a single product (e.g., an ASOS item).
        
        Args:
            product_id: Unique ID for the product (e.g., ASOS product ID)
            display_name: Human-readable name
            labels: Dict of filterable labels like {"color": "blue", "style": "casual"}
            description: Optional product description
        
        Returns:
            Dict with product info
        """
        from google.cloud.vision_v1.types import Product
        from google.api_core.exceptions import AlreadyExists
        
        # Build labels for filtering
        product_labels = []
        if labels:
            for key, value in labels.items():
                product_labels.append(
                    Product.KeyValue(key=key, value=str(value))
                )
        
        product = Product(
            display_name=display_name,
            product_category=PRODUCT_CATEGORY,
            product_labels=product_labels,
            description=description
        )
        
        try:
            response = self.product_search_client.create_product(
                parent=self.location_path,
                product=product,
                product_id=product_id
            )
            
            # Add product to our product set
            self.product_search_client.add_product_to_product_set(
                name=self.product_set_path,
                product=response.name
            )
            
            print(f"✅ Product added: {product_id} - {display_name}")
            return {"status": "created", "name": response.name}
            
        except AlreadyExists:
            print(f"ℹ️ Product already exists: {product_id}")
            return {"status": "exists", "product_id": product_id}
    
    def add_reference_image(
        self, 
        product_id: str, 
        gcs_uri: str,
        reference_image_id: Optional[str] = None
    ) -> dict:
        """
        Add a reference image to a product.
        
        Args:
            product_id: The product to add the image to
            gcs_uri: Cloud Storage URI (gs://bucket/path/image.jpg)
            reference_image_id: Optional ID for the reference image
        
        Returns:
            Dict with reference image info
        """
        from google.cloud.vision_v1.types import ReferenceImage
        from google.api_core.exceptions import AlreadyExists
        
        product_path = f"{self.location_path}/products/{product_id}"
        
        reference_image = ReferenceImage(uri=gcs_uri)
        
        try:
            response = self.product_search_client.create_reference_image(
                parent=product_path,
                reference_image=reference_image,
                reference_image_id=reference_image_id
            )
            print(f"✅ Reference image added to {product_id}: {gcs_uri}")
            return {"status": "created", "name": response.name}
            
        except AlreadyExists:
            print(f"ℹ️ Reference image already exists for {product_id}")
            return {"status": "exists", "product_id": product_id}
    
    def bulk_import_from_csv(self, gcs_csv_uri: str) -> dict:
        """
        Bulk import products from a CSV file in Cloud Storage.
        
        CSV format (no header):
        gs://bucket/image.jpg,image-id,product-set-id,product-id,apparel,Display Name,color=blue|style=casual,
        
        Args:
            gcs_csv_uri: Cloud Storage URI to the CSV file
        
        Returns:
            Dict with import operation info
        """
        from google.cloud.vision_v1.types import (
            ImportProductSetsInputConfig,
            ImportProductSetsGcsSource,
        )
        
        gcs_source = ImportProductSetsGcsSource(csv_file_uri=gcs_csv_uri)
        input_config = ImportProductSetsInputConfig(gcs_source=gcs_source)
        
        print(f"📤 Starting bulk import from: {gcs_csv_uri}")
        print("   This may take 30-60 minutes to index...")
        
        response = self.product_search_client.import_product_sets(
            parent=self.location_path,
            input_config=input_config
        )
        
        print(f"   Operation started: {response.operation.name}")
        
        # Optionally wait for completion (can take a while)
        # result = response.result()
        
        return {
            "status": "started",
            "operation": response.operation.name,
            "message": "Import started. Check index status in 30-60 minutes."
        }
    
    # =========================================================================
    # SEARCH METHODS - Use these for Shop the Look queries
    # =========================================================================
    
    def search_by_image_base64(
        self, 
        image_base64: str,
        filter_expression: Optional[str] = None,
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Search for similar products using a base64 encoded image.
        This is the main method for FlutterFlow integration.
        
        Args:
            image_base64: Base64 encoded image string
            filter_expression: Optional filter like "color=blue AND style=casual"
            max_results: Maximum number of results (default 10)
        
        Returns:
            List of SearchResult objects
        """
        # Decode base64 to bytes
        image_content = base64.b64decode(image_base64)
        
        image = self.vision.Image(content=image_content)
        
        product_search_params = self.vision.ProductSearchParams(
            product_set=self.product_set_path,
            product_categories=[PRODUCT_CATEGORY],
            filter=filter_expression or ""
        )
        
        image_context = self.vision.ImageContext(
            product_search_params=product_search_params
        )
        
        response = self.image_annotator_client.product_search(
            image=image,
            image_context=image_context,
            max_results=max_results
        )
        
        return self._parse_search_results(response)
    
    def search_by_image_url(
        self, 
        image_url: str,
        filter_expression: Optional[str] = None,
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Search for similar products using an image URL.
        
        Args:
            image_url: URL to the query image
            filter_expression: Optional filter
            max_results: Maximum number of results
        
        Returns:
            List of SearchResult objects
        """
        image = self.vision.Image()
        image.source.image_uri = image_url
        
        product_search_params = self.vision.ProductSearchParams(
            product_set=self.product_set_path,
            product_categories=[PRODUCT_CATEGORY],
            filter=filter_expression or ""
        )
        
        image_context = self.vision.ImageContext(
            product_search_params=product_search_params
        )
        
        response = self.image_annotator_client.product_search(
            image=image,
            image_context=image_context,
            max_results=max_results
        )
        
        return self._parse_search_results(response)
    
    def search_by_gcs_uri(
        self, 
        gcs_uri: str,
        filter_expression: Optional[str] = None,
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Search for similar products using an image in Cloud Storage.
        
        Args:
            gcs_uri: Cloud Storage URI (gs://bucket/path/image.jpg)
            filter_expression: Optional filter
            max_results: Maximum number of results
        
        Returns:
            List of SearchResult objects
        """
        image = self.vision.Image()
        image.source.image_uri = gcs_uri
        
        product_search_params = self.vision.ProductSearchParams(
            product_set=self.product_set_path,
            product_categories=[PRODUCT_CATEGORY],
            filter=filter_expression or ""
        )
        
        image_context = self.vision.ImageContext(
            product_search_params=product_search_params
        )
        
        response = self.image_annotator_client.product_search(
            image=image,
            image_context=image_context,
            max_results=max_results
        )
        
        return self._parse_search_results(response)
    
    def _parse_search_results(self, response) -> List[SearchResult]:
        """Parse the API response into SearchResult objects"""
        results = []
        
        product_search_results = response.product_search_results
        
        if not product_search_results or not product_search_results.results:
            print("⚠️ No results found. Check if products are indexed.")
            return results
        
        for result in product_search_results.results:
            product = result.product
            
            # Extract product ID from the full resource name
            product_id = product.name.split("/")[-1]
            
            # Parse labels
            labels = {}
            for kv in product.product_labels:
                labels[kv.key] = kv.value
            
            results.append(SearchResult(
                product_id=product_id,
                display_name=product.display_name,
                score=result.score,
                image_uri=result.image,
                labels=labels
            ))
        
        return results
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def check_index_status(self) -> dict:
        """
        Check if the product set has been indexed.
        Indexing takes 30-60 minutes after adding/importing products.
        
        Returns:
            Dict with indexing status
        """
        try:
            product_set = self.product_search_client.get_product_set(
                name=self.product_set_path
            )
            
            index_time = product_set.index_time
            
            # If index_time year is 1970, still indexing
            if index_time.year == 1970:
                print("⏳ Product set is still indexing. Please wait 30-60 minutes...")
                return {
                    "indexed": False,
                    "message": "Still indexing. Please wait."
                }
            else:
                print(f"✅ Product set indexed at: {index_time}")
                return {
                    "indexed": True,
                    "index_time": str(index_time),
                    "message": "Ready for searches!"
                }
                
        except Exception as e:
            print(f"❌ Error checking index status: {e}")
            return {
                "indexed": False,
                "error": str(e)
            }
    
    def list_products(self, page_size: int = 100) -> List[dict]:
        """
        List all products in the product set.
        
        Args:
            page_size: Number of products per page
        
        Returns:
            List of product dicts
        """
        products = []
        
        request = {
            "name": self.product_set_path,
            "page_size": page_size
        }
        
        for product in self.product_search_client.list_products_in_product_set(request=request):
            products.append({
                "name": product.name,
                "product_id": product.name.split("/")[-1],
                "display_name": product.display_name,
                "category": product.product_category,
                "labels": {kv.key: kv.value for kv in product.product_labels}
            })
        
        print(f"📦 Found {len(products)} products in product set")
        return products
    
    def delete_product(self, product_id: str) -> bool:
        """Delete a product from the catalog"""
        product_path = f"{self.location_path}/products/{product_id}"
        
        try:
            self.product_search_client.delete_product(name=product_path)
            print(f"🗑️ Deleted product: {product_id}")
            return True
        except Exception as e:
            print(f"❌ Error deleting product: {e}")
            return False
    
    def delete_product_set(self) -> bool:
        """Delete the entire product set (use with caution!)"""
        try:
            self.product_search_client.delete_product_set(name=self.product_set_path)
            print(f"🗑️ Deleted product set: {PRODUCT_SET_ID}")
            return True
        except Exception as e:
            print(f"❌ Error deleting product set: {e}")
            return False


# =============================================================================
# Quick test
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing VisionProductSearch Client")
    print("="*60 + "\n")
    
    try:
        # Initialize client
        search = VisionProductSearch()
        
        # Check if product set exists / create it
        print("\n📋 Creating/checking product set...")
        search.create_product_set()
        
        # Check index status
        print("\n📊 Checking index status...")
        status = search.check_index_status()
        print(f"   Status: {status}")
        
        print("\n✅ Client is ready!")
        print("\nNext steps:")
        print("1. Import your ASOS products using import_asos_products.py")
        print("2. Wait 30-60 minutes for indexing")
        print("3. Test searches with sample images")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you've run setup_vision_search.py first!")
