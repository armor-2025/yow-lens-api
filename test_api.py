"""
Test script for Shop the Look API
"""
import requests
import json
import sys

API_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint"""
    print("🔍 Testing health endpoint...")
    try:
        r = requests.get(f"{API_URL}/health")
        data = r.json()
        print(f"   Status: {data['status']}")
        print(f"   Models loaded: {data['models_loaded']}")
        print(f"   Total products: {data.get('total_products', 'N/A')}")
        print(f"   Categories: {data.get('categories', {})}")
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_shop_the_look(image_path: str, limit: int = 5):
    """Test shop-the-look endpoint"""
    print(f"\n🛍️  Testing Shop the Look...")
    print(f"   Image: {image_path}")
    
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (image_path, f, 'image/jpeg')}
            params = {'limit_per_item': limit}
            
            print("   Uploading and processing...")
            r = requests.post(
                f"{API_URL}/shop-the-look",
                files=files,
                params=params,
                timeout=120  # Give it time for Gemini + embeddings
            )
        
        if r.status_code != 200:
            print(f"   ❌ HTTP {r.status_code}: {r.text[:200]}")
            return
        
        data = r.json()
        
        print(f"\n   ✅ Success!")
        print(f"   Items detected: {data['items_detected']}")
        
        for item_key, item_data in data['results'].items():
            detected = item_data['detected_item']
            products = item_data['products']
            
            print(f"\n   {'='*50}")
            print(f"   🏷️  {detected['category'].upper()}: {detected['label']}")
            print(f"      Color: {detected['color']}")
            print(f"      Material: {detected['material']}")
            print(f"      Pattern: {detected['pattern']}")
            
            if detected['features']:
                print(f"      Features: {', '.join(detected['features'][:3])}")
            
            print(f"      Query: \"{item_data.get('text_query', '')}\"")
            print(f"\n      Top {len(products)} matches:")
            
            for i, p in enumerate(products):
                score_icon = "🎯" if p['similarity_score'] > 0.6 else "✓" if p['similarity_score'] > 0.5 else "○"
                boost_str = f" +{p['feature_boost']:.2f}" if p['feature_boost'] > 0 else ""
                
                print(f"      {i+1}. {score_icon} [{p['similarity_score']:.3f}] {p['name'][:40]}...")
                print(f"         V:{p['visual_score']:.2f} T:{p['text_score']:.2f} C:{p['color_score']:.2f}{boost_str}")
                print(f"         {p['brand']} | {p['color']} | ${p['price']:.2f}")
        
        # Save full response
        with open('last_api_response.json', 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n   📄 Full response saved to: last_api_response.json")
        
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Cannot connect to API. Is it running?")
        print(f"   Run: python shop_the_look_api.py")
    except Exception as e:
        print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    print("="*60)
    print("YOW Lens - API Test Script")
    print("="*60)
    
    # Test health first
    if not test_health():
        print("\n⚠️  API not running. Start it with:")
        print("   python shop_the_look_api.py")
        sys.exit(1)
    
    # Test with image if provided
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        test_shop_the_look(image_path)
    else:
        print("\n💡 Usage: python test_api.py <image_path>")
        print("   Example: python test_api.py /path/to/outfit.jpg")
        
        # Try default test images
        test_images = [
            "temp_test.jpg",
            "/Users/gavinwalker/Desktop/AI OUTFIT PICS/josefine vogt.jpeg",
        ]
        
        for img in test_images:
            import os
            if os.path.exists(img):
                print(f"\n   Found test image: {img}")
                response = input("   Test with this image? (y/n): ")
                if response.lower() == 'y':
                    test_shop_the_look(img)
                    break
