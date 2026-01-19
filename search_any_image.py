import asyncio
import asyncpg
import sys
from PIL import Image
from fashion_clip.fashion_clip import FashionCLIP

DB_URL = "postgresql://localhost/yow_lens_test"

print("Loading FashionCLIP...")
fashion_clip = FashionCLIP('fashion-clip')
print("✓ Ready\n")

async def search(image_path: str, category: str = None, limit: int = 10):
    img = Image.open(image_path).convert('RGB')
    embedding = fashion_clip.encode_images([img], batch_size=1)[0]
    emb_str = "[" + ",".join(map(str, embedding.tolist())) + "]"
    
    conn = await asyncpg.connect(DB_URL)
    
    if category:
        results = await conn.fetch(f"""
            SELECT name, brand, price, category, color, image_url,
                   1 - (embedding <=> '{emb_str}'::vector) as similarity
            FROM products
            WHERE category = '{category}'
            ORDER BY embedding <=> '{emb_str}'::vector
            LIMIT {limit}
        """)
    else:
        results = await conn.fetch(f"""
            SELECT name, brand, price, category, color, image_url,
                   1 - (embedding <=> '{emb_str}'::vector) as similarity
            FROM products
            ORDER BY embedding <=> '{emb_str}'::vector
            LIMIT {limit}
        """)
    
    await conn.close()
    return results

async def main():
    if len(sys.argv) < 2:
        print("Usage: python search_any_image.py <image_path> [category]")
        return
    
    image_path = sys.argv[1]
    category = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"🔍 Searching: {image_path}")
    if category:
        print(f"   Category: {category}")
    print("="*70)
    
    results = await search(image_path, category, limit=10)
    
    print(f"\nTop {len(results)} matches:\n")
    for i, r in enumerate(results):
        print(f"{i+1}. [{r['similarity']:.3f}] {r['name'][:55]}...")
        print(f"   {r['brand']} | {r['category']} | {r['color']} | ${r['price']}")
        print()

asyncio.run(main())
