"""Test with cropped/zoomed image"""
from PIL import Image

# Load the VTO and crop to just show part of dress
img = Image.open("test_vto_hard.jpg")
w, h = img.size

# Crop to middle section (torso area - showing wrap top detail)
cropped = img.crop((w*0.2, h*0.15, w*0.8, h*0.6))
cropped.save("test_cropped.jpg")
print(f"Cropped from {img.size} to {cropped.size}")
print("Saved to test_cropped.jpg")
import os
os.system("open test_cropped.jpg")
