"""
YOW - Vision Warehouse Search API
=================================
FastAPI endpoints for Shop the Look visual search using Vision Warehouse.

Endpoints:
- POST /api/shop-the-look/search/text - Search by text description
- POST /api/shop-the-look/search/image - Search by image upload
- POST /api/shop-the-look/search/base64 - Search by base64 image (for FlutterFlow)
- GET /api/shop-the-look/status - Check service status

Project: Your Online Wardrobe
"""

import os
import json
import base64
import subprocess
import requests
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configuration
PROJECT_ID = "gen-lang-client-0930631788"
LOCATION = "us-central1"
INDEX_ENDPOINT_ID = "yow-search-endpoint"
CORPUS_ID = "yow-shop-the-look"

# API Base URL
API_BASE = "https://warehouse-visionai.googleapis.com/v1"

# Cache project number
_project_number = None


def get_project_number() -> str:
    """Get project number from project ID"""
    global _project_number
    if _project_number:
        return _project_number
    
    result = subprocess.run(
        ["gcloud", "projects", "describe", PROJECT_ID, "--format=value(projectNumber)"],
        capture_output=True, text=True
    )
    _project_number = result.stdout.strip()
    return _project_number


def get_access_token() -> str:
    """Get Google Cloud access token"""
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


# FastAPI app
app = FastAPI(
    title="YOW Shop the Look API",
    description="Visual product search using Vision AI Warehouse",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class TextSearchRequest(BaseModel):
    query: str
    max_results: int = 10
    filters: Optional[dict] = None


class ImageSearchRequest(BaseModel):
    image_base64: str
    max_results: int = 10
    filters: Optional[dict] = None


class ImageUrlSearchRequest(BaseModel):
    image_url: str
    max_results: int = 10
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    asset_id: str
    relevance: float
    product_id: Optional[str] = None
    name: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    count: int
    query_type: str


def search_index_endpoint(query_data: dict) -> dict:
    """Make search request to Vision Warehouse"""
    project_number = get_project_number()
    token = get_access_token()
    
    endpoint = f"{API_BASE}/projects/{project_number}/locations/{LOCATION}/indexEndpoints/{INDEX_ENDPOINT_ID}:searchIndexEndpoint"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(endpoint, headers=headers, json=query_data, timeout=30)
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Vision Warehouse error: {response.text}"
        )
    
    return response.json()


def get_asset_annotations(asset_name: str) -> dict:
    """Get annotations for an asset"""
    token = get_access_token()
    
    # Get annotations endpoint
    endpoint = f"{API_BASE}/{asset_name}/annotations"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(endpoint, headers=headers, timeout=10)
    
    if response.status_code != 200:
        return {}
    
    annotations = {}
    for ann in response.json().get("annotations", []):
        key = ann.get("key", "")
        value = ann.get("value", {})
        
        if "strValue" in value:
            annotations[key] = value["strValue"]
        elif "floatValue" in value:
            annotations[key] = value["floatValue"]
        elif "intValue" in value:
            annotations[key] = value["intValue"]
    
    return annotations


def parse_search_results(raw_results: dict, include_annotations: bool = True) -> List[SearchResult]:
    """Parse Vision Warehouse search results"""
    results = []
    
    for item in raw_results.get("searchResultItems", []):
        asset_name = item.get("asset", "")
        relevance = float(item.get("relevance", 0))
        
        # Extract asset ID from name
        asset_id = asset_name.split("/")[-1] if asset_name else ""
        
        result = SearchResult(
            asset_id=asset_id,
            relevance=relevance,
            product_id=f"asos_{asset_id}",
        )
        
        # Get annotations if requested
        if include_annotations and asset_name:
            try:
                annotations = get_asset_annotations(asset_name)
                result.name = annotations.get("name")
                result.color = annotations.get("color")
                result.category = annotations.get("category")
                result.brand = annotations.get("brand")
                result.product_id = annotations.get("product_id", f"asos_{asset_id}")
            except:
                pass
        
        results.append(result)
    
    return results


@app.get("/")
async def root():
    """Health check"""
    return {
        "service": "YOW Shop the Look API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/api/shop-the-look/status")
async def get_status():
    """Check Vision Warehouse status"""
    try:
        project_number = get_project_number()
        token = get_access_token()
        
        # Check if endpoint exists
        endpoint = f"{API_BASE}/projects/{project_number}/locations/{LOCATION}/indexEndpoints/{INDEX_ENDPOINT_ID}"
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(endpoint, headers=headers, timeout=10)
        
        if response.status_code == 200:
            endpoint_data = response.json()
            return {
                "status": "ready",
                "endpoint": INDEX_ENDPOINT_ID,
                "deployed_indexes": endpoint_data.get("deployedIndexes", [])
            }
        else:
            return {
                "status": "not_ready",
                "message": "Index endpoint not found or not deployed"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/api/shop-the-look/search/text", response_model=SearchResponse)
async def search_by_text(request: TextSearchRequest):
    """
    Search for products by text description.
    
    Example: "blue summer dress" or "black leather jacket"
    """
    query_data = {
        "text_query": request.query,
        "page_size": request.max_results
    }
    
    # Add criteria filters if provided
    if request.filters:
        criteria = []
        for key, value in request.filters.items():
            criteria.append({
                "field": key,
                "text_array": {"txt_values": [value]}
            })
        if criteria:
            query_data["criteria"] = criteria
    
    raw_results = search_index_endpoint(query_data)
    results = parse_search_results(raw_results)
    
    return SearchResponse(
        results=results,
        count=len(results),
        query_type="text"
    )


@app.post("/api/shop-the-look/search/base64", response_model=SearchResponse)
async def search_by_base64(request: ImageSearchRequest):
    """
    Search for similar products by base64-encoded image.
    
    This is the main endpoint for FlutterFlow integration.
    """
    # Decode base64 to get image bytes
    try:
        # Handle data URL format (data:image/jpeg;base64,...)
        if "," in request.image_base64:
            image_data = request.image_base64.split(",")[1]
        else:
            image_data = request.image_base64
        
        # Validate base64
        base64.b64decode(image_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {str(e)}")
    
    query_data = {
        "image_query": {
            "input_image_bytes": image_data
        },
        "page_size": request.max_results
    }
    
    # Add criteria filters if provided
    if request.filters:
        criteria = []
        for key, value in request.filters.items():
            criteria.append({
                "field": key,
                "text_array": {"txt_values": [value]}
            })
        if criteria:
            query_data["criteria"] = criteria
    
    raw_results = search_index_endpoint(query_data)
    results = parse_search_results(raw_results)
    
    return SearchResponse(
        results=results,
        count=len(results),
        query_type="image"
    )


@app.post("/api/shop-the-look/search/upload", response_model=SearchResponse)
async def search_by_upload(
    file: UploadFile = File(...),
    max_results: int = 10
):
    """
    Search for similar products by uploading an image file.
    """
    # Read and encode image
    contents = await file.read()
    image_base64 = base64.b64encode(contents).decode()
    
    query_data = {
        "image_query": {
            "input_image_bytes": image_base64
        },
        "page_size": max_results
    }
    
    raw_results = search_index_endpoint(query_data)
    results = parse_search_results(raw_results)
    
    return SearchResponse(
        results=results,
        count=len(results),
        query_type="image_upload"
    )


@app.post("/api/shop-the-look/search/url", response_model=SearchResponse)
async def search_by_url(request: ImageUrlSearchRequest):
    """
    Search for similar products by image URL.
    
    Downloads the image and searches for similar products.
    """
    # Download image
    try:
        response = requests.get(request.image_url, timeout=30)
        response.raise_for_status()
        image_base64 = base64.b64encode(response.content).decode()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")
    
    query_data = {
        "image_query": {
            "input_image_bytes": image_base64
        },
        "page_size": request.max_results
    }
    
    raw_results = search_index_endpoint(query_data)
    results = parse_search_results(raw_results)
    
    return SearchResponse(
        results=results,
        count=len(results),
        query_type="image_url"
    )


if __name__ == "__main__":
    import uvicorn
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     YOW - Shop the Look API                               ║
    ║     Vision Warehouse Visual Search                        ║
    ╚═══════════════════════════════════════════════════════════╝
    
    Starting server on http://localhost:8001
    
    API Documentation: http://localhost:8001/docs
    
    Endpoints:
    ----------
    POST /api/shop-the-look/search/text   - Search by text
    POST /api/shop-the-look/search/base64 - Search by base64 image
    POST /api/shop-the-look/search/upload - Search by file upload
    POST /api/shop-the-look/search/url    - Search by image URL
    GET  /api/shop-the-look/status        - Check service status
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
