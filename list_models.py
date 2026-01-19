from google import genai
import os

client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY', 'AIzaSyARJ5pKG26LhsrfX9pidnLjJlYrY3jIEOA'))

print("Available models with image generation:\n")
for model in client.models.list():
    name = model.name
    if 'flash' in name.lower() or 'image' in name.lower():
        print(f"  {name}")
