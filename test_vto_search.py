"""
Test: Can YOW Lens find the same item when worn by a different model?
"""
import asyncio
import asyncpg
from google import genai
from google.genai import types
from PIL import Image
from pathlib import Path
import base64
import io
import os

# Config
DB_URL = "postgresql://localhost/yow_lens_test"
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyARJ5pKG26LhsrfX9pidnLjJlYrY3jIEOA')

print("Loading FashionCLIP...")
from fashion_clip.fashion_clip import FashionCLIP
fashion_clip = FashionCLIP('fashion-clip')
print("✓ FashionCLIP Ready")

print("Configuring Gemini...")
client = genai.Client(api_key=GEMINI_API_KEY)
print("✓ Gemini Ready\n")

async def get_random_dress():
    conn = await asyncpg.connect(DB_URL)
    result = await conn.fetchrow("""
        SELECT id, name, brand, color, image_url 
        FROM products 
        WHERE category = 'dress'
        ORDER BY RANDOM()
        LIMIT 1
    """)
    await conn.close()
    return result

async def search(embedding, limit=5):
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

async def main():
    # Step 1: Get a random dress
    print("="*70)
    print("STEP 1: Selecting a random dress from database...")
    dress = await get_random_dress()
    print(f"\n📦 Original Product:")
    print(f"   ID: {dress['id']}")
    print(f"   Name: {dress['name'][:60]}...")
    print(f"   Brand: {dress['brand']} | Color: {dress['color']}")
    
    # Load original
    original_img_path = Path(f"./asos_products/images/{dress['id']}.jpg")
    original_img = Image.open(original_img_path)
    original_img.save("test_original_dress.jpg")
    print(f"   ✓ Saved original to: test_original_dress.jpg")
    
    # Step 2: Generate VTO
    print("\n" + "="*70)
    print("STEP 2: Generating VTO with Gemini 2.5 Flash...")
    
    # Convert to base64
    img_bytes = io.BytesIO()
    original_img.save(img_bytes, format='JPEG')
    img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
    
    prompt = f"""Generate a realistic fashion photo of a young woman model wearing this exact dress.
    
DRESS DETAILS:
- Color: {dress['color']}
- The dress must look EXACTLY like the reference image
- Same color, same style, same details

PHOTO REQUIREMENTS:
- Professional studio photo with neutral grey backdrop
- Full body shot showing the complete dress
- Model standing in a natural pose
- High quality fashion photography

Generate the image now."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-05-20",
            contents=[
                types.Part.from_bytes(data=base64.b64decode(img_b64), mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                temperature=0.7,
            )
        )
        
        vto_img = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    img_data = part.inline_data.data
                    vto_img = Image.open(io.BytesIO(img_data))
                    vto_img.save("test_vto_dress.jpg")
                    print("   ✓ Saved VTO image to: test_vto_dress.jpg")
                    break
        
        if not vto_img:
            print("   ✗ No image generated, using original")
            vto_img = original_img
            
    except Exception as e:
        print(f"   ✗ Gemini error: {e}")
        print("   Using original image for test")
        vto_img = original_img
    
    # Step 3: Search
    print("\n" + "="*70)
    print("STEP 3: Searching with both images...")
    
    print("\n🔍 Search with ORIGINAL product image:")
    orig_emb = fashion_clip.encode_images([original_img], batch_size=1)[0]
    orig_results = await search(orig_emb, limit=5)
    
    for i, r in enumerate(orig_results):
        match = "✓ EXACT" if r['id'] == dress['id'] else ""
        print(f"   {i+1}. [{r['similarity']:.3f}] {r['name'][:45]}... {match}")
    
    print("\n🔍 Search with VTO image (model wearing dress):")
    vto_emb = fashion_clip.encode_images([vto_img], batch_size=1)[0]
    vto_results = await search(vto_emb, limit=5)
    
    found = False
    for i, r in enumerate(vto_results):
        match = ""
        if r['id'] == dress['id']:
            match = "✓ FOUND!"
            found = True
        print(f"   {i+1}. [{r['similarity']:.3f}] {r['name'][:45]}... {match}")
    
    print("\n" + "="*70)
    if found:
        rank = next(i+1 for i, r in enumerate(vto_results) if r['id'] == dress['id'])
        print(f"✅ SUCCESS! Found original at rank #{rank}")
    else:
        print("❌ Original not in top 5 (but similar items found)")
    print("="*70)
    
    # Open images for visual comparison
    print("\n📷 Opening images for comparison...")
    os.system("open test_original_dress.jpg test_vto_dress.jpg")

asyncio.run(main())
