"""
YOW - Vision Warehouse Image Search for Shop the Look
======================================================
Uses Google Cloud Vision AI Warehouse for visual product search.
This is the modern replacement for the deprecated Vision API Product Search.

Flow:
1. Create a Corpus (container for images)
2. Create Data Schemas (for annotations like color, category, brand)
3. Upload images to GCS + Create JSONL import file
4. Import Assets to Corpus
5. Analyze Corpus (generate embeddings)
6. Create Index
7. Create Index Endpoint
8. Deploy Index to Endpoint
9. Search!

Project: Your Online Wardrobe
Project ID: gen-lang-client-0930631788
"""

import os
import sys
import json
import time
import requests
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Configuration
PROJECT_ID = "gen-lang-client-0930631788"
PROJECT_NUMBER = None  # Will be fetched
LOCATION = "us-central1"  # Vision Warehouse supported region
BUCKET_NAME = f"{PROJECT_ID}-vision-warehouse"
CORPUS_ID = "yow-shop-the-look"
INDEX_ID = "yow-product-index"
INDEX_ENDPOINT_ID = "yow-search-endpoint"

# API Base URL
API_BASE = f"https://warehouse-visionai.googleapis.com/v1"


def get_access_token() -> str:
    """Get Google Cloud access token"""
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def get_project_number() -> str:
    """Get project number from project ID"""
    result = subprocess.run(
        ["gcloud", "projects", "describe", PROJECT_ID, "--format=value(projectNumber)"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def api_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make authenticated API request to Vision Warehouse"""
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    url = f"{API_BASE}/{endpoint}"
    
    if method == "GET":
        response = requests.get(url, headers=headers, timeout=60)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data, timeout=60)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers, timeout=60)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    if response.status_code >= 400:
        print(f"❌ API Error: {response.status_code}")
        print(f"   {response.text[:500]}")
        return {"error": response.status_code, "message": response.text}
    
    return response.json() if response.text else {}


def wait_for_operation(operation_name: str, timeout_minutes: int = 30) -> bool:
    """Wait for a long-running operation to complete"""
    print(f"⏳ Waiting for operation: {operation_name.split('/')[-1][:20]}...")
    
    start_time = time.time()
    while time.time() - start_time < timeout_minutes * 60:
        result = api_request("GET", operation_name.replace(f"{API_BASE}/", ""))
        
        if result.get("done"):
            if "error" in result:
                print(f"❌ Operation failed: {result['error']}")
                return False
            print("✅ Operation completed!")
            return True
        
        time.sleep(10)
        print("   Still processing...")
    
    print(f"⚠️ Operation timed out after {timeout_minutes} minutes")
    return False


class VisionWarehouseSetup:
    """Set up Vision Warehouse for Shop the Look"""
    
    def __init__(self):
        global PROJECT_NUMBER
        PROJECT_NUMBER = get_project_number()
        print(f"✅ Project Number: {PROJECT_NUMBER}")
        self.base_path = f"projects/{PROJECT_NUMBER}/locations/{LOCATION}"
    
    def create_corpus(self) -> Optional[str]:
        """Create an image corpus"""
        print("\n📦 Creating Image Corpus...")
        
        # Check if corpus already exists
        print("   Checking for existing corpora...")
        result = api_request("GET", f"{self.base_path}/corpora")
        
        if "error" not in result and "corpora" in result:
            for corpus in result["corpora"]:
                corpus_name = corpus.get("name", "")
                display_name = corpus.get("displayName", "")
                print(f"   Found corpus: {display_name} ({corpus_name})")
                # Return the first one we find (or one matching our display name)
                if "yow" in display_name.lower() or "shop" in display_name.lower() or "asos" in display_name.lower():
                    print(f"✅ Using existing corpus: {corpus_name}")
                    return corpus_name
            
            # If we have any corpora, use the first one
            if result["corpora"]:
                corpus_name = result["corpora"][0].get("name")
                print(f"✅ Using existing corpus: {corpus_name}")
                return corpus_name
        
        print("   No existing corpus found, creating new one...")
        
        data = {
            "display_name": "YOW Shop the Look Products",
            "description": "ASOS product images for visual search",
            "type": "IMAGE",
            "search_capability_setting": {
                "search_capabilities": [
                    {"type": "EMBEDDING_SEARCH"}
                ]
            }
        }
        
        result = api_request(
            "POST",
            f"{self.base_path}/corpora",
            data
        )
        
        if "error" in result:
            print(f"   Error creating corpus, checking if one exists anyway...")
            # Check again if it was created despite the error
            check_result = api_request("GET", f"{self.base_path}/corpora")
            if "corpora" in check_result and check_result["corpora"]:
                corpus_name = check_result["corpora"][0].get("name")
                print(f"✅ Found corpus: {corpus_name}")
                return corpus_name
            return None
        
        # Wait for operation if needed
        if "name" in result and "operations" in result["name"]:
            wait_for_operation(result["name"])
            # After operation, get the corpus
            check_result = api_request("GET", f"{self.base_path}/corpora")
            if "corpora" in check_result and check_result["corpora"]:
                corpus_name = check_result["corpora"][0].get("name")
                print(f"✅ Corpus created: {corpus_name}")
                return corpus_name
        
        # Extract corpus name from response
        if "response" in result:
            corpus_name = result["response"].get("name")
            if corpus_name:
                print(f"✅ Corpus created: {corpus_name}")
                return corpus_name
        
        print("⚠️ Corpus may have been created but couldn't get name")
        return None
    
    def create_data_schemas(self, corpus_name: str) -> bool:
        """Create data schemas for product annotations"""
        print("\n📋 Creating Data Schemas...")
        
        schemas = [
            {"key": "color", "type": "STRING", "search": "EXACT_SEARCH"},
            {"key": "category", "type": "STRING", "search": "EXACT_SEARCH"},
            {"key": "brand", "type": "STRING", "search": "EXACT_SEARCH"},
            {"key": "gender", "type": "STRING", "search": "EXACT_SEARCH"},
            {"key": "product_id", "type": "STRING", "search": "EXACT_SEARCH"},
            {"key": "name", "type": "STRING", "search": "SMART_SEARCH"},
            {"key": "price", "type": "FLOAT", "search": "NO_SEARCH"},
        ]
        
        corpus_path = corpus_name.replace(f"{API_BASE}/", "")
        
        for schema in schemas:
            data = {
                "key": schema["key"],
                "schema_details": {
                    "type": schema["type"],
                    "granularity": "GRANULARITY_ASSET_LEVEL",
                    "search_strategy": {
                        "search_strategy_type": schema["search"]
                    }
                }
            }
            
            result = api_request(
                "POST",
                f"{corpus_path}/dataSchemas",
                data
            )
            
            if "error" not in result:
                print(f"   ✅ Schema created: {schema['key']}")
            else:
                # Schema might already exist
                if "ALREADY_EXISTS" in str(result.get("message", "")):
                    print(f"   ℹ️ Schema already exists: {schema['key']}")
                else:
                    print(f"   ⚠️ Failed to create schema {schema['key']}: {result.get('message', '')[:100]}")
        
        return True
    
    def create_index(self, corpus_name: str) -> Optional[str]:
        """Create an index on the corpus"""
        print("\n📊 Creating Index...")
        
        corpus_path = corpus_name.replace(f"{API_BASE}/", "")
        
        # Check if index exists
        result = api_request("GET", f"{corpus_path}/indexes")
        if "indexes" in result:
            for index in result["indexes"]:
                if INDEX_ID in index.get("name", ""):
                    print(f"✅ Index already exists: {index['name']}")
                    return index["name"]
        
        data = {
            "display_name": "YOW Product Search Index",
            "description": "Index for visual product search"
        }
        
        result = api_request(
            "POST",
            f"{corpus_path}/indexes?index_id={INDEX_ID}",
            data
        )
        
        if "error" in result:
            return None
        
        # Wait for operation (this can take a while)
        if "name" in result and "operations" in result["name"]:
            wait_for_operation(result["name"], timeout_minutes=60)
        
        index_name = f"{corpus_path}/indexes/{INDEX_ID}"
        print(f"✅ Index created: {index_name}")
        return index_name
    
    def create_index_endpoint(self) -> Optional[str]:
        """Create an index endpoint for search"""
        print("\n🔌 Creating Index Endpoint...")
        
        # Check if endpoint exists
        result = api_request("GET", f"{self.base_path}/indexEndpoints")
        if "indexEndpoints" in result:
            for endpoint in result["indexEndpoints"]:
                if INDEX_ENDPOINT_ID in endpoint.get("name", ""):
                    print(f"✅ Index Endpoint already exists: {endpoint['name']}")
                    return endpoint["name"]
        
        data = {
            "display_name": "YOW Shop the Look Search",
            "description": "Endpoint for visual product search"
        }
        
        result = api_request(
            "POST",
            f"{self.base_path}/indexEndpoints?index_endpoint_id={INDEX_ENDPOINT_ID}",
            data
        )
        
        if "error" in result:
            return None
        
        # Wait for operation
        if "name" in result and "operations" in result["name"]:
            wait_for_operation(result["name"])
        
        endpoint_name = f"{self.base_path}/indexEndpoints/{INDEX_ENDPOINT_ID}"
        print(f"✅ Index Endpoint created: {endpoint_name}")
        return endpoint_name
    
    def deploy_index(self, index_name: str, endpoint_name: str) -> bool:
        """Deploy index to endpoint"""
        print("\n🚀 Deploying Index to Endpoint...")
        
        endpoint_path = endpoint_name.replace(f"{API_BASE}/", "")
        
        data = {
            "deployedIndex": {
                "index": index_name
            }
        }
        
        result = api_request(
            "POST",
            f"{endpoint_path}:deployIndex",
            data
        )
        
        if "error" in result:
            if "ALREADY_EXISTS" in str(result.get("message", "")):
                print("✅ Index already deployed")
                return True
            return False
        
        # Wait for deployment (can take 10-20 minutes)
        if "name" in result and "operations" in result["name"]:
            wait_for_operation(result["name"], timeout_minutes=30)
        
        print("✅ Index deployed!")
        return True


class ProductImporter:
    """Import products to Vision Warehouse"""
    
    def __init__(self):
        global PROJECT_NUMBER
        if not PROJECT_NUMBER:
            PROJECT_NUMBER = get_project_number()
        self.base_path = f"projects/{PROJECT_NUMBER}/locations/{LOCATION}"
        self.corpus_path = f"{self.base_path}/corpora/{CORPUS_ID}"
    
    def upload_images_to_gcs(self, products: List[dict]) -> List[dict]:
        """Upload product images to Cloud Storage and return GCS URIs"""
        from google.cloud import storage
        
        print(f"\n📤 Uploading {len(products)} images to Cloud Storage...")
        
        # Create bucket if needed
        client = storage.Client()
        try:
            bucket = client.get_bucket(BUCKET_NAME)
        except:
            bucket = client.create_bucket(BUCKET_NAME, location=LOCATION)
            print(f"✅ Created bucket: {BUCKET_NAME}")
        
        uploaded = []
        for i, product in enumerate(products):
            try:
                # Download image
                image_url = product.get("image_url", "")
                if not image_url:
                    continue
                
                response = requests.get(
                    image_url,
                    timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                response.raise_for_status()
                
                # Upload to GCS
                product_id = product.get("product_id", f"product_{i}")
                blob_name = f"products/{product_id}.jpg"
                blob = bucket.blob(blob_name)
                blob.upload_from_string(
                    response.content,
                    content_type="image/jpeg"
                )
                
                gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
                product["gcs_uri"] = gcs_uri
                uploaded.append(product)
                
                if (i + 1) % 50 == 0:
                    print(f"   Uploaded {i + 1}/{len(products)} images")
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"   ⚠️ Failed to upload {product.get('product_id')}: {e}")
                continue
        
        print(f"✅ Uploaded {len(uploaded)} images to GCS")
        return uploaded
    
    def create_import_jsonl(self, products: List[dict], output_path: str) -> str:
        """Create JSONL file for bulk import"""
        print(f"\n📝 Creating import JSONL file...")
        
        with open(output_path, 'w') as f:
            for product in products:
                if "gcs_uri" not in product:
                    continue
                
                # Create import record
                record = {
                    "gcsUri": product["gcs_uri"],
                    "assetId": product.get("product_id", "").replace("asos_", ""),
                    "annotations": [
                        {"key": "product_id", "value": {"strValue": product.get("product_id", "")}},
                        {"key": "name", "value": {"strValue": product.get("name", "")[:500]}},
                        {"key": "color", "value": {"strValue": product.get("color", "unknown")}},
                        {"key": "category", "value": {"strValue": product.get("category", "clothing")}},
                        {"key": "brand", "value": {"strValue": product.get("brand", "ASOS")}},
                        {"key": "gender", "value": {"strValue": product.get("gender", "unisex")}},
                    ]
                }
                
                if product.get("price"):
                    record["annotations"].append(
                        {"key": "price", "value": {"floatValue": float(product.get("price", 0))}}
                    )
                
                f.write(json.dumps(record) + "\n")
        
        print(f"✅ Created JSONL: {output_path}")
        return output_path
    
    def upload_jsonl_to_gcs(self, local_path: str) -> str:
        """Upload JSONL file to GCS"""
        from google.cloud import storage
        
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        
        blob_name = "import/products_import.jsonl"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        
        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
        print(f"✅ Uploaded JSONL to: {gcs_uri}")
        return gcs_uri
    
    def import_assets(self, jsonl_gcs_uri: str) -> bool:
        """Import assets from JSONL file"""
        print(f"\n📥 Importing assets to corpus...")
        
        data = {
            "assets_gcs_uri": jsonl_gcs_uri
        }
        
        result = api_request(
            "POST",
            f"{self.corpus_path}/assets:import",
            data
        )
        
        if "error" in result:
            return False
        
        # Wait for import operation
        if "name" in result:
            wait_for_operation(result["name"], timeout_minutes=60)
        
        print("✅ Assets imported!")
        return True
    
    def analyze_corpus(self) -> bool:
        """Analyze corpus to generate embeddings"""
        print(f"\n🔬 Analyzing corpus (generating embeddings)...")
        
        data = {
            "name": self.corpus_path
        }
        
        result = api_request(
            "POST",
            f"{self.corpus_path}:analyze",
            data
        )
        
        if "error" in result:
            return False
        
        # Wait for analysis (this can take a while for large datasets)
        if "name" in result:
            wait_for_operation(result["name"], timeout_minutes=120)
        
        print("✅ Corpus analyzed!")
        return True


class VisionWarehouseSearch:
    """Search products using Vision Warehouse"""
    
    def __init__(self):
        global PROJECT_NUMBER
        if not PROJECT_NUMBER:
            PROJECT_NUMBER = get_project_number()
        self.base_path = f"projects/{PROJECT_NUMBER}/locations/{LOCATION}"
        self.endpoint_path = f"{self.base_path}/indexEndpoints/{INDEX_ENDPOINT_ID}"
    
    def search_by_text(self, query: str, max_results: int = 10) -> List[dict]:
        """Search for products by text query"""
        data = {
            "text_query": query,
            "page_size": max_results
        }
        
        result = api_request(
            "POST",
            f"{self.endpoint_path}:searchIndexEndpoint",
            data
        )
        
        return result.get("searchResultItems", [])
    
    def search_by_image_uri(self, gcs_uri: str, max_results: int = 10) -> List[dict]:
        """Search for similar products by image GCS URI"""
        data = {
            "image_query": {
                "input_image": gcs_uri
            },
            "page_size": max_results
        }
        
        result = api_request(
            "POST",
            f"{self.endpoint_path}:searchIndexEndpoint",
            data
        )
        
        return result.get("searchResultItems", [])
    
    def search_by_image_bytes(self, image_bytes: bytes, max_results: int = 10) -> List[dict]:
        """Search for similar products by image bytes"""
        import base64
        
        data = {
            "image_query": {
                "input_image_bytes": base64.b64encode(image_bytes).decode()
            },
            "page_size": max_results
        }
        
        result = api_request(
            "POST",
            f"{self.endpoint_path}:searchIndexEndpoint",
            data
        )
        
        return result.get("searchResultItems", [])


def load_products_from_json(json_path: str) -> List[dict]:
    """Load products from the previously saved JSON file"""
    with open(json_path, 'r') as f:
        return json.load(f)


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     YOW - Vision Warehouse Setup for Shop the Look        ║
    ║     Modern Visual Product Search                          ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Step 1: Set up Vision Warehouse infrastructure
    print("\n" + "="*60)
    print("STEP 1: Set Up Vision Warehouse Infrastructure")
    print("="*60)
    
    setup = VisionWarehouseSetup()
    
    # Create corpus
    corpus_name = setup.create_corpus()
    if not corpus_name:
        print("❌ Failed to create corpus")
        sys.exit(1)
    
    # Create data schemas
    setup.create_data_schemas(corpus_name)
    
    # Step 2: Import products
    print("\n" + "="*60)
    print("STEP 2: Import Products")
    print("="*60)
    
    # Load products from previously saved JSON
    products_file = "asos_products_1000.json"
    if not os.path.exists(products_file):
        print(f"❌ Products file not found: {products_file}")
        print("   Run import_1000_asos.py first to fetch products")
        sys.exit(1)
    
    products = load_products_from_json(products_file)
    print(f"✅ Loaded {len(products)} products from {products_file}")
    
    importer = ProductImporter()
    
    # Upload images to GCS
    products_with_gcs = importer.upload_images_to_gcs(products[:100])  # Start with 100 for testing
    
    # Create import JSONL
    jsonl_path = "vision_warehouse_import.jsonl"
    importer.create_import_jsonl(products_with_gcs, jsonl_path)
    
    # Upload JSONL to GCS
    jsonl_gcs_uri = importer.upload_jsonl_to_gcs(jsonl_path)
    
    # Import assets
    importer.import_assets(jsonl_gcs_uri)
    
    # Analyze corpus
    importer.analyze_corpus()
    
    # Step 3: Create and deploy index
    print("\n" + "="*60)
    print("STEP 3: Create and Deploy Index")
    print("="*60)
    
    # Create index
    index_name = setup.create_index(corpus_name)
    if not index_name:
        print("❌ Failed to create index")
        sys.exit(1)
    
    # Create index endpoint
    endpoint_name = setup.create_index_endpoint()
    if not endpoint_name:
        print("❌ Failed to create index endpoint")
        sys.exit(1)
    
    # Deploy index
    setup.deploy_index(index_name, endpoint_name)
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║     SETUP COMPLETE!                                       ║
    ╚═══════════════════════════════════════════════════════════╝
    
    Vision Warehouse is now ready for visual search!
    
    Resources created:
    ------------------
    📦 Corpus: {corpus_name}
    📊 Index: {index_name}
    🔌 Endpoint: {endpoint_name}
    
    NEXT STEPS:
    -----------
    1. Test the search:
       python vision_warehouse_search.py
    
    2. Integrate with your FastAPI backend
    
    3. Connect to FlutterFlow
    """)


if __name__ == "__main__":
    main()
