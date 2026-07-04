import os
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.image_preprocess import image_preprocessor

def run_preprocess_profiler():
    print("=== Preprocessing-only Profiler ===")
    test_dir = Path(__file__).resolve().parent
    test_image_path = test_dir / "large_sample_invoice_prep.png"
    
    # Generate large mock invoice image (2000 x 2500 pixels)
    img = Image.new("RGB", (2000, 2500), color="white")
    draw = ImageDraw.Draw(img)
    # Simple line representing text
    draw.text((100, 100), "ACME Supplies Ltd.", fill="black")
    draw.text((100, 200), "Invoice No: INV-2026-998", fill="black")
    img.save(test_image_path)
    print(f"Generated large mock invoice image at: {test_image_path}")
        
    print("\nRunning Preprocessing steps...")
    try:
        pil_img = Image.open(test_image_path)
        img_np = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        # 1. Resize
        t0 = time.time()
        img_resized = image_preprocessor.resize(img_np, max_dim=2000)
        t_resize = time.time() - t0
        print(f"  - Resize: {t_resize:.4f}s (Shape: {img_resized.shape})")
        
        # 2. Denoise
        t0 = time.time()
        img_denoised = image_preprocessor.denoise(img_resized)
        t_denoise = time.time() - t0
        print(f"  - Denoise (Bilateral Filter): {t_denoise:.4f}s")
        
        # 3. CLAHE
        t0 = time.time()
        img_clahe = image_preprocessor.enhance_contrast(img_denoised)
        t_clahe = time.time() - t0
        print(f"  - Contrast (CLAHE): {t_clahe:.4f}s")
        
        # 4. Deskew
        t0 = time.time()
        img_deskewed = image_preprocessor.deskew(img_clahe)
        t_deskew = time.time() - t0
        print(f"  - Deskew: {t_deskew:.4f}s")
        
        processed_path = test_dir / "processed_large_sample_prep.png"
        cv2.imwrite(str(processed_path), img_deskewed)
        print(f"-> Preprocessing finished. Output saved to: {processed_path}")
    except Exception as e:
        print(f"-> Preprocessing failed: {e}")
        return

if __name__ == "__main__":
    run_preprocess_profiler()
