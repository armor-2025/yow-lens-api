"""Test with different pose and background"""
from google import genai
from google.genai import types
from PIL import Image
import base64
import io
import os
import random

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyARJ5pKG26LhsrfX9pidnLjJlYrY3jIEOA')
client = genai.Client(api_key=GEMINI_API_KEY)

# Load test image
img = Image.open("test_original_dress.jpg")
img_bytes = io.BytesIO()
img.save(img_bytes, format='JPEG')
img_b64 = base64.b64encode(img_bytes.getvalue()).decode()

# Random variations
ethnicities = ["Asian", "Black", "Latina", "Middle Eastern", "South Asian", "Scandinavian"]
poses = ["walking confidently", "sitting on a chair", "leaning against a wall", "mid-stride walking", "turning to look over shoulder", "adjusting her hair"]
backgrounds = ["busy city street", "outdoor garden with flowers", "modern apartment interior", "beach boardwalk at sunset", "trendy coffee shop", "art gallery with white walls"]

model_desc = random.choice(ethnicities)
pose = random.choice(poses)
background = random.choice(backgrounds)

print(f"🎭 Model: {model_desc}")
print(f"🕺 Pose: {pose}")
print(f"🏙️ Background: {background}")
print("\nGenerating VTO...")

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=base64.b64decode(img_b64), mime_type="image/jpeg"),
            f"""Generate a realistic photo of a {model_desc} woman wearing this EXACT dress.

CRITICAL - DRESS MUST BE IDENTICAL:
- Same color
- Same style and cut
- Same fabric texture
- Same details (wrap top, draped skirt, etc.)

SCENE:
- Pose: {pose}
- Location: {background}
- Natural lighting
- Candid street style photography feel
- Full body or 3/4 shot showing the dress clearly

Generate now."""
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            temperature=0.9,
        )
    )
    
    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                img_data = part.inline_data.data
                result = Image.open(io.BytesIO(img_data))
                result.save("test_vto_hard.jpg")
                print("✓ Saved to test_vto_hard.jpg")
                os.system("open test_vto_hard.jpg test_original_dress.jpg")
                break
    else:
        print("No image generated")
                
except Exception as e:
    print(f"Error: {e}")
