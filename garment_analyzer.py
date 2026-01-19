"""
YOW Lens - Garment Analyzer v7
Better color detection + material accuracy
"""
import os
import json
import base64
import io
from PIL import Image, ImageDraw
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

class GarmentAnalyzer:
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = "gemini-2.0-flash"
    
    def analyze_outfit(self, image: Image.Image) -> list:
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='JPEG')
        img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
        
        prompt = """Analyze this outfit image. For each fashion item, extract detailed attributes.

Return JSON array ONLY.

{
  "label": "detailed description",
  "box_2d": [ymin, xmin, ymax, xmax],
  "category": "top|bottom|dress|jacket|coat|shoes|bag|accessory|sunglasses",
  "subcategory": "specific type",
  "color": "ACCURATE color - see guidance below",
  "material": "ACCURATE material - see guidance below", 
  "pattern": "pattern type",
  "sleeve_length": "sleeveless|short_sleeve|three_quarter|long_sleeve",
  "length": "cropped|regular|midi|maxi|mini",
  "fit": "oversized|relaxed|regular|slim|fitted",
  "distinctive_features": ["list", "of", "details"],
  "texture": "texture description",
  "style_keywords": ["searchable", "terms"]
}

COLOR GUIDANCE - Be PRECISE:
- Look at the ACTUAL colors, not what lighting makes them appear
- Olive/khaki green is NOT brown - it's a yellow-green color
- Cream/off-white is NOT pure white
- Navy is NOT black
- Common stripe colors: olive & white, navy & white, black & white, red & white
- If unsure between similar colors, name BOTH: "olive green or khaki"

MATERIAL GUIDANCE - Be SPECIFIC:
- T-shirts/casual tops: usually "cotton jersey", "cotton", "jersey knit"
- Sweaters/jumpers: "knit", "wool knit", "cable knit", "chunky knit"  
- Dress shirts: "cotton poplin", "oxford cloth", "linen"
- Lightweight long sleeve tops: "cotton jersey", "cotton blend", "jersey"
- Heavy sweatshirts: "fleece", "french terry", "heavyweight cotton"

TEXTURE - different from material:
- Jersey/t-shirt: "smooth jersey", "soft cotton"
- Knit sweater: "ribbed knit", "cable knit texture", "chunky knit"
- Woven shirt: "crisp woven", "textured weave"

PATTERN specifics:
- "horizontal_stripes" - going across (breton, rugby style)
- "vertical_stripes" - going up/down (pinstripe)
- "wide_stripes" vs "thin_stripes"

Example - striped casual top:
{
  "label": "olive and white horizontal striped long sleeve henley top",
  "category": "top",
  "subcategory": "henley_top",
  "color": "olive green and white",
  "material": "cotton jersey",
  "pattern": "horizontal_stripes",
  "texture": "soft jersey",
  "distinctive_features": ["horizontal breton stripes", "henley neckline", "button placket"],
  "style_keywords": ["breton", "striped", "casual", "henley"]
}

Return JSON array only."""

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=base64.b64decode(img_b64), mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=3000
            )
        )
        
        return self._parse_response(response.text)
    
    def _parse_response(self, text: str) -> list:
        import re
        text = text.strip()
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            text = match.group(0)
        
        try:
            items = json.loads(text)
            
            for item in items:
                box = item.get('box_2d', [])
                if len(box) == 4:
                    item['bounding_box'] = {
                        'y_min': box[0] / 1000,
                        'x_min': box[1] / 1000,
                        'y_max': box[2] / 1000,
                        'x_max': box[3] / 1000
                    }
            return items
        except json.JSONDecodeError as e:
            print(f"JSON error: {e}")
            return []
    
    def crop_items(self, image: Image.Image, items: list, padding_pct: float = 0.12) -> list:
        width, height = image.size
        crops = []
        
        for item in items:
            bbox = item.get('bounding_box', {})
            if not bbox:
                continue
            
            x_min = bbox.get('x_min', 0)
            y_min = bbox.get('y_min', 0)
            x_max = bbox.get('x_max', 1)
            y_max = bbox.get('y_max', 1)
            
            if x_min >= x_max or y_min >= y_max:
                continue
            
            pad_x = (x_max - x_min) * padding_pct
            pad_y = (y_max - y_min) * padding_pct
            
            x_min = max(0, x_min - pad_x)
            y_min = max(0, y_min - pad_y)
            x_max = min(1, x_max + pad_x)
            y_max = min(1, y_max + pad_y)
            
            left = int(x_min * width)
            top = int(y_min * height)
            right = int(x_max * width)
            bottom = int(y_max * height)
            
            cropped = image.crop((left, top, right, bottom))
            crops.append({
                'image': cropped,
                'attributes': item
            })
        
        return crops
    
    def visualize_boxes(self, image: Image.Image, items: list) -> Image.Image:
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        width, height = image.size
        
        colors = ['#FF0000', '#00FF00', '#0000FF', '#FFA500', '#FF00FF', '#00FFFF']
        
        for i, item in enumerate(items):
            bbox = item.get('bounding_box', {})
            if not bbox:
                continue
            
            left = int(bbox.get('x_min', 0) * width)
            top = int(bbox.get('y_min', 0) * height)
            right = int(bbox.get('x_max', 1) * width)
            bottom = int(bbox.get('y_max', 1) * height)
            
            color = colors[i % len(colors)]
            draw.rectangle([left, top, right, bottom], outline=color, width=4)
            
            label = f"{item.get('category', '?')}: {item.get('subcategory', '')[:12]}"
            draw.rectangle([left, top-25, left + len(label)*8, top], fill=color)
            draw.text((left + 4, top - 22), label, fill='white')
        
        return img_copy


if __name__ == "__main__":
    import sys
    
    analyzer = GarmentAnalyzer()
    image_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/gavinwalker/Desktop/AI OUTFIT PICS/josefine vogt.jpeg"
    
    print(f"🔍 Analyzing: {image_path}")
    print("="*70)
    
    image = Image.open(image_path)
    items = analyzer.analyze_outfit(image)
    
    print(f"\n📦 Detected {len(items)} items:\n")
    
    for i, item in enumerate(items):
        print(f"\n{i+1}. {item.get('category', '?').upper()}: {item.get('label', '?')}")
        print(f"   Subcategory: {item.get('subcategory', '-')}")
        print(f"   Color: {item.get('color', '-')}")
        print(f"   Material: {item.get('material', '-')}")
        print(f"   Pattern: {item.get('pattern', '-')}")
        print(f"   Texture: {item.get('texture', '-')}")
        print(f"   Fit: {item.get('fit', '-')}")
        print(f"   Sleeve: {item.get('sleeve_length', '-')} | Length: {item.get('length', '-')}")
        
        features = item.get('distinctive_features', [])
        if features:
            print(f"   Features: {', '.join(features)}")
        
        keywords = item.get('style_keywords', [])
        if keywords:
            print(f"   Style: {', '.join(keywords)}")

    # Visualize and save
    viz = analyzer.visualize_boxes(image, items)
    viz.save("debug_boxes.jpg")
    print(f"\n📊 Saved: debug_boxes.jpg")
