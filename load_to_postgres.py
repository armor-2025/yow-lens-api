"""
Load products + embeddings into PostgreSQL with pgvector
"""
import asyncio
import json
import numpy as np
from pathlib import Path
import asyncpg
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = "postgresql://localhost/yow_lens_test"

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS products;

CREATE TABLE products (
    id TEXT PRIMARY KEY,
    external_id TEXT,
    name TEXT NOT NULL,
    brand TEXT,
    price DECIMAL(10,2),
    sale_price DECIMAL(10,2),
    currency TEXT DEFAULT 'USD',
    retailer TEXT NOT NULL,
    product_url TEXT,
    image_url TEXT NOT NULL,
    category TEXT,
    subcategory TEXT,
    color TEXT,
    gender TEXT,
    embedding vector(512),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_embedding ON products USING hnsw (embedding vector_cosine_ops);
"""

async def main():
    products_dir = Path("./asos_products")
    data_dir = products_dir / "data"
    
    # Load data
    with open(data_dir / "products_with_embeddings.json") as f:
        data = json.load(f)
    products = data["products"]
    
    emb_data = np.load(data_dir / "embeddings.npz")
    embeddings = emb_data["embeddings"]
    product_ids = emb_data["product_ids"].tolist()
    
    logger.info(f"Loaded {len(products)} products, {len(embeddings)} embeddings")
    
    # Create ID to embedding map
    id_to_emb = {pid: embeddings[i] for i, pid in enumerate(product_ids)}
    
    # Connect and setup
    conn = await asyncpg.connect(DB_URL)
    logger.info("Connected to PostgreSQL")
    
    await conn.execute(SCHEMA)
    logger.info("Schema created")
    
    # Insert products
    inserted = 0
    for p in products:
        emb = id_to_emb.get(p["id"])
        if emb is None:
            continue
        
        emb_str = "[" + ",".join(map(str, emb.tolist())) + "]"
        
        await conn.execute("""
            INSERT INTO products (id, external_id, name, brand, price, sale_price, currency,
                                  retailer, product_url, image_url, category, subcategory, 
                                  color, gender, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::vector)
        """, p["id"], p.get("external_id"), p["name"], p.get("brand"), 
            p.get("price"), p.get("sale_price"), p.get("currency", "USD"),
            p.get("retailer", "asos"), p.get("product_url"), p["image_url"],
            p.get("category"), p.get("subcategory"), p.get("color"), p.get("gender"),
            emb_str)
        
        inserted += 1
        if inserted % 500 == 0:
            logger.info(f"Inserted {inserted} products...")
    
    logger.info(f"Done! Inserted {inserted} products")
    
    # Test query
    result = await conn.fetchrow("SELECT COUNT(*) FROM products")
    logger.info(f"Total products in DB: {result[0]}")
    
    await conn.close()
    
    print("\n" + "="*60)
    print("DATABASE LOAD COMPLETE")
    print("="*60)
    print(f"Products loaded: {inserted}")
    print(f"Database: {DB_URL}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
