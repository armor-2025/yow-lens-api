"""
Fast parallel image downloader + embedding generator
Uses ThreadPool for downloads, then batch embeddings
"""
import json
import os
import requests
import asyncio
import asyncpg
from PIL import Image
import io
from fashion_clip.fashion_clip import FashionCLIP
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time

DB_URL = "postgresql://localhost/yow_lens_test"
IMAGE_DIR = "product_images"

os.makedirs(IMAGE_DIR, exist_ok=True)

print("Loading FashionCLIP...")
fashion_clip = FashionCLIP('fashion-clip')
print("✓ Ready\n")


def download_image(product: dict) -> dict:
    """Download single image, return product with local path"""
    product_id = product['id']
    filepath = f"{IMAGE_DIR}/{product_id}.jpg"
    
    # Skip if already downloaded
    if os.path.exists(filepath):
        product['local_image'] = filepath
        return product
    
    try:
        response = requests.get(
            product['image_url'], 
            timeout=10, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        if response.status_code == 200:
            img = Image.open(io.BytesIO(response.content))
            img = img.convert('RGB')
            img.save(filepath, 'JPEG', quality=85)
            product['local_image'] = filepath
            return product
    except:
        pass
    
    return None


def generate_embeddings_batch(products: list, batch_size: int = 32) -> list:
    """Generate embeddings in batches for speed"""
    results = []
    
    for i in tqdm(range(0, len(products), batch_size), desc="Generating embeddings"):
        batch = products[i:i+batch_size]
        
        # Load images
        images = []
        valid_products = []
        
        for p in batch:
            try:
                img = Image.open(p['local_image'])
                images.append(img)
                valid_products.append(p)
            except:
                continue
        
        if not images:
            continue
        
        # Batch encode
        try:
            embeddings = fashion_clip.encode_images(images, batch_size=len(images))
            
            for p, emb in zip(valid_products, embeddings):
                p['embedding'] = emb.tolist()
                results.append(p)
        except Exception as e:
            print(f"Batch error: {e}")
            continue
    
    return results


async def add_to_database(products: list):
    """Add products to PostgreSQL"""
    conn = await asyncpg.connect(DB_URL)
    
    # Get existing IDs
    existing = await conn.fetch("SELECT id FROM products")
    existing_ids = {r['id'] for r in existing}
    
    new_products = [p for p in products if p['id'] not in existing_ids]
    
    print(f"\nAdding {len(new_products)} new products to database...")
    
    added = 0
    for p in tqdm(new_products, desc="Inserting"):
        try:
            emb_str = "[" + ",".join(map(str, p['embedding'])) + "]"
            
            await conn.execute("""
                INSERT INTO products (id, name, brand, price, category, color, image_url, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
                ON CONFLICT (id) DO NOTHING
            """, p['id'], p['name'], p['brand'], p['price'], p['category'], 
                p['color'], p['image_url'], emb_str)
            added += 1
        except Exception as e:
            pass
    
    await conn.close()
    print(f"✅ Added {added} products to database")


async def main():
    # Load products
    with open('asos_products_full.json') as f:
        products = json.load(f)
    
    print(f"Total products to process: {len(products)}")
    
    # Check already downloaded
    already_downloaded = set()
    for f in os.listdir(IMAGE_DIR):
        if f.endswith('.jpg'):
            already_downloaded.add(f.replace('.jpg', ''))
    
    print(f"Already downloaded: {len(already_downloaded)}")
    
    to_download = [p for p in products if p['id'] not in already_downloaded]
    already_have = [p for p in products if p['id'] in already_downloaded]
    
    # Add local path to already downloaded
    for p in already_have:
        p['local_image'] = f"{IMAGE_DIR}/{p['id']}.jpg"
    
    print(f"Need to download: {len(to_download)}")
    
    # Parallel download with 20 threads
    downloaded = list(already_have)
    
    if to_download:
        print(f"\n📥 Downloading {len(to_download)} images (20 threads)...")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(download_image, p): p for p in to_download}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Downloading"):
                result = future.result()
                if result and result.get('local_image'):
                    downloaded.append(result)
    
    print(f"\n✅ Total images ready: {len(downloaded)}")
    
    # Filter to only those with images
    with_images = [p for p in downloaded if p.get('local_image') and os.path.exists(p.get('local_image', ''))]
    print(f"Valid images: {len(with_images)}")
    
    # Generate embeddings in batches
    print(f"\n🧠 Generating embeddings...")
    with_embeddings = generate_embeddings_batch(with_images, batch_size=32)
    
    print(f"\n✅ Products with embeddings: {len(with_embeddings)}")
    
    # Save checkpoint
    with open('asos_products_with_embeddings.json', 'w') as f:
        json.dump(with_embeddings, f)
    print("Saved to asos_products_with_embeddings.json")
    
    # Add to database
    await add_to_database(with_embeddings)
    
    # Final stats
    conn = await asyncpg.connect(DB_URL)
    stats = await conn.fetch("""
        SELECT category, COUNT(*) as cnt 
        FROM products 
        GROUP BY category 
        ORDER BY cnt DESC
    """)
    total = await conn.fetchval("SELECT COUNT(*) FROM products")
    await conn.close()
    
    print("\n" + "="*50)
    print("FINAL DATABASE STATS")
    print("="*50)
    print(f"Total products: {total}")
    print("\nBy category:")
    for r in stats:
        print(f"  {r['category']}: {r['cnt']}")


if __name__ == "__main__":
    asyncio.run(main())
