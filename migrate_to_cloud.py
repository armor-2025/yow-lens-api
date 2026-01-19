"""
Migrate products from local PostgreSQL to Supabase + Pinecone
"""
import asyncio
import asyncpg
import psycopg2
from pinecone import Pinecone
import numpy as np

# Local database
LOCAL_DB = "postgresql://localhost/yow_lens_test"

# Cloud databases
SUPABASE_URL = "postgresql://postgres:1WFf3xVzY3HVaSRz@db.eayoasnkemanrguvfuch.supabase.co:5432/postgres"
PINECONE_API_KEY = "pcsk_3e2bNu_ESZ77iM7pxPbnFrb1GgH4hRZrpeLmwrw6TWoQg8Rd8QFvP3NXx2E3Y5ohtD5W8r"
PINECONE_INDEX = "yow-products"

async def migrate():
    print("Connecting to local database...")
    local_conn = await asyncpg.connect(LOCAL_DB)
    
    # Get all products with embeddings
    products = await local_conn.fetch("""
        SELECT id, name, brand, price, color, category, subcategory, 
               image_url, product_url, embedding
        FROM products 
        WHERE embedding IS NOT NULL
    """)
    print(f"Found {len(products)} products with embeddings")
    
    await local_conn.close()
    
    # Connect to Supabase
    print("\nConnecting to Supabase...")
    cloud_conn = psycopg2.connect(SUPABASE_URL)
    cur = cloud_conn.cursor()
    
    # Connect to Pinecone
    print("Connecting to Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)
    
    # Migrate in batches
    batch_size = 100
    pinecone_vectors = []
    
    print(f"\nMigrating {len(products)} products...")
    
    for i, p in enumerate(products):
        # Insert into Supabase
        cur.execute("""
            INSERT INTO products (id, name, brand, price, color, category, subcategory, image_url, product_url, retailer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'asos')
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                brand = EXCLUDED.brand,
                price = EXCLUDED.price,
                color = EXCLUDED.color,
                category = EXCLUDED.category,
                subcategory = EXCLUDED.subcategory,
                image_url = EXCLUDED.image_url,
                product_url = EXCLUDED.product_url
        """, (p['id'], p['name'], p['brand'], float(p['price']) if p['price'] else 0, 
              p['color'], p['category'], p['subcategory'], p['image_url'], p['product_url']))
        
        # Convert embedding to list of floats
        embedding = p['embedding']
        if isinstance(embedding, str):
            # Parse string like "[0.1, 0.2, ...]"
            embedding = [float(x) for x in embedding.strip('[]').split(',')]
        elif hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        else:
            embedding = [float(x) for x in embedding]
        
        # Prepare Pinecone vector
        pinecone_vectors.append({
            "id": p['id'],
            "values": embedding,
            "metadata": {
                "category": p['category'] or "",
                "subcategory": p['subcategory'] or "",
                "color": p['color'] or "",
                "brand": p['brand'] or ""
            }
        })
        
        # Upsert to Pinecone in batches
        if len(pinecone_vectors) >= batch_size:
            index.upsert(vectors=pinecone_vectors)
            pinecone_vectors = []
            print(f"  Migrated {i+1}/{len(products)}...")
    
    # Final batch
    if pinecone_vectors:
        index.upsert(vectors=pinecone_vectors)
    
    cloud_conn.commit()
    cur.close()
    cloud_conn.close()
    
    # Verify
    stats = index.describe_index_stats()
    print(f"\n✅ Migration complete!")
    print(f"   Pinecone vectors: {stats.total_vector_count}")

asyncio.run(migrate())
