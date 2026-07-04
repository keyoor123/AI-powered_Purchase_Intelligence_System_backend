import os
import logging
import time
import asyncio
from pathlib import Path

# Disable PaddlePaddle/PaddleX online model checks to avoid ~120s latency on CPU
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)

class OCRService:
    def __init__(self):
        self._ocr = None

    def _get_ocr_engine(self) -> PaddleOCR:
        """Lazily instantiates PaddleOCR engine to speed up startup."""
        if self._ocr is None:
            logger.info("Initializing PaddleOCR engine (CPU, PP-OCRv4)...")
            try:
                # use_textline_orientation=False avoids loading redundant PP-LCNet textline_ori model
                # enable_mkldnn=False avoids NotImplementedError on Windows CPU
                # use_doc_orientation_classify=False and use_doc_unwarping=False speed up CPU initialization
                self._ocr = PaddleOCR(
                    ocr_version="PP-OCRv4",
                    use_textline_orientation=False,
                    lang="en",
                    device="cpu",
                    enable_mkldnn=False,
                    cpu_threads=4,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False
                )
                logger.info("PaddleOCR engine initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR engine: {e}")
                raise RuntimeError(f"OCR engine initialization failed: {e}")
        return self._ocr

    def warmup(self):
        """Warms up the OCR engine by instantiating it and running a dummy prediction."""
        logger.info("Warming up OCR engine...")
        try:
            # Get the engine (this initializes it)
            ocr_engine = self._get_ocr_engine()
            # Run a quick dummy prediction on a 1x1 blank image to force compiling
            import numpy as np
            dummy_img = np.ones((1, 1, 3), dtype=np.uint8) * 255
            list(ocr_engine.predict(dummy_img))
            logger.info("OCR engine warmup completed successfully.")
        except Exception as e:
            logger.warning(f"OCR engine warmup failed (it will initialize on first request): {e}")

    def _predict_in_thread(self, image_path: str) -> list:
        """Helper to run the CPU-bound PaddleOCR predict method in a thread pool."""
        ocr_engine = self._get_ocr_engine()
        return list(ocr_engine.predict(image_path))

    async def extract_text(self, image_path: str) -> str:
        """Extracts text from an image using PaddleOCR and returns the text asynchronously."""
        logger.info(f"Running OCR on file: {image_path}")
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found for OCR: {image_path}")

        try:
            start_time = time.time()
            # Run CPU-bound prediction in a background thread to keep event loop responsive
            result = await asyncio.to_thread(self._predict_in_thread, image_path)
            
            extracted_lines = []
            if result and 'rec_texts' in result[0]:
                extracted_lines = result[0]['rec_texts']
            
            raw_text = "\n".join(extracted_lines)
            duration = time.time() - start_time
            logger.info(f"OCR completed successfully in {duration:.4f}s.")
            
            return raw_text
        except Exception as e:
            logger.error(f"Error during OCR extraction: {e}")
            raise RuntimeError(f"OCR extraction failed: {e}")

# Instantiate singleton OCR service
ocr_service = OCRService()
