"""
Set up Supabase tables and Pinecone index for YOW Lens
"""
import psycopg2
from pinecone import Pinecone

# Supabase (PostgreSQL)
DATABASE_URL = "postgresql://postgres:1WFf3xVzY3HVaSRz@db.eayoasnkemanrguvfuch.supabase.co:5432/postgres"

# Pinecone
PINECONE_API_KEY = "pcsk_3e2bNu_ESZ77iM7pxPbnFrb1GgH4hRZrpeLmwrw6TWoQg8Rd8QFvP3NXx2E3Y5ohtD5W8r"
PINECONE_INDEX = "yow-products"

print("Setting up Supabase...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Create products table
cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        brand TEXT,
        price DECIMAL(10,2),
        color TEXT,
        category TEXT,
        subcategory TEXT,
        image_url TEXT,
        product_url TEXT,
        retailer TEXT DEFAULT 'asos',
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
    CREATE INDEX IF NOT EXISTS idx_products_retailer ON products(retailer);
""")

conn.commit()
print("✅ Supabase products table created!")

cur.close()
conn.close()

print("\nChecking Pinecone...")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)
stats = index.describe_index_stats()
print(f"✅ Pinecone index ready! Vectors: {stats.total_vector_count}")

print("\n🎉 Cloud databases ready!")
