"""
YOW Lens - Hybrid Search System v13
Fixed: dedupe text query, lower color weight when uncertain
"""
import asyncio
import asyncpg
import numpy as np
from PIL import Image
from fashion_clip.fashion_clip import FashionCLIP

DB_URL = "postgresql://localhost/yow_lens_test"

print("Loading FashionCLIP...")
fashion_clip = FashionCLIP('fashion-clip')
print("✓ Ready\n")


def color_name_to_rgb(color_name: str) -> tuple:
    color_map = {
        'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
        'blue': (0, 0, 255), 'navy': (0, 0, 128), 'green': (0, 128, 0),
        'olive': (107, 142, 35), 'yellow': (255, 255, 0), 'orange': (255, 165, 0),
        'pink': (255, 192, 203), 'purple': (128, 0, 128), 'brown': (139, 69, 19),
        'beige': (245, 245, 220), 'cream': (255, 253, 208), 'gray': (128, 128, 128),
        'grey': (128, 128, 128), 'tan': (210, 180, 140), 'burgundy': (128, 0, 32),
        'khaki': (195, 176, 145), 'indigo': (75, 0, 130), 'teal': (0, 128, 128),
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
    color_words = ['olive', 'navy', 'burgundy', 'maroon', 'charcoal', 'teal', 'indigo',
                   'coral', 'gold', 'silver', 'khaki', 'beige', 'cream', 'tan',
                   'black', 'white', 'gray', 'grey', 'blue', 'red', 'green', 
                   'brown', 'pink', 'purple', 'yellow', 'orange']
    
    found_colors = []
    for color in color_words:
        pos = gemini_lower.find(color)
        if pos != -1:
            found_colors.append((pos, color))
    
    if found_colors:
        found_colors.sort(key=lambda x: x[0])
        return found_colors[0][1]
    
    return 'gray'


def delta_e(color1: tuple, color2: tuple) -> float:
    return np.sqrt(sum((a-b)**2 for a, b in zip(color1, color2)))


def build_rich_text_query(attributes: dict) -> str:
    """
    Build DEDUPED rich text query.
    """
    parts = []
    seen = set()  # Track words we've already added
    
    def add_unique(text):
        if not text or text in ['-', '?', 'null', 'none', 'None', '']:
            return
        # Split and add unique words
        words = text.lower().replace('_', ' ').split()
        for word in words:
            if word not in seen and len(word) > 2:
                parts.append(word)
                seen.add(word)
    
    # Color
    if attributes.get('color'):
        add_unique(attributes['color'])
    
    # Texture
    add_unique(attributes.get('texture', ''))
    
    # Distinctive features (most important!)
    features = attributes.get('distinctive_features', [])
    if features and isinstance(features, list):
        for feature in features[:4]:
            add_unique(feature)
    
    # Pattern
    add_unique(attributes.get('pattern', ''))
    
    # Sleeve/fit
    add_unique(attributes.get('sleeve_length', ''))
    add_unique(attributes.get('fit', ''))
    
    # Style keywords
    keywords = attributes.get('style_keywords', [])
    if keywords and isinstance(keywords, list):
        for kw in keywords[:3]:
            add_unique(kw)
    
    # Category last
    add_unique(attributes.get('category', ''))
    
    return ' '.join(parts)


# Pattern keywords
PATTERN_KEYWORDS = {
    'horizontal_stripes': ['horizontal stripe', 'breton', 'rugby', 'stripe'],
    'horizontal stripes': ['horizontal stripe', 'breton', 'rugby', 'stripe'],
    'vertical_stripes': ['vertical stripe', 'pinstripe', 'pin stripe'],
    'striped': ['stripe', 'striped', 'stripes'],
    'stripes': ['stripe', 'striped', 'stripes'],
    'plaid': ['plaid', 'check', 'checked', 'tartan'],
    'woven': ['woven', 'intrecciato', 'braided', 'weave'],
    'quilted': ['quilted', 'quilt', 'padded'],
}

PATTERN_EXCLUDES = {
    'horizontal_stripes': ['pinstripe', 'vertical'],
    'horizontal stripes': ['pinstripe', 'vertical'],
    'vertical_stripes': ['horizontal', 'breton', 'rugby'],
}

FEATURE_KEYWORDS = {
    'woven leather': ['woven', 'intrecciato', 'braided'],
    'intrecciato': ['woven', 'intrecciato', 'braided'],
    'horizontal stripes': ['stripe', 'striped', 'breton', 'rugby'],
    'crew neck': ['crew neck', 'crew-neck', 'crewneck'],
    'v-neck': ['v-neck', 'v neck', 'vneck'],
    'wide leg': ['wide leg', 'wide-leg'],
    'high waisted': ['high waist', 'high-waist', 'high rise'],
    'pleated': ['pleat', 'pleated'],
    'ribbed': ['ribbed', 'rib'],
    'ruffle': ['ruffle', 'ruffled', 'frill'],
    'lace': ['lace', 'lacy'],
    'quilted': ['quilted', 'quilt'],
}


def check_pattern_match(product_name: str, pattern: str) -> bool:
    if not pattern or pattern.lower() in ['solid', '-', '?', 'null', 'none', '']:
        return True
    
    pattern_lower = pattern.lower()
    product_name_lower = (product_name or '').lower()
    
    if pattern_lower in PATTERN_EXCLUDES:
        for exclude_kw in PATTERN_EXCLUDES[pattern_lower]:
            if exclude_kw in product_name_lower:
                return False
    
    if pattern_lower in PATTERN_KEYWORDS:
        for kw in PATTERN_KEYWORDS[pattern_lower]:
            if kw in product_name_lower:
                return True
        return False
    
    return True


def calculate_feature_boost(product_name: str, attributes: dict) -> tuple:
    product_name_lower = (product_name or '').lower()
    boost = 0.0
    matched = []
    
    features = attributes.get('distinctive_features', [])
    if features and isinstance(features, list):
        for feature in features:
            feature_lower = (feature or '').lower()
            
            if feature_lower in product_name_lower:
                boost += 0.10
                matched.append(feature)
                continue
            
            if feature_lower in FEATURE_KEYWORDS:
                for kw in FEATURE_KEYWORDS[feature_lower]:
                    if kw in product_name_lower:
                        boost += 0.10
                        matched.append(feature)
                        break
    
    texture = (attributes.get('texture', '') or '').lower()
    if texture and texture not in ['smooth', 'soft'] and texture in product_name_lower:
        boost += 0.05
        matched.append(f"texture:{texture}")
    
    keywords = attributes.get('style_keywords', [])
    if keywords and isinstance(keywords, list):
        for kw in keywords:
            kw_lower = (kw or '').lower()
            if kw_lower and len(kw_lower) > 3 and kw_lower in product_name_lower:
                boost += 0.03
                matched.append(f"style:{kw}")
    
    return min(boost, 0.30), matched  # Cap at 0.30


async def hybrid_search(
    image: Image.Image,
    attributes: dict = None,
    limit: int = 100,
    final_limit: int = 10,
    visual_weight: float = 0.55,
    text_weight: float = 0.35,
    color_weight: float = 0.10,
    filter_pattern: bool = True,
    min_results: int = 5,
) -> tuple:
    """
    V:55% T:35% C:10% + feature boosts
    Color weight reduced - Gemini sometimes gets colors wrong
    """
    
    text_query = build_rich_text_query(attributes) if attributes else ""
    
    gemini_color = attributes.get('color', '') if attributes else ''
    primary_color = extract_primary_color(gemini_color)
    query_color_rgb = color_name_to_rgb(primary_color)
    
    pattern = (attributes.get('pattern', '') if attributes else '').lower()
    
    img_embedding = fashion_clip.encode_images([image], batch_size=1)[0]
    img_emb_str = "[" + ",".join(map(str, img_embedding.tolist())) + "]"
    
    text_emb_str = None
    if text_query:
        text_embedding = fashion_clip.encode_text([text_query], batch_size=1)[0]
        text_emb_str = "[" + ",".join(map(str, text_embedding.tolist())) + "]"
    
    conn = await asyncpg.connect(DB_URL)
    
    where_clauses = []
    category = (attributes.get('category', '') if attributes else '').lower()
    
    if category:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM products WHERE category = '{category}'")
        if count and count > 0:
            where_clauses.append(f"category = '{category}'")
    
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    if text_emb_str:
        query = f"""
            SELECT 
                id, name, brand, price, category, color, image_url,
                1 - (embedding <=> '{img_emb_str}'::vector) as visual_sim,
                1 - (embedding <=> '{text_emb_str}'::vector) as text_sim
            FROM products
            {where_sql}
            ORDER BY (
                0.5 * (1 - (embedding <=> '{img_emb_str}'::vector)) +
                0.5 * (1 - (embedding <=> '{text_emb_str}'::vector))
            ) DESC
            LIMIT {limit}
        """
    else:
        query = f"""
            SELECT 
                id, name, brand, price, category, color, image_url,
                1 - (embedding <=> '{img_emb_str}'::vector) as visual_sim,
                0.0 as text_sim
            FROM products
            {where_sql}
            ORDER BY embedding <=> '{img_emb_str}'::vector
            LIMIT {limit}
        """
    
    results = await conn.fetch(query)
    await conn.close()
    
    scored_results = []
    filtered_out = 0
    
    for r in results:
        pattern_match = check_pattern_match(r['name'], pattern)
        
        if filter_pattern and not pattern_match:
            filtered_out += 1
            continue
        
        product_rgb = color_name_to_rgb(r['color'] or 'gray')
        color_distance = delta_e(query_color_rgb, product_rgb)
        color_sim = max(0, 1 - (color_distance / 441.67))
        
        feature_boost, matched = calculate_feature_boost(r['name'], attributes)
        
        combined = (
            visual_weight * float(r['visual_sim']) +
            text_weight * float(r['text_sim']) +
            color_weight * color_sim +
            feature_boost
        )
        
        scored_results.append({
            'id': r['id'],
            'name': r['name'],
            'brand': r['brand'],
            'price': float(r['price']) if r['price'] else 0,
            'category': r['category'],
            'color': r['color'],
            'image_url': r['image_url'],
            'visual_sim': float(r['visual_sim']),
            'text_sim': float(r['text_sim']),
            'color_sim': color_sim,
            'feature_boost': feature_boost,
            'matched_features': matched,
            'combined_score': combined,
            'pattern_match': pattern_match,
        })
    
    filter_used = 'pattern' if filter_pattern and pattern and pattern not in ['solid', '-', 'null'] else 'none'
    
    if len(scored_results) < min_results and filter_pattern:
        scored_results = []
        for r in results:
            product_rgb = color_name_to_rgb(r['color'] or 'gray')
            color_distance = delta_e(query_color_rgb, product_rgb)
            color_sim = max(0, 1 - (color_distance / 441.67))
            feature_boost, matched = calculate_feature_boost(r['name'], attributes)
            
            combined = (
                visual_weight * float(r['visual_sim']) +
                text_weight * float(r['text_sim']) +
                color_weight * color_sim +
                feature_boost
            )
            
            scored_results.append({
                'id': r['id'],
                'name': r['name'],
                'brand': r['brand'],
                'price': float(r['price']) if r['price'] else 0,
                'category': r['category'],
                'color': r['color'],
                'image_url': r['image_url'],
                'visual_sim': float(r['visual_sim']),
                'text_sim': float(r['text_sim']),
                'color_sim': color_sim,
                'feature_boost': feature_boost,
                'matched_features': matched,
                'combined_score': combined,
                'pattern_match': True,
            })
        filter_used = 'none (fallback)'
    
    scored_results.sort(key=lambda x: x['combined_score'], reverse=True)
    return scored_results[:final_limit], filter_used, filtered_out


async def search_outfit(image_path: str):
    from garment_analyzer import GarmentAnalyzer
    
    analyzer = GarmentAnalyzer()
    image = Image.open(image_path)
    
    print(f"🔍 Analyzing: {image_path}")
    print("="*80)
    
    items = analyzer.analyze_outfit(image)
    crops = analyzer.crop_items(image, items)
    
    print(f"\n📦 Detected {len(crops)} items\n")
    
    conn = await asyncpg.connect(DB_URL)
    cat_counts = await conn.fetch("SELECT category, COUNT(*) as cnt FROM products GROUP BY category")
    await conn.close()
    cat_counts_dict = {r['category']: r['cnt'] for r in cat_counts}
    
    print("📊 Products: " + ", ".join([f"{cat}:{cnt}" for cat, cnt in sorted(cat_counts_dict.items(), key=lambda x: -x[1])]))
    
    all_results = {}
    
    for crop_data in crops:
        attrs = crop_data['attributes']
        crop_img = crop_data['image']
        
        category = attrs.get('category', 'unknown').lower()
        products_available = cat_counts_dict.get(category, 0)
        
        text_query = build_rich_text_query(attrs)
        features = attrs.get('distinctive_features', [])
        keywords = attrs.get('style_keywords', [])
        
        print(f"\n{'='*70}")
        print(f"🏷️  {category.upper()}: {attrs.get('label', '?')}")
        
        if products_available == 0:
            print(f"   ⚠️  No {category} products")
        
        print(f"\n   Color: {attrs.get('color', '-')}")
        print(f"   Pattern: {attrs.get('pattern', '-')} | Texture: {attrs.get('texture', '-')}")
        
        if features:
            print(f"   ✨ Features: {', '.join(features)}")
        if keywords:
            print(f"   🏷️  Style: {', '.join(keywords)}")
        
        print(f"\n   📝 Query: \"{text_query}\"")
        print("-"*70)
        
        results, filter_used, filtered_out = await hybrid_search(
            image=crop_img,
            attributes=attrs,
            limit=100,
            final_limit=5,
            visual_weight=0.55,
            text_weight=0.35,
            color_weight=0.10,
            filter_pattern=True,
            min_results=5,
        )
        
        if filtered_out > 0:
            print(f"\n   🎨 Pattern filter: {filtered_out} removed")
        
        all_results[category] = {'results': results}
        
        print(f"\n   Top {len(results)} matches:\n")
        for i, r in enumerate(results):
            icon = "🎯" if r['combined_score'] > 0.60 else "✓" if r['combined_score'] > 0.50 else "○"
            
            boost_str = ""
            if r['feature_boost'] > 0:
                boost_str = f" +{r['feature_boost']:.2f}"
                if r['matched_features']:
                    boost_str += f" [{', '.join(r['matched_features'][:2])}]"
            
            print(f"   {i+1}. {icon} [{r['combined_score']:.3f}] {r['name'][:44]}...")
            print(f"      V:{r['visual_sim']:.2f} T:{r['text_sim']:.2f} C:{r['color_sim']:.2f}{boost_str}")
            print(f"      {r['brand']} | {r['color']} | ${r['price']:.2f}")
            print()
    
    return all_results


if __name__ == "__main__":
    import sys
    image_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/gavinwalker/Desktop/AI OUTFIT PICS/josefine vogt.jpeg"
    asyncio.run(search_outfit(image_path))
