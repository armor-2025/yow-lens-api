"""
Generate FashionCLIP Embeddings from local images
"""
import argparse
import json
import numpy as np
from pathlib import Path
from PIL import Image
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def load_fashion_clip():
    logger.info("Loading FashionCLIP model...")
    from fashion_clip.fashion_clip import FashionCLIP
    model = FashionCLIP('fashion-clip')
    logger.info("✓ FashionCLIP loaded")
    return model

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--products-dir', type=str, default='./asos_products')
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()
    
    products_dir = Path(args.products_dir)
    data_dir = products_dir / "data"
    images_dir = products_dir / "images"
    
    # Load products
    with open(data_dir / "products.json") as f:
        products = json.load(f)["products"]
    logger.info(f"Loaded {len(products)} products")
    
    # Load model
    fashion_clip = load_fashion_clip()
    
    embeddings = []
    product_ids = []
    failed = 0
    
    # Process in batches
    for i in range(0, len(products), args.batch_size):
        batch = products[i:i + args.batch_size]
        
        valid_images = []
        valid_ids = []
        
        for p in batch:
            img_path = images_dir / f"{p['id']}.jpg"
            if img_path.exists():
                try:
                    img = Image.open(img_path).convert('RGB')
                    valid_images.append(img)
                    valid_ids.append(p['id'])
                except:
                    failed += 1
            else:
                failed += 1
        
        if valid_images:
            batch_embeddings = fashion_clip.encode_images(valid_images, batch_size=len(valid_images))
            embeddings.extend(batch_embeddings)
            product_ids.extend(valid_ids)
        
        processed = min(i + args.batch_size, len(products))
        if processed % 200 == 0 or processed == len(products):
            logger.info(f"Progress: {processed}/{len(products)} (✓ {len(embeddings)}, ✗ {failed})")
    
    embeddings = np.array(embeddings)
    
    # Save embeddings
    np.savez_compressed(
        data_dir / "embeddings.npz",
        embeddings=embeddings,
        product_ids=np.array(product_ids)
    )
    logger.info(f"Saved embeddings to {data_dir}/embeddings.npz")
    
    # Save products with embedding index
    id_to_idx = {pid: idx for idx, pid in enumerate(product_ids)}
    products_with_emb = []
    for p in products:
        if p['id'] in id_to_idx:
            p['embedding_idx'] = id_to_idx[p['id']]
            products_with_emb.append(p)
    
    with open(data_dir / "products_with_embeddings.json", "w") as f:
        json.dump({
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'count': len(products_with_emb),
                'embedding_dim': 512
            },
            'products': products_with_emb
        }, f)
    
    print("\n" + "="*60)
    print("EMBEDDING GENERATION COMPLETE")
    print("="*60)
    print(f"Products: {len(product_ids)}")
    print(f"Embeddings shape: {embeddings.shape}")
    print("="*60)

if __name__ == "__main__":
    main()
