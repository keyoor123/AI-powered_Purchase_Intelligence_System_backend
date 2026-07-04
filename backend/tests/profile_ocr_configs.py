import time
import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from paddleocr import PaddleOCR
import numpy as np

def run_config_test():
    print("=== OCR Configuration Profiler ===")
    
    # Create a dummy image
    dummy_img = np.ones((800, 1000, 3), dtype=np.uint8) * 255
    
    configs = [
        {
            "name": "Default Config (use_textline_orientation=True)",
            "params": {
                "use_textline_orientation": True,
                "lang": "en",
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False
            }
        },
        {
            "name": "Disable Textline Orientation Classifier",
            "params": {
                "use_textline_orientation": False,
                "lang": "en",
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False
            }
        },
        {
            "name": "OCR Version PP-OCRv4",
            "params": {
                "ocr_version": "PP-OCRv4",
                "lang": "en",
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False
            }
        },
        {
            "name": "PP-OCRv4 + text_det_limit_side_len=720",
            "params": {
                "ocr_version": "PP-OCRv4",
                "text_det_limit_side_len": 720,
                "lang": "en",
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False
            }
        }
    ]
    
    for cfg in configs:
        print(f"\n--- Testing: {cfg['name']} ---")
        try:
            # 1. Initialize
            t0 = time.time()
            ocr = PaddleOCR(**cfg["params"])
            init_time = time.time() - t0
            print(f"  - Initialization: {init_time:.4f}s")
            
            # 2. Cold prediction
            t0 = time.time()
            list(ocr.predict(dummy_img))
            cold_time = time.time() - t0
            print(f"  - Cold Inference: {cold_time:.4f}s")
            
            # 3. Warm prediction
            t0 = time.time()
            list(ocr.predict(dummy_img))
            warm_time = time.time() - t0
            print(f"  - Warm Inference: {warm_time:.4f}s")
            
        except Exception as e:
            print(f"  - Failed with error: {e}")

if __name__ == "__main__":
    run_config_test()
