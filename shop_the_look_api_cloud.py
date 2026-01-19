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

# ============== CONFIG ==============

SUPABASE_URL = "postgresql://postgres:1WFf3xVzY3HVaSRz@db.eayoasnkemanrguvfuch.supabase.co:5432/postgres"
PINECONE_API_KEY = "pcsk_3e2bNu_ESZ77iM7pxPbnFrb1GgH4hRZrpeLmwrw6TWoQg8Rd8QFvP3NXx2E3Y5ohtD5W8r"
PINECONE_INDEX = "yow-products"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyARJ5pKG26LhsrfX9pidnLjJlYrY3jIEOA")

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


def search_pinecone(embedding: list, category: str = None, limit: int = 50) -> list:
    """Search Pinecone for similar products"""
    filter_dict = {}
    if category:
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


# ============== ENDPOINTS ==============

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
        
        # Search Pinecone
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
            'embedding': embedding_list  # Return for caching!
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
