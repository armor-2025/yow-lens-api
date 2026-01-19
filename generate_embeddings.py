"""
Generate FashionCLIP Embeddings for Downloaded Products
"""

import argparse
import json
import numpy as np
from pathlib import Path
from PIL import Image
import logging
from datetime import datetime
import httpx
import asyncio
import io

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Headers to mimic browser request
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.asos.com/',
}

def load_fashion_clip():
    logger.info("Loading FashionCLIP model (first time takes ~30s)...")
    from fashion_clip.fashion_clip import FashionCLIP
    model = FashionCLIP('fashion-clip')
    logger.info("✓ FashionCLIP loaded")
    return model

async def download_image(url: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> Image.Image:
    """Download image from URL with browser headers"""
    async with semaphore:
        try:
            response = await client.get(url, headers=HEADERS)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert('RGB')
            await asyncio.sleep(0.1)  # Small delay to avoid rate limiting
            return img
        except Exception as e:
            return None

async def generate_embeddings_async(products_dir: Path, fashion_clip, batch_size: int = 32):
    """Generate embeddings for all products"""
    
    data_dir = products_dir / "data"
    products_file = data_dir / "products.json"
    
    with open(products_file, 'r') as f:
        data = json.load(f)
    products = data['products']
    
    logger.info(f"Loaded {len(products)} products")
    
    embeddings = []
    product_ids = []
    failed = 0
    
    semaphore = asyncio.Semaphore(10)  # Limit concurrent downloads
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            
            # Download images concurrently
            tasks = [download_image(p.get('image_url', ''), client, semaphore) for p in batch]
            images = await asyncio.gather(*tasks)
            
            # Filter valid images
            valid_images = []
            valid_ids = []
            for p, img in zip(batch, images):
                if img is not None:
                    valid_images.append(img)
                    valid_ids.append(p['id'])
                else:
                    failed += 1
            
            if valid_images:
                # Generate embeddings
                batch_embeddings = fashion_clip.encode_images(valid_images)
                embeddings.extend(batch_embeddings)
                product_ids.extend(valid_ids)
            
            processed = min(i + batch_size, len(products))
            logger.info(f"Progress: {processed}/{len(products)} (✓ {len(embeddings)}, ✗ {failed})")
    
    return np.array(embeddings), product_ids, products

def main():
    parser = argparse.ArgumentParser(description='Generate FashionCLIP embeddings')
    parser.add_argument('--products-dir', type=str, default='./asos_products')
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()
    
    products_dir = Path(args.products_dir)
    data_dir = products_dir / "data"
    
    if not (data_dir / "products.json").exists():
        print(f"Error: No products.json found in {data_dir}")
        return
    
    # Load model
    fashion_clip = load_fashion_clip()
    
    # Generate embeddings
    embeddings, product_ids, products = asyncio.run(
        generate_embeddings_async(products_dir, fashion_clip, args.batch_size)
    )
    
    # Save embeddings
    embeddings_file = data_dir / "embeddings.npz"
    np.savez_compressed(embeddings_file, embeddings=embeddings, product_ids=np.array(product_ids))
    logger.info(f"Saved embeddings to {embeddings_file}")
    
    # Save products with embedding indices
    id_to_idx = {pid: idx for idx, pid in enumerate(product_ids)}
    products_with_emb = []
    for p in products:
        if p['id'] in id_to_idx:
            p_copy = p.copy()
            p_copy['embedding_idx'] = id_to_idx[p['id']]
            products_with_emb.append(p_copy)
    
    output = {
        'metadata': {
            'created_at': datetime.now().isoformat(),
            'count': len(products_with_emb),
            'embedding_dim': embeddings.shape[1] if len(embeddings) > 0 else 512,
        },
        'products': products_with_emb
    }
    
    products_emb_file = data_dir / "products_with_embeddings.json"
    with open(products_emb_file, 'w') as f:
        json.dump(output, f)
    
    logger.info(f"Saved {len(products_with_emb)} products to {products_emb_file}")
    
    print("\n" + "="*60)
    print("EMBEDDING GENERATION COMPLETE")
    print("="*60)
    print(f"Products: {len(product_ids)}")
    print(f"Embedding shape: {embeddings.shape}")
    print("="*60)

if __name__ == "__main__":
    main()
