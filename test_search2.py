import asyncio
import asyncpg
from PIL import Image
from pathlib import Path
from fashion_clip.fashion_clip import FashionCLIP

DB_URL = "postgresql://localhost/yow_lens_test"
fashion_clip = FashionCLIP('fashion-clip')

async def search(image_path: str, limit: int = 5):
    img = Image.open(image_path).convert('RGB')
    embedding = fashion_clip.encode_images([img], batch_size=1)[0]
    emb_str = "[" + ",".join(map(str, embedding.tolist())) + "]"
    
    conn = await asyncpg.connect(DB_URL)
    results = await conn.fetch(f"""
        SELECT name, brand, price, category, color,
               1 - (embedding <=> '{emb_str}'::vector) as similarity
        FROM products
        ORDER BY embedding <=> '{emb_str}'::vector
        LIMIT {limit}
    """)
    await conn.close()
    return results

async def main():
    images_dir = Path("./asos_products/images")
    images = list(images_dir.glob("*.jpg"))
    
    # Test with a few different products
    for idx in [0, 100, 500, 1000]:
        test_image = images[idx]
        print(f"\n{'='*60}")
        print(f"🔍 Query: {test_image.name}")
        
        results = await search(str(test_image), limit=3)
        for i, r in enumerate(results):
            sim = f"{r['similarity']:.3f}"
            print(f"  {i+1}. [{sim}] {r['category']} - {r['brand']} - {r['color']}")

asyncio.run(main())
