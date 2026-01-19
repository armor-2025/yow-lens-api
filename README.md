# YOW - Shop the Look with Vision API Product Search

Visual product search for Your Online Wardrobe using Google Cloud Vision API Product Search.

## Project Details

- **Project Name**: Your Online Wardrobe
- **Project ID**: `gen-lang-client-0930631788`
- **Feature**: Shop the Look (visual product search)

## Overview

This implementation uses Google Cloud Vision API Product Search to power the "Shop the Look" feature. Users can:

1. Upload a photo of an outfit they like
2. Get visually similar products from your ASOS catalog
3. Filter results by color, category, style, etc.

## Pricing

| Usage | Cost |
|-------|------|
| First 1,000 images/month | **FREE** |
| Search queries (1,001-5M) | $4.50 per 1,000 |
| Image storage | $0.10 per 1,000 images/month |

**Estimated MVP cost**: $5-20/month

## Quick Start

### 1. Prerequisites

```bash
# Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login

# Set project
gcloud config set project gen-lang-client-0930631788
```

### 2. Run Setup Script

```bash
# Install Python dependencies
pip install google-cloud-vision google-cloud-storage requests psycopg2-binary --break-system-packages

# Run setup
cd yow-vision-search
python setup_vision_search.py
```

This will:
- Enable the Vision API
- Create a Cloud Storage bucket
- Create a service account with credentials
- Test the API connection

### 3. Import Products

```bash
# Import sample products for testing
python import_asos_products.py
```

For your real ASOS products, modify `import_asos_products.py`:

```python
# From JSON file
products = load_products_from_json('your_products.json')

# From CSV
products = load_products_from_csv('your_products.csv')

# From PostgreSQL
products = load_products_from_postgres(
    "postgresql://user:pass@host:5432/dbname"
)

# Import
importer = ASOSProductImporter()
importer.import_products(products)
```

### 4. Wait for Indexing

**Important**: After importing products, you must wait **30-60 minutes** for indexing.

Check status:
```bash
python -c "from vision_product_search import VisionProductSearch; VisionProductSearch().check_index_status()"
```

### 5. Test Search

```bash
python test_search.py
```

### 6. Run API Server

```bash
# Standalone
python shop_the_look_api.py

# Or add to your existing FastAPI app:
# from shop_the_look_api import router
# app.include_router(router)
```

API will be available at: http://localhost:8001/docs

## API Endpoints

### Search by Image Upload
```
POST /api/shop-the-look/search/upload
Content-Type: multipart/form-data

file: <image file>
filter: color="blue" (optional)
max_results: 10 (optional)
```

### Search by Image URL
```
POST /api/shop-the-look/search/url
Content-Type: application/json

{
    "image_url": "https://example.com/dress.jpg",
    "filter": "category=\"dresses\"",
    "max_results": 10
}
```

### Search by Base64 Image (for FlutterFlow)
```
POST /api/shop-the-look/search/base64
Content-Type: application/json

{
    "image_base64": "<base64 encoded image>",
    "filter": null,
    "max_results": 10
}
```

### Check Index Status
```
GET /api/shop-the-look/status
```

### List Products
```
GET /api/shop-the-look/products?limit=100
```

## FlutterFlow Integration

### API Call Setup

1. Create an API Call in FlutterFlow
2. Set method: `POST`
3. Set URL: `https://your-backend.com/api/shop-the-look/search/base64`
4. Add header: `Content-Type: application/json`
5. Set body:
```json
{
    "image_base64": "<camera_image_base64>",
    "max_results": 10
}
```

### Response Handling

The API returns:
```json
{
    "results": [
        {
            "product_id": "asos_12345",
            "display_name": "Blue Midi Dress",
            "score": 0.85,
            "image_uri": "gs://bucket/image.jpg",
            "labels": {"color": "blue", "category": "dresses"}
        }
    ],
    "count": 10,
    "query_type": "base64"
}
```

Map to your product display widgets in FlutterFlow.

## File Structure

```
yow-vision-search/
├── setup_vision_search.py      # Initial setup script
├── vision_product_search.py    # Core Vision API client
├── import_asos_products.py     # Product import utilities
├── test_search.py              # Test script
├── shop_the_look_api.py        # FastAPI endpoints
└── README.md                   # This file
```

## Product Data Format

### JSON Format
```json
[
    {
        "id": "asos_12345",
        "name": "Blue Midi Wrap Dress",
        "image_url": "https://images.asos-media.com/...",
        "color": "blue",
        "category": "dresses",
        "subcategory": "midi",
        "brand": "ASOS DESIGN",
        "gender": "women",
        "price": 45.00
    }
]
```

### CSV Format
```csv
id,name,image_url,color,category,subcategory,brand,gender,price
asos_12345,Blue Midi Wrap Dress,https://...,blue,dresses,midi,ASOS DESIGN,women,45.00
```

## Filter Expressions

Use filters to narrow search results:

```python
# Single filter
filter = 'color="blue"'

# Multiple filters (AND)
filter = 'color="blue" AND category="dresses"'

# Multiple values (OR not supported directly, use separate queries)
```

## Troubleshooting

### "No results found"
1. Check index status - wait 30-60 minutes after import
2. Verify products were imported: `list_products()`
3. Check if query image is valid

### "Permission denied"
1. Verify credentials: `echo $GOOGLE_APPLICATION_CREDENTIALS`
2. Re-run setup script
3. Check IAM roles in Google Cloud Console

### Slow searches
- Vision API typically responds in 1-3 seconds
- Use smaller images (resize to 640px max dimension)
- Check network latency to Google Cloud

## Next Steps

1. ✅ Complete setup
2. ✅ Import test products
3. ⏳ Wait for indexing (30-60 min)
4. ✅ Test search
5. 🔄 Import real ASOS products
6. 🔄 Integrate with FlutterFlow
7. 🔄 Deploy API to production (Render)

## Support

- [Vision API Product Search Docs](https://cloud.google.com/vision/product-search/docs)
- [Google Cloud Console](https://console.cloud.google.com/apis/library/vision.googleapis.com?project=gen-lang-client-0930631788)
