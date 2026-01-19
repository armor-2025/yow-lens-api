"""
Process new ASOS products:
1. Download images
2. Generate FashionCLIP embeddings
3. Add to PostgreSQL database
"""
import json
import os
import requests
import asyncio
import asyncpg
from PIL import Image
import io
from fashion_clip.fashion_clip import FashionCLIP
from tqdm import tqdm
import time

DB_URL = "postgresql://localhost/yow_lens_test"
IMAGE_DIR = "product_images"

os.makedirs(IMAGE_DIR, exist_ok=True)

print("Loading FashionCLIP...")
fashion_clip = FashionCLIP('fashion-clip')
print("✓ Ready\n")


def download_image(url: str, product_id: str) -> str:
    """Download image and return local path"""
    filepath = f"{IMAGE_DIR}/{product_id}.jpg"
    
    if os.path.exists(filepath):
        return filepath
    
    try:
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        if response.status_code == 200:
            img = Image.open(io.BytesIO(response.content))
            img = img.convert('RGB')
            img.save(filepath, 'JPEG', quality=85)
            return filepath
    except Exception as e:
        pass
    
    return None


def generate_embedding(image_path: str) -> list:
    """Generate FashionCLIP embedding for an image"""
    try:
        img = Image.open(image_path)
        embedding = fashion_clip.encode_images([img], batch_size=1)[0]
        return embedding.tolist()
    except Exception as e:
        return None


async def add_to_database(products: list):
    """Add products with embeddings to PostgreSQL"""
    conn = await asyncpg.connect(DB_URL)
    
    # Check existing products
    existing = await conn.fetch("SELECT id FROM products")
    existing_ids = {r['id'] for r in existing}
    
    new_products = [p for p in products if p['id'] not in existing_ids and p.get('embedding')]
    
    print(f"\nAdding {len(new_products)} new products to database...")
    
    for p in tqdm(new_products):
        try:
            emb_str = "[" + ",".join(map(str, p['embedding'])) + "]"
            
            await conn.execute("""
                INSERT INTO products (id, name, brand, price, category, color, image_url, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
                ON CONFLICT (id) DO NOTHING
            """, p['id'], p['name'], p['brand'], p['price'], p['category'], 
                p['color'], p['image_url'], emb_str)
        except Exception as e:
            print(f"Error adding {p['id']}: {e}")
    
    await conn.close()
    print("✅ Database updated!")


async def main():
    # Load products
    with open('asos_products_full.json') as f:
        products = json.load(f)
    
    print(f"Processing {len(products)} products...")
    
    # Download images and generate embeddings
    processed = []
    
    for p in tqdm(products, desc="Downloading & embedding"):
        # Download image
        image_path = download_image(p['image_url'], p['id'])
        
        if not image_path:
            continue
        
        # Generate embedding
        embedding = generate_embedding(image_path)
        
        if embedding:
            p['embedding'] = embedding
            p['local_image'] = image_path
            processed.append(p)
        
        # Small delay to be nice to servers
        time.sleep(0.05)
    
    print(f"\n✅ Processed {len(processed)} products with embeddings")
    
    # Save processed data
    with open('asos_products_with_embeddings.json', 'w') as f:
        json.dump(processed, f)
    
    # Add to database
    await add_to_database(processed)
    
    # Final stats
    conn = await asyncpg.connect(DB_URL)
    stats = await conn.fetch("""
        SELECT category, COUNT(*) as cnt 
        FROM products 
        GROUP BY category 
        ORDER BY cnt DESC
    """)
    await conn.close()
    
    print("\n📊 Database stats:")
    total = 0
    for r in stats:
        print(f"   {r['category']}: {r['cnt']}")
        total += r['cnt']
    print(f"\n   TOTAL: {total} products")


if __name__ == "__main__":
    asyncio.run(main())
