import time
from paddleocr import PaddleOCR
import numpy as np

def test():
    print("Testing PaddleOCR CPU speed optimizations...")
    dummy_img = np.ones((800, 1000, 3), dtype=np.uint8) * 255
    
    params = {
        "ocr_version": "PP-OCRv4",
        "use_textline_orientation": False,
        "lang": "en",
        "device": "cpu",
        "enable_mkldnn": False,
        "cpu_threads": 6,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False
    }
    
    try:
        print("Initializing PaddleOCR with enable_mkldnn=True, cpu_threads=6...")
        ocr = PaddleOCR(**params)
        
        print("Running prediction...")
        t0 = time.time()
        list(ocr.predict(dummy_img))
        print(f"Prediction success in {time.time() - t0:.4f}s")
        
    except Exception as e:
        print(f"Failed with error: {e}")

if __name__ == "__main__":
    test()
