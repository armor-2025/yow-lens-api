"""
Test YOW Lens visual search
"""
import asyncio
import asyncpg
import numpy as np
from PIL import Image
from pathlib import Path

DB_URL = "postgresql://localhost/yow_lens_test"

# Load FashionCLIP
print("Loading FashionCLIP...")
from fashion_clip.fashion_clip import FashionCLIP
fashion_clip = FashionCLIP('fashion-clip')
print("✓ Ready")

async def search_by_image(image_path: str, limit: int = 5):
    """Search for similar products"""
    
    # Load and encode image
    img = Image.open(image_path).convert('RGB')
    embedding = fashion_clip.encode_images([img], batch_size=1)[0]
    emb_str = "[" + ",".join(map(str, embedding.tolist())) + "]"
    
    conn = await asyncpg.connect(DB_URL)
    
    results = await conn.fetch(f"""
        SELECT id, name, brand, price, category, color, image_url,
               1 - (embedding <=> '{emb_str}'::vector) as similarity
        FROM products
        ORDER BY embedding <=> '{emb_str}'::vector
        LIMIT {limit}
    """)
    
    await conn.close()
    return results

async def test_with_product():
    """Test search using an existing product image"""
    
    # Pick a random product image to search with
    images_dir = Path("./asos_products/images")
    test_image = list(images_dir.glob("*.jpg"))[42]
    
    print(f"\n🔍 Searching with: {test_image.name}")
    print("="*60)
    
    results = await search_by_image(str(test_image), limit=5)
    
    print(f"\nTop 5 matches:")
    for i, r in enumerate(results):
        print(f"\n{i+1}. {r['name'][:60]}...")
        print(f"   Brand: {r['brand']} | Category: {r['category']} | Color: {r['color']}")
        print(f"   Price: ${r['price']} | Similarity: {r['similarity']:.3f}")

if __name__ == "__main__":
    asyncio.run(test_with_product())
