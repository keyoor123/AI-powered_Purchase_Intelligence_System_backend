import os
import sys
import asyncio
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.image_preprocess import image_preprocessor
from app.services.ocr_service import ocr_service
from app.services.llm_extractor import llm_extractor
from tests.test_pipeline import generate_mock_invoice_image

async def run_profiler():
    print("=== Pipeline Profiler ===")
    test_dir = Path(__file__).resolve().parent
    test_image_path = test_dir / "large_sample_invoice.png"
    
    # Generate large mock invoice image (2000 x 2500 pixels)
    img = Image.new("RGB", (2000, 2500), color="white")
    draw = ImageDraw.Draw(img)
    # Simple line representing text
    draw.text((100, 100), "ACME Supplies Ltd.", fill="black")
    draw.text((100, 200), "Invoice No: INV-2026-998", fill="black")
    draw.text((100, 300), "A4 Paper Reams  10  $45.00  $450.00", fill="black")
    img.save(test_image_path)
    print(f"Generated large mock invoice image at: {test_image_path}")
        
    # Profile Preprocessing step-by-step
    print("\n[1/3] Running Image Preprocessing steps...")
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
        
        processed_path = test_dir / "processed_large_sample.png"
        cv2.imwrite(str(processed_path), img_deskewed)
        print(f"-> Preprocessing finished. Output saved to: {processed_path}")
    except Exception as e:
        print(f"-> Preprocessing failed: {e}")
        return

    # Profile OCR Service (First run vs Second run)
    print("\n[2/3] Running OCR Service (PaddleOCR)...")
    
    # OCR Run 1 (Cold)
    print("  Running OCR Run 1 (Cold)...")
    start_time = time.time()
    try:
        raw_text_1 = await ocr_service.extract_text(str(processed_path))
        ocr_time_1 = time.time() - start_time
        print(f"  -> OCR Run 1 finished in {ocr_time_1:.4f}s")
    except Exception as e:
        print(f"  -> OCR Run 1 failed: {e}")
        return

    # OCR Run 2 (Warm)
    print("  Running OCR Run 2 (Warm)...")
    start_time = time.time()
    try:
        raw_text_2 = await ocr_service.extract_text(str(processed_path))
        ocr_time_2 = time.time() - start_time
        print(f"  -> OCR Run 2 finished in {ocr_time_2:.4f}s")
    except Exception as e:
        print(f"  -> OCR Run 2 failed: {e}")
        return

    # Profile Real OpenRouter API call
    print("\n[3/3] Running LLM Extraction (OpenRouter)...")
    print(f"Using model: {llm_extractor.model}")
    start_time = time.time()
    try:
        bill_data = await llm_extractor.extract_bill_data(raw_text_2, str(processed_path))
        llm_time = time.time() - start_time
        print(f"-> LLM extraction finished in {llm_time:.4f}s")
        print("-> Extracted data:")
        print(bill_data)
    except Exception as e:
        llm_time = time.time() - start_time
        print(f"-> LLM extraction failed after {llm_time:.4f}s: {e}")
        return

    total_time = t_resize + t_denoise + t_clahe + t_deskew + ocr_time_1 + ocr_time_2 + llm_time
    print(f"\n=== Profiling Finished. Total pipeline time (including cold OCR): {total_time:.4f}s ===")

if __name__ == "__main__":
    asyncio.run(run_profiler())
