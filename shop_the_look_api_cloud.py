"""
YOW Lens - Shop the Look API (Cloud Version)
Uses Pinecone for vector search + Supabase for product metadata
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import psycopg2
from pinecone import Pinecone
import base64
import io
from PIL import Image
import numpy as np
import os
import requests
import json
from datetime import datetime
import uuid

# ============== CONFIG ==============

SUPABASE_URL = os.environ.get("SUPABASE_URL")
PINECONE_API_KEY = "pcsk_3e2bNu_ESZ77iM7pxPbnFrb1GgH4hRZrpeLmwrw6TWoQg8Rd8QFvP3NXx2E3Y5ohtD5W8r"
PINECONE_INDEX = "yow-products"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Category priority for sorting (lower = more prominent, shown first)
CATEGORY_PRIORITY = {
    'outerwear': 1,
    'coat': 1,
    'jacket': 1,
    'blazer': 1,
    'dress': 2,
    'jumpsuit': 2,
    'top': 3,
    'shirt': 3,
    'blouse': 3,
    'sweater': 3,
    'bottom': 4,
    'pants': 4,
    'jeans': 4,
    'skirt': 4,
    'shorts': 4,
    'shoes': 5,
    'footwear': 5,
    'bag': 6,
    'handbag': 6,
    'accessory': 7,
    'accessories': 7,
    'jewelry': 8,
    'hat': 8,
    'scarf': 8,
    'belt': 8,
    'sunglasses': 8,
    'watch': 8,
}

def get_category_priority(category: str) -> int:
    """Get sort priority for a category (lower = shown first)"""
    cat_lower = category.lower() if category else 'unknown'
    return CATEGORY_PRIORITY.get(cat_lower, 99)

# ============== APP ==============

app = FastAPI(title="YOW Lens - Shop the Look API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== GLOBALS ==============

fashion_clip = None
analyzer = None
pinecone_index = None

@app.on_event("startup")
async def startup():
    global fashion_clip, analyzer, pinecone_index
    
    print("🚀 Starting YOW Lens API (Cloud)...")
    
    print("   Loading FashionCLIP...")
    from fashion_clip.fashion_clip import FashionCLIP
    fashion_clip = FashionCLIP('fashion-clip')
    print("   ✅ FashionCLIP loaded")
    
    print("   Loading Garment Analyzer...")
    from garment_analyzer import GarmentAnalyzer
    analyzer = GarmentAnalyzer()
    print("   ✅ Garment Analyzer loaded")
    
    print("   Connecting to Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    pinecone_index = pc.Index(PINECONE_INDEX)
    stats = pinecone_index.describe_index_stats()
    print(f"   ✅ Pinecone connected ({stats.total_vector_count} vectors)")
    
    print("✅ YOW Lens API ready!")


# ============== MODELS ==============

class DetectedItem(BaseModel):
    category: str
    label: str
    color: Optional[str]
    material: Optional[str]
    pattern: Optional[str]
    bounding_box: Optional[dict]

class ProductMatch(BaseModel):
    id: str
    name: str
    brand: str
    price: float
    color: str
    category: str
    image_url: str
    product_url: Optional[str]
    similarity_score: float

class ShopTheLookResponse(BaseModel):
    success: bool
    items_detected: int
    results: dict

class ProcessInspoRequest(BaseModel):
    image_url: str
    user_id: Optional[str] = None

class ProcessInspoResponse(BaseModel):
    success: bool
    post_id: str
    items_detected: int
    results: List[dict]  # Changed from dict to List[dict]


# ============== HELPERS ==============

def preprocess_image(image: Image.Image, max_dim: int = 1500) -> Image.Image:
    if image.mode != 'RGB':
        image = image.convert('RGB')
    if max(image.size) > max_dim:
        ratio = max_dim / max(image.size)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=90)
    buffer.seek(0)
    return Image.open(buffer)


def search_pinecone(embedding: list, category: str = None, subcategory: str = None, limit: int = 50) -> list:
    """Search Pinecone for similar products"""
    filter_dict = {}
    if subcategory:
        filter_dict["subcategory"] = {"$eq": subcategory}
    elif category:
        filter_dict["category"] = {"$eq": category}
    
    results = pinecone_index.query(
        vector=embedding,
        top_k=limit,
        include_metadata=True,
        filter=filter_dict if filter_dict else None
    )
    return results.matches


def get_products_from_supabase(product_ids: list) -> dict:
    """Fetch full product details from Supabase"""
    if not product_ids:
        return {}
    
    conn = psycopg2.connect(SUPABASE_URL)
    cur = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(product_ids))
    cur.execute(f"""
        SELECT id, name, brand, price, color, category, subcategory, image_url, product_url
        FROM products
        WHERE id IN ({placeholders})
    """, product_ids)
    
    products = {}
    for row in cur.fetchall():
        products[row[0]] = {
            'id': row[0],
            'name': row[1],
            'brand': row[2],
            'price': float(row[3]) if row[3] else 0,
            'color': row[4],
            'category': row[5],
            'subcategory': row[6],
            'image_url': row[7],
            'product_url': row[8]
        }
    
    cur.close()
    conn.close()
    return products


def download_image(url: str) -> Image.Image:
    """Download image from URL"""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))


def save_inspo_post(post_id: str, user_id: str, image_url: str, detected_items: dict, product_matches: dict, embeddings: dict):
    """Save processed inspo post to database"""
    conn = psycopg2.connect(SUPABASE_URL)
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO inspo_posts (id, user_id, image_url, detected_items, product_matches, embeddings, processed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            detected_items = EXCLUDED.detected_items,
            product_matches = EXCLUDED.product_matches,
            embeddings = EXCLUDED.embeddings,
            processed_at = EXCLUDED.processed_at
    """, (
        post_id,
        user_id if user_id and user_id.strip() else None,
        image_url,
        json.dumps(detected_items),
        json.dumps(product_matches),
        json.dumps(embeddings),
        datetime.utcnow()
    ))
    
    conn.commit()
    cur.close()
    conn.close()


def get_inspo_post(post_id: str) -> dict:
    """Get cached inspo post from database"""
    conn = psycopg2.connect(SUPABASE_URL)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, user_id, image_url, detected_items, product_matches, embeddings, likes_count, comments_count, created_at, processed_at
        FROM inspo_posts
        WHERE id = %s
    """, (post_id,))
    
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        return None
    
    return {
        'id': str(row[0]),
        'user_id': str(row[1]) if row[1] else None,
        'image_url': row[2],
        'detected_items': row[3],
        'product_matches': row[4],
        'embeddings': row[5],
        'likes_count': row[6],
        'comments_count': row[7],
        'created_at': row[8].isoformat() if row[8] else None,
        'processed_at': row[9].isoformat() if row[9] else None
    }


# ============== ENDPOINTS ==============

@app.post("/process-inspo", response_model=ProcessInspoResponse)
async def process_inspo_image(request: ProcessInspoRequest):
    """
    Process an inspo image from URL and cache results.
    Returns results as an array sorted by category prominence (outerwear/tops/bottoms first, accessories last).
    """
    try:
        # Download image
        raw_image = download_image(request.image_url)
        image = preprocess_image(raw_image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")
    
    # Detect items with Gemini
    items = analyzer.analyze_outfit(image)
    crops = analyzer.crop_items(image, items)
    
    if not crops:
        raise HTTPException(status_code=400, detail="No fashion items detected")
    
    results_list = []  # Changed to list
    detected_items = {}
    embeddings = {}
    
    for crop_data in crops:
        attrs = crop_data['attributes']
        crop_img = crop_data['image']
        
        category = attrs.get('category', 'unknown').lower()
        label = attrs.get('label', 'unknown')
        
        if not attrs.get('bounding_box'):
            continue
        
        # Generate embedding with FashionCLIP
        embedding = fashion_clip.encode_images([crop_img], batch_size=1)[0]
        embedding_list = embedding.tolist()
        
        # Search Pinecone
        subcategory = attrs.get('subcategory', '').lower()
        matches = search_pinecone(embedding_list, subcategory=subcategory, limit=20)
        
        if len(matches) < 3:
            matches = search_pinecone(embedding_list, category=category, limit=20)
        
        # Get product details
        product_ids = [m.id for m in matches]
        products = get_products_from_supabase(product_ids)
        
        # Build response
        product_matches = []
        for m in matches[:10]:
            if m.id in products:
                p = products[m.id]
                product_matches.append({
                    'id': p['id'],
                    'name': p['name'],
                    'brand': p['brand'] or '',
                    'price': p['price'],
                    'color': p['color'] or '',
                    'category': p['category'] or '',
                    'image_url': p['image_url'] or '',
                    'product_url': p['product_url'],
                    'similarity_score': round(m.score, 3)
                })
        
        item_key = f"{category}_{label[:30].replace(' ', '_')}"
        
        detected_item = {
            'category': category,
            'label': label,
            'color': attrs.get('color'),
            'material': attrs.get('material'),
            'pattern': attrs.get('pattern'),
            'bounding_box': attrs.get('bounding_box')
        }
        
        detected_items[item_key] = detected_item
        
        # Add to results list (will sort later)
        results_list.append({
            'item_key': item_key,
            'detected_item': detected_item,
            'products': product_matches,
            'total_matches': len(matches)
        })
        
        embeddings[item_key] = embedding_list
    
    # Sort results by category priority (outerwear/tops/bottoms first, accessories last)
    results_list.sort(key=lambda x: get_category_priority(x['detected_item']['category']))
    
    # Generate post ID and save to database
    post_id = str(uuid.uuid4())
    save_inspo_post(
        post_id=post_id,
        user_id=request.user_id if request.user_id and request.user_id.strip() and request.user_id.lower() != "null" else None,
        image_url=request.image_url,
        detected_items=detected_items,
        product_matches={item['item_key']: item['products'] for item in results_list},
        embeddings=embeddings
    )
    
    # Flatten all products from all detected items for easy FlutterFlow consumption
    all_products = []
    for item in results_list:
        for product in item['products']:
            product['detected_category'] = item['detected_item']['category']
            product['detected_label'] = item['detected_item']['label']
            all_products.append(product)
    
    return {
        "success": True,
        "post_id": post_id,
        "items_detected": len(results_list),
        "results": results_list,
        "products": all_products
    }


@app.get("/inspo/{post_id}")
async def get_inspo(post_id: str):
    """
    Get cached inspo post data.
    Use this when user taps on an inspo image in the feed.
    """
    post = get_inspo_post(post_id)
    
    if not post:
        raise HTTPException(status_code=404, detail="Inspo post not found")
    
    return {
        "success": True,
        "post": post
    }


@app.post("/shop-the-look", response_model=ShopTheLookResponse)
async def shop_the_look(
    file: UploadFile = File(...),
    limit_per_item: int = 10
):
    """
    Analyze outfit image and find similar products.
    Uses Pinecone for vector search, Supabase for product details.
    """
    contents = await file.read()
    raw_image = Image.open(io.BytesIO(contents))
    image = preprocess_image(raw_image)
    
    # Detect items with Gemini
    items = analyzer.analyze_outfit(image)
    crops = analyzer.crop_items(image, items)
    
    if not crops:
        raise HTTPException(status_code=400, detail="No fashion items detected")
    
    results = {}
    
    for crop_data in crops:
        attrs = crop_data['attributes']
        crop_img = crop_data['image']
        
        category = attrs.get('category', 'unknown').lower()
        label = attrs.get('label', 'unknown')
        
        if not attrs.get('bounding_box'):
            continue
        
        # Generate embedding with FashionCLIP
        embedding = fashion_clip.encode_images([crop_img], batch_size=1)[0]
        embedding_list = embedding.tolist()
        
        # Search Pinecone - try subcategory first, fallback to category
        subcategory = attrs.get('subcategory', '').lower()
        matches = search_pinecone(embedding_list, subcategory=subcategory, limit=limit_per_item * 2)
        
        # Fallback to category if no/few results
        if len(matches) < 3:
            matches = search_pinecone(embedding_list, category=category, limit=limit_per_item * 2)
        
        # Get product details from Supabase
        product_ids = [m.id for m in matches]
        products = get_products_from_supabase(product_ids)
        
        # Build response
        product_matches = []
        for m in matches[:limit_per_item]:
            if m.id in products:
                p = products[m.id]
                product_matches.append(ProductMatch(
                    id=p['id'],
                    name=p['name'],
                    brand=p['brand'] or '',
                    price=p['price'],
                    color=p['color'] or '',
                    category=p['category'] or '',
                    image_url=p['image_url'] or '',
                    product_url=p['product_url'],
                    similarity_score=round(m.score, 3)
                ))
        
        item_key = f"{category}_{label[:30].replace(' ', '_')}"
        results[item_key] = {
            'detected_item': DetectedItem(
                category=category,
                label=label,
                color=attrs.get('color'),
                material=attrs.get('material'),
                pattern=attrs.get('pattern'),
                bounding_box=attrs.get('bounding_box')
            ).dict(),
            'products': [p.dict() for p in product_matches],
            'total_matches': len(matches),
            'embedding': embedding_list
        }
    
    return ShopTheLookResponse(
        success=True,
        items_detected=len(results),
        results=results
    )


@app.post("/search-by-embedding")
async def search_by_embedding(
    embedding: List[float],
    category: str = None,
    limit: int = 10
):
    """
    Search using a cached embedding (no Gemini call needed).
    Use this for refreshing product matches on cached inspo posts.
    """
    matches = search_pinecone(embedding, category=category, limit=limit)
    product_ids = [m.id for m in matches]
    products = get_products_from_supabase(product_ids)
    
    results = []
    for m in matches:
        if m.id in products:
            p = products[m.id]
            results.append({
                **p,
                'similarity_score': round(m.score, 3)
            })
    
    return {"success": True, "results": results}


@app.get("/health")
async def health_check():
    stats = pinecone_index.describe_index_stats()
    return {
        "status": "healthy",
        "pinecone_vectors": stats.total_vector_count,
        "models_loaded": fashion_clip is not None
    }


@app.get("/")
async def root():
    return {
        "service": "YOW Lens - Shop the Look API",
        "version": "2.0 (Cloud)",
        "docs": "/docs"
    }



# Query parameter version for FlutterFlow compatibility
@app.get("/inspo-post")
async def get_inspo_query(post_id: str):
    """Get cached inspo post by ID (query parameter version)"""
    post = get_inspo_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "post": post}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
