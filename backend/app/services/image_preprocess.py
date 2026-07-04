import os
import cv2
import fitz  # PyMuPDF
import numpy as np
import logging
import tempfile
from PIL import Image, ImageOps
from pathlib import Path

logger = logging.getLogger(__name__)

class ImagePreprocessor:
    def __init__(self):
        pass

    def convert_pdf_to_image(self, pdf_path: Path, output_dir: Path) -> Path:
        """Converts the first page of a PDF file to a PNG image in the designated output directory."""
        logger.info(f"Converting PDF to image: {pdf_path}")
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            raise ValueError("PDF file is empty")
        
        # Load the first page
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=200)  # Render with 200 DPI for OCR balance
        
        output_filename = f"{pdf_path.stem}_page_0.png"
        output_path = output_dir / output_filename
        
        pix.save(str(output_path))
        doc.close()
        logger.info(f"PDF converted to image saved at: {output_path}")
        return output_path

    def correct_orientation(self, image: Image.Image) -> Image.Image:
        """Corrects orientation using EXIF orientation tag."""
        try:
            # ImageOps.exif_transpose automatically handles EXIF orientation
            corrected_image = ImageOps.exif_transpose(image)
            return corrected_image
        except Exception as e:
            logger.warning(f"Failed to correct orientation via EXIF: {e}")
            return image

    def resize(self, img_np: np.ndarray, max_dim: int = 2000) -> np.ndarray:
        """Resizes the image if its dimensions exceed max_dim, maintaining aspect ratio."""
        h, w = img_np.shape[:2]
        if max(h, w) <= max_dim:
            return img_np
            
        if h > w:
            new_h = max_dim
            new_w = int((w / h) * max_dim)
        else:
            new_w = max_dim
            new_h = int((h / w) * max_dim)
            
        logger.info(f"Resizing image from ({w}x{h}) to ({new_w}x{new_h})")
        return cv2.resize(img_np, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def denoise(self, img_np: np.ndarray) -> np.ndarray:
        """Applies bilateral filtering to remove noise while keeping edges sharp."""
        logger.info("Applying Bilateral Denoising")
        return cv2.bilateralFilter(img_np, d=9, sigmaColor=75, sigmaSpace=75)

    def enhance_contrast(self, img_np: np.ndarray) -> np.ndarray:
        """Applies Contrast Limited Adaptive Histogram Equalization (CLAHE)."""
        logger.info("Applying CLAHE for contrast enhancement")
        if len(img_np.shape) == 3:
            # Convert to LAB color space
            lab = cv2.cvtColor(img_np, cv2.COLOR_BGR2LAB)
            l_channel, a, b = cv2.split(lab)
            
            # Apply CLAHE
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l_channel)
            
            # Merge back and convert to BGR
            merged = cv2.merge((cl, a, b))
            return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
        else:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(img_np)

    def deskew(self, img_np: np.ndarray) -> np.ndarray:
        """Detects text orientation/skew angle and rotates image to align it."""
        logger.info("Performing deskewing")
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if len(img_np.shape) == 3 else img_np
        
        # Binarize
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Dilate to merge text lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
        dilate = cv2.dilate(thresh, kernel, iterations=2)
        
        # Find coordinates of all white pixels
        coords = np.column_stack(np.where(dilate > 0))
        
        # Get minimum area bounding box
        if len(coords) == 0:
            return img_np  # No text found, return original
            
        angle = cv2.minAreaRect(coords)[-1]
        
        # Adjust angle: minAreaRect returns angle in range [-90, 0)
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        # Avoid rotating if the skew angle is negligible
        if abs(angle) < 0.5 or abs(angle) > 45:
            logger.info(f"Skew angle is negligible ({angle:.2f} degrees). Skipping rotation.")
            return img_np

        logger.info(f"Deskewing angle detected: {angle:.2f} degrees")
        
        # Rotate image
        h, w = img_np.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img_np, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated

    def preprocess(self, file_path: str, output_dir: str = None) -> str:
        """Runs the entire modular preprocessing pipeline and saves the result in a temp folder or output_dir."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Resolve output directory
        if output_dir is None:
            out_path_dir = Path(tempfile.gettempdir())
        else:
            out_path_dir = Path(output_dir)
            out_path_dir.mkdir(parents=True, exist_ok=True)

        # 1. Convert PDF if necessary
        if path.suffix.lower() == ".pdf":
            working_path = self.convert_pdf_to_image(path, out_path_dir)
        else:
            working_path = path

        # 2. Correct EXIF Orientation using Pillow
        logger.info(f"Loading image for preprocessing: {working_path}")
        pil_img = Image.open(working_path)
        pil_img = self.correct_orientation(pil_img)
        
        # Convert to OpenCV BGR format
        img_np = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # 3. Modular steps
        img_np = self.resize(img_np, max_dim=2000)
        img_np = self.denoise(img_np)
        img_np = self.enhance_contrast(img_np)
        img_np = self.deskew(img_np)

        # 4. Save preprocessed image
        processed_filename = f"processed_{working_path.name}"
        processed_path = out_path_dir / processed_filename
        
        cv2.imwrite(str(processed_path), img_np)
        logger.info(f"Preprocessing completed. Output saved at: {processed_path}")
        
        return str(processed_path)

# Instantiate singleton preprocessor
image_preprocessor = ImagePreprocessor()
