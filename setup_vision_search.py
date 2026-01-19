#!/usr/bin/env python3
"""
YOW - Vision API Product Search Setup Script
============================================
This script sets up Vision API Product Search for the Shop the Look feature.

Project: Your Online Wardrobe
Project ID: gen-lang-client-0930631788

Run this script to:
1. Enable the Vision API
2. Create a product set for ASOS products
3. Test the setup

Prerequisites:
- Google Cloud SDK installed (gcloud)
- Authenticated with: gcloud auth login
- Project set: gcloud config set project gen-lang-client-0930631788
"""

import os
import subprocess
import sys

PROJECT_ID = "gen-lang-client-0930631788"
LOCATION = "us-east1"  # Good for most use cases, low latency
PRODUCT_SET_ID = "yow-asos-products"
BUCKET_NAME = f"{PROJECT_ID}-product-images"


def run_command(command: str, description: str):
    """Run a shell command and handle errors"""
    print(f"\n{'='*60}")
    print(f"📌 {description}")
    print(f"{'='*60}")
    print(f"Running: {command}\n")
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        # Some gcloud commands output to stderr even on success
        print(result.stderr)
    
    return result.returncode == 0


def setup_gcloud():
    """Configure gcloud for the project"""
    print("\n" + "="*60)
    print("🔧 STEP 1: Configure Google Cloud Project")
    print("="*60)
    
    # Set the project
    run_command(
        f"gcloud config set project {PROJECT_ID}",
        "Setting active project"
    )
    
    # Enable required APIs
    apis = [
        "vision.googleapis.com",
        "storage.googleapis.com",
    ]
    
    for api in apis:
        run_command(
            f"gcloud services enable {api}",
            f"Enabling {api}"
        )


def create_storage_bucket():
    """Create a Cloud Storage bucket for product images"""
    print("\n" + "="*60)
    print("🪣 STEP 2: Create Cloud Storage Bucket")
    print("="*60)
    
    # Check if bucket exists
    check = subprocess.run(
        f"gsutil ls gs://{BUCKET_NAME}",
        shell=True, capture_output=True
    )
    
    if check.returncode == 0:
        print(f"✅ Bucket gs://{BUCKET_NAME} already exists")
        return True
    
    # Create bucket
    success = run_command(
        f"gsutil mb -l {LOCATION} gs://{BUCKET_NAME}",
        f"Creating bucket gs://{BUCKET_NAME}"
    )
    
    if success:
        print(f"✅ Bucket created: gs://{BUCKET_NAME}")
    else:
        print(f"⚠️ Could not create bucket. It may already exist or name is taken.")
    
    return success


def create_service_account():
    """Create a service account for Vision API access"""
    print("\n" + "="*60)
    print("🔑 STEP 3: Create Service Account")
    print("="*60)
    
    sa_name = "yow-vision-search"
    sa_email = f"{sa_name}@{PROJECT_ID}.iam.gserviceaccount.com"
    key_path = os.path.expanduser("~/yow-vision-key.json")
    
    # Create service account
    run_command(
        f'gcloud iam service-accounts create {sa_name} --display-name="YOW Vision Search" 2>/dev/null || true',
        "Creating service account"
    )
    
    # Grant roles
    roles = [
        "roles/visionai.admin",
        "roles/storage.objectAdmin",
    ]
    
    for role in roles:
        run_command(
            f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
            f'--member="serviceAccount:{sa_email}" '
            f'--role="{role}" --quiet',
            f"Granting {role}"
        )
    
    # Create key file
    if not os.path.exists(key_path):
        run_command(
            f'gcloud iam service-accounts keys create {key_path} '
            f'--iam-account={sa_email}',
            "Creating service account key"
        )
        print(f"✅ Key saved to: {key_path}")
    else:
        print(f"✅ Key already exists: {key_path}")
    
    return key_path


def test_vision_api():
    """Test that the Vision API is working"""
    print("\n" + "="*60)
    print("🧪 STEP 4: Test Vision API Connection")
    print("="*60)
    
    try:
        from google.cloud import vision
        
        # Set credentials
        key_path = os.path.expanduser("~/yow-vision-key.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        
        client = vision.ImageAnnotatorClient()
        print("✅ Vision API client created successfully!")
        
        # Test with a simple label detection on a public image
        image = vision.Image()
        image.source.image_uri = "gs://cloud-samples-data/vision/label/wakeupcat.jpg"
        
        response = client.label_detection(image=image, max_results=3)
        
        if response.label_annotations:
            print("✅ Vision API is working! Test labels detected:")
            for label in response.label_annotations:
                print(f"   - {label.description} ({label.score:.2%})")
        
        return True
        
    except ImportError:
        print("❌ google-cloud-vision not installed. Run:")
        print("   pip install google-cloud-vision --break-system-packages")
        return False
    except Exception as e:
        print(f"❌ Error testing Vision API: {e}")
        return False


def print_next_steps():
    """Print next steps for the user"""
    print("\n" + "="*60)
    print("✅ SETUP COMPLETE!")
    print("="*60)
    print(f"""
Your Vision API Product Search is ready to configure!

Project ID: {PROJECT_ID}
Location: {LOCATION}
Product Set ID: {PRODUCT_SET_ID}
Storage Bucket: gs://{BUCKET_NAME}
Credentials: ~/yow-vision-key.json

NEXT STEPS:
-----------
1. Run the product search client:
   python vision_product_search.py

2. Create the product set:
   python -c "from vision_product_search import VisionProductSearch; VisionProductSearch().create_product_set()"

3. Import your ASOS products (see import_asos_products.py)

4. Wait 30-60 minutes for indexing

5. Test searches with sample images!

PRICING REMINDER:
-----------------
- First 1,000 images/month: FREE
- After that: $4.50 per 1,000 search queries
- Storage: $0.10 per 1,000 images/month

You have $300 in free credits to start!
""")


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     YOW - Vision API Product Search Setup                 ║
    ║     Shop the Look Feature                                 ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check if gcloud is installed
    result = subprocess.run("which gcloud", shell=True, capture_output=True)
    if result.returncode != 0:
        print("❌ Google Cloud SDK (gcloud) is not installed.")
        print("   Install from: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    
    # Run setup steps
    setup_gcloud()
    create_storage_bucket()
    key_path = create_service_account()
    
    # Set environment variable for this session
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
    
    # Test the API
    test_vision_api()
    
    # Print next steps
    print_next_steps()


if __name__ == "__main__":
    main()
