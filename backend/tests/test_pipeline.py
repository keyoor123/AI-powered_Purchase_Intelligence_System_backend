import os
import sys
import asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.image_preprocess import image_preprocessor
from app.services.ocr_service import ocr_service
from app.services.llm_extractor import OpenRouterExtractor, BaseLLMExtractor

class MockLLMExtractor(BaseLLMExtractor):
    """Mock extractor for offline testing without OpenRouter credentials."""
    async def extract_bill_data(self, ocr_text: str, image_path: str) -> dict:
        return {
            "dealer_name": "ACME Supplies Ltd.",
            "invoice_no": "INV-2026-998",
            "date": "2026-06-10",
            "subtotal": 450.0,
            "gst": 30.0,
            "total": 480.0,
            "items": [
                {
                    "product": "A4 Paper Reams",
                    "quantity": 10.0,
                    "unit": "box",
                    "price": 45.0,
                    "amount": 450.0
                }
            ]
        }

def generate_mock_invoice_image(output_path: Path):
    """Draws a dummy invoice text on a white canvas and saves it."""
    # Create white image
    img = Image.new("RGB", (800, 1000), color="white")
    draw = ImageDraw.Draw(img)
    
    # Simple lines representing an invoice
    draw.text((50, 50), "ACME Supplies Ltd.", fill="black")
    draw.text((50, 80), "Phone: 555-0199", fill="black")
    draw.text((50, 110), "Address: 123 Industrial Way", fill="black")
    
    draw.text((500, 50), "INVOICE", fill="black")
    draw.text((500, 80), "Invoice No: INV-2026-998", fill="black")
    draw.text((500, 110), "Date: 2026-06-10", fill="black")
    
    draw.line((50, 150, 750, 150), fill="black", width=2)
    
    draw.text((50, 180), "Item", fill="black")
    draw.text((400, 180), "Qty", fill="black")
    draw.text((500, 180), "Price", fill="black")
    draw.text((650, 180), "Total", fill="black")
    
    draw.line((50, 210, 750, 210), fill="black", width=1)
    
    draw.text((50, 230), "A4 Paper Reams", fill="black")
    draw.text((400, 230), "10", fill="black")
    draw.text((500, 230), "$45.00", fill="black")
    draw.text((650, 230), "$450.00", fill="black")
    
    draw.line((50, 700, 750, 700), fill="black", width=1)
    
    draw.text((500, 720), "Subtotal:", fill="black")
    draw.text((650, 720), "$450.00", fill="black")
    
    draw.text((500, 750), "GST (6.67%):", fill="black")
    draw.text((650, 750), "$30.00", fill="black")
    
    draw.text((500, 780), "Total Amount:", fill="black")
    draw.text((650, 780), "$480.00", fill="black")
    
    img.save(output_path)
    print(f"Generated mock invoice image at: {output_path}")

async def run_test_pipeline():
    print("--- Starting Pipeline Verification Test ---")
    
    test_dir = Path(__file__).resolve().parent
    test_image_path = test_dir / "sample_invoice.png"
    
    # 1. Generate sample invoice image if not exists
    generate_mock_invoice_image(test_image_path)
    
    # 2. Test Image Preprocessing
    print("\n1. Testing Image Preprocessing...")
    try:
        processed_path = image_preprocessor.preprocess(str(test_image_path))
        print(f"[OK] Preprocessing success. Output saved to: {processed_path}")
    except Exception as e:
        print(f"[FAIL] Preprocessing failed: {e}")
        return

    # 3. Test OCR extraction
    print("\n2. Testing OCR Service (PaddleOCR)...")
    try:
        raw_text = await ocr_service.extract_text(processed_path)
        print("[OK] OCR extracted text snippet:")
        print("------------------------------")
        print(raw_text[:300] + "\n...")
        print("------------------------------")
    except Exception as e:
        print(f"[FAIL] OCR failed: {e}")
        return

    # 4. Test LLM extraction (using Mock)
    print("\n3. Testing LLM Extraction (Mock Service)...")
    mock_extractor = MockLLMExtractor()
    try:
        bill_data = await mock_extractor.extract_bill_data(raw_text, processed_path)
        print("[OK] Mock LLM successfully returned structured data:")
        print(bill_data)
    except Exception as e:
        print(f"[FAIL] LLM Extraction failed: {e}")
        return
        
    print("\n--- Pipeline Verification Completed Successfully! ---")

if __name__ == "__main__":
    asyncio.run(run_test_pipeline())
