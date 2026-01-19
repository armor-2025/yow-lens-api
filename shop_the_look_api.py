"""
YOW Lens - Shop the Look API
FastAPI endpoint for visual outfit search
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import asyncpg
import base64
import io
from PIL import Image
import numpy as np
from fashion_clip.fashion_clip import FashionCLIP

# Initialize
app = FastAPI(title="YOW Lens - Shop the Look API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = "postgresql://localhost/yow_lens_test"

# Load models at startup
fashion_clip = None
analyzer = None

@app.on_event("startup")
async def startup():
    global fashion_clip, analyzer
    print("Loading FashionCLIP...")
    fashion_clip = FashionCLIP('fashion-clip')
    print("Loading Garment Analyzer...")
    from garment_analyzer import GarmentAnalyzer
    analyzer = GarmentAnalyzer()
    print("✓ Ready!")


# ============== IMAGE PREPROCESSING ==============

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
    image = Image.open(buffer)
    
    return image


# ============== MODELS ==============

class DetectedItem(BaseModel):
    category: str
    label: str
    color: Optional[str]
    material: Optional[str]
    pattern: Optional[str]
    texture: Optional[str]
    features: List[str] = []
    style_keywords: List[str] = []
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
    visual_score: float
    text_score: float
    color_score: float
    feature_boost: float
    matched_features: List[str] = []

class ShopTheLookResponse(BaseModel):
    success: bool
    items_detected: int
    results: dict


# ============== HELPER FUNCTIONS ==============

def color_name_to_rgb(color_name: str) -> tuple:
    color_map = {
        'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
        'blue': (0, 0, 255), 'navy': (0, 0, 128), 'green': (0, 128, 0),
        'olive': (107, 142, 35), 'yellow': (255, 255, 0), 'orange': (255, 165, 0),
        'pink': (255, 192, 203), 'purple': (128, 0, 128), 'brown': (139, 69, 19),
        'beige': (245, 245, 220), 'cream': (255, 253, 208), 'gray': (128, 128, 128),
        'grey': (128, 128, 128), 'tan': (210, 180, 140), 'burgundy': (128, 0, 32),
    }
    color_lower = (color_name or '').lower()
    for name, rgb in color_map.items():
        if name in color_lower:
            return rgb
    return (128, 128, 128)


def extract_primary_color(gemini_color: str) -> str:
    if not gemini_color:
        return 'gray'
    gemini_lower = gemini_color.lower()
    color_words = ['olive', 'navy', 'burgundy', 'black', 'white', 'gray', 'grey', 
                   'blue', 'red', 'green', 'brown', 'pink', 'purple', 'yellow', 'orange']
    for color in color_words:
        if color in gemini_lower:
            return color
    return 'gray'


def delta_e(color1: tuple, color2: tuple) -> float:
    return np.sqrt(sum((a-b)**2 for a, b in zip(color1, color2)))


def build_text_query(attrs: dict) -> str:
    parts = []
    seen = set()
    
    def add_unique(text):
        if not text or text in ['-', '?', 'null', 'none', 'None', '']:
            return
        words = text.lower().replace('_', ' ').split()
        for word in words:
            if word not in seen and len(word) > 2:
                parts.append(word)
                seen.add(word)
    
    add_unique(attrs.get('color', ''))
    add_unique(attrs.get('texture', ''))
    
    features = attrs.get('distinctive_features', [])
    if features and isinstance(features, list):
        for f in features[:3]:
            add_unique(f)
    
    add_unique(attrs.get('pattern', ''))
    add_unique(attrs.get('sleeve_length', ''))
    add_unique(attrs.get('fit', ''))
    
    keywords = attrs.get('style_keywords', [])
    if keywords and isinstance(keywords, list):
        for kw in keywords[:2]:
            add_unique(kw)
    
    add_unique(attrs.get('category', ''))
    
    return ' '.join(parts)


FEATURE_KEYWORDS = {
    'wide leg': ['wide leg', 'wide-leg'],
    'high waisted': ['high waist', 'high-waist', 'high rise'],
    'crew neck': ['crew neck', 'crew-neck', 'crewneck'],
    'v-neck': ['v-neck', 'v neck', 'vneck'],
    'woven': ['woven', 'intrecciato', 'braided'],
    'quilted': ['quilted', 'quilt'],
    'pleated': ['pleat', 'pleated'],
    'sheer': ['sheer', 'transparent'],
    'lace': ['lace', 'lacy'],
    'horizontal stripes': ['stripe', 'striped', 'breton'],
}


def calculate_feature_boost(product_name: str, attrs: dict) -> tuple:
    product_lower = (product_name or '').lower()
    boost = 0.0
    matched = []
    
    features = attrs.get('distinctive_features', [])
    if features and isinstance(features, list):
        for feature in features:
            feature_lower = (feature or '').lower()
            
            if feature_lower in product_lower:
                boost += 0.10
                matched.append(feature)
                continue
            
            if feature_lower in FEATURE_KEYWORDS:
                for kw in FEATURE_KEYWORDS[feature_lower]:
                    if kw in product_lower:
                        boost += 0.10
                        matched.append(feature)
                        break
    
    keywords = attrs.get('style_keywords', [])
    if keywords and isinstance(keywords, list):
        for kw in keywords:
            kw_lower = (kw or '').lower()
            if kw_lower and len(kw_lower) > 3 and kw_lower in product_lower:
                boost += 0.03
                matched.append(f"style:{kw}")
    
    return min(boost, 0.30), matched


# ============== PATTERN FILTERING ==============

PATTERN_KEYWORDS = {
    'striped': ['stripe', 'striped', 'stripes'],
    'horizontal_stripes': ['stripe', 'breton', 'rugby'],
    'plaid': ['plaid', 'check', 'tartan'],
    'floral': ['floral', 'flower'],
    'woven': ['woven', 'intrecciato'],
}

PATTERN_EXCLUDES = {
    'horizontal_stripes': ['pinstripe', 'vertical'],
}


def check_pattern_match(product_name: str, pattern: str) -> bool:
    if not pattern or pattern.lower() in ['solid', '-', '?', 'null', 'none', '']:
        return True
    
    pattern_lower = pattern.lower()
    product_lower = (product_name or '').lower()
    
    if pattern_lower in PATTERN_EXCLUDES:
        for exclude in PATTERN_EXCLUDES[pattern_lower]:
            if exclude in product_lower:
                return False
    
    if pattern_lower in PATTERN_KEYWORDS:
        for kw in PATTERN_KEYWORDS[pattern_lower]:
            if kw in product_lower:
                return True
        return False
    
    return True


# ============== MAIN ENDPOINT ==============

@app.post("/shop-the-look", response_model=ShopTheLookResponse)
async def shop_the_look(
    file: UploadFile = File(...),
    limit_per_item: int = 5
):
    contents = await file.read()
    raw_image = Image.open(io.BytesIO(contents))
    image = preprocess_image(raw_image)
    
    items = analyzer.analyze_outfit(image)
    crops = analyzer.crop_items(image, items)
    
    if not crops:
        raise HTTPException(status_code=400, detail="No fashion items detected in image")
    
    conn = await asyncpg.connect(DB_URL)
    
    results = {}
    
    for crop_data in crops:
        attrs = crop_data['attributes']
        crop_img = crop_data['image']
        
        category = attrs.get('category', 'unknown').lower()
        label = attrs.get('label', 'unknown')
        
        if not attrs.get('bounding_box'):
            continue
        
        text_query = build_text_query(attrs)
        
        gemini_color = attrs.get('color', '')
        primary_color = extract_primary_color(gemini_color)
        query_color_rgb = color_name_to_rgb(primary_color)
        
        pattern = attrs.get('pattern', '')
        
        # Generate embeddings
        # Pass PIL Image directly to FashionCLIP
        img_embedding = fashion_clip.encode_images([crop_img], batch_size=1)[0]
        img_emb_str = "[" + ",".join(map(str, img_embedding.tolist())) + "]"
        
        text_emb_str = None
        if text_query:
            text_embedding = fashion_clip.encode_text([text_query], batch_size=1)[0]
            text_emb_str = "[" + ",".join(map(str, text_embedding.tolist())) + "]"
        
        cat_count = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE category = $1", category
        )
        
        where_clause = f"WHERE category = '{category}'" if cat_count > 0 else ""
        
        if text_emb_str:
            query = f"""
                SELECT 
                    id, name, brand, price, category, color, image_url,
                    1 - (embedding <=> '{img_emb_str}'::vector) as visual_sim,
                    1 - (embedding <=> '{text_emb_str}'::vector) as text_sim
                FROM products
                {where_clause}
                ORDER BY (
                    0.5 * (1 - (embedding <=> '{img_emb_str}'::vector)) +
                    0.5 * (1 - (embedding <=> '{text_emb_str}'::vector))
                ) DESC
                LIMIT 100
            """
        else:
            query = f"""
                SELECT 
                    id, name, brand, price, category, color, image_url,
                    1 - (embedding <=> '{img_emb_str}'::vector) as visual_sim,
                    0.0 as text_sim
                FROM products
                {where_clause}
                ORDER BY embedding <=> '{img_emb_str}'::vector
                LIMIT 100
            """
        
        rows = await conn.fetch(query)
        
        scored = []
        for r in rows:
            if not check_pattern_match(r['name'], pattern):
                continue
            
            product_rgb = color_name_to_rgb(r['color'] or 'gray')
            color_distance = delta_e(query_color_rgb, product_rgb)
            color_sim = max(0, 1 - (color_distance / 441.67))
            
            feature_boost, matched_features = calculate_feature_boost(r['name'], attrs)
            
            combined = (
                0.55 * float(r['visual_sim']) +
                0.35 * float(r['text_sim']) +
                0.00 * color_sim +
                feature_boost
            )
            
            scored.append(ProductMatch(
                id=r['id'],
                name=r['name'],
                brand=r['brand'],
                price=float(r['price']) if r['price'] else 0,
                color=r['color'] or '',
                category=r['category'],
                image_url=r['image_url'],
                product_url=None,
                similarity_score=round(combined, 3),
                visual_score=round(float(r['visual_sim']), 3),
                text_score=round(float(r['text_sim']), 3),
                color_score=round(color_sim, 3),
                feature_boost=round(feature_boost, 3),
                matched_features=matched_features,
            ))
        
        scored.sort(key=lambda x: x.similarity_score, reverse=True)
        
        item_key = f"{category}_{label[:30].replace(' ', '_')}"
        results[item_key] = {
            'detected_item': DetectedItem(
                category=category,
                label=label,
                color=attrs.get('color'),
                material=attrs.get('material'),
                pattern=attrs.get('pattern'),
                texture=attrs.get('texture'),
                features=attrs.get('distinctive_features', []),
                style_keywords=attrs.get('style_keywords', []),
                bounding_box=attrs.get('bounding_box'),
            ).dict(),
            'text_query': text_query,
            'products': [p.dict() for p in scored[:limit_per_item]],
            'total_matches': len(scored),
        }
    
    await conn.close()
    
    return ShopTheLookResponse(
        success=True,
        items_detected=len(results),
        results=results,
    )


@app.get("/health")
async def health_check():
    conn = await asyncpg.connect(DB_URL)
    stats = await conn.fetch("""
        SELECT category, COUNT(*) as cnt 
        FROM products 
        GROUP BY category
        ORDER BY cnt DESC
    """)
    total = await conn.fetchval("SELECT COUNT(*) FROM products")
    await conn.close()
    
    return {
        "status": "healthy",
        "models_loaded": fashion_clip is not None,
        "total_products": total,
        "categories": {cat['category']: cat['cnt'] for cat in stats}
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
