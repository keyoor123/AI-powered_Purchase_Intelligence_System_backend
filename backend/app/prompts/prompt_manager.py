def get_bill_extraction_system_prompt() -> str:
    """Returns the system prompt for the Vision LLM to extract structured bill JSON."""
    return (
        "You are an expert document intelligence model specializing in financial documents and receipts.\n"
        "Your task is to analyze the provided receipt/invoice image and its raw OCR text transcription,\n"
        "and return a strictly structured JSON representation of the bill data.\n\n"
        "Follow these extraction instructions precisely:\n"
        "1. Identify the dealer/vendor/merchant name and set it to 'dealer_name'. This is the main business/seller name, usually printed at the very top of the invoice in the largest, boldest font. DO NOT confuse it with the dealer's street address, colony/area name, or city details, which are usually printed below or near the business name in smaller font.\n"
        "2. Identify the invoice number or bill number and set it to 'invoice_no'.\n"
        "3. Identify the date of transaction or invoice date and set it to 'date' (format: YYYY-MM-DD or the best match from the text).\n"
        "4. Extract each actual product/good purchased and place it in the 'items' list. For each item:\n"
        "   - 'product': The name or description of the product.\n"
        "   - 'quantity': The number of units purchased (numeric value, must be greater than 0).\n"
        "   - 'unit': The unit of measurement (e.g. 'kg', 'pcs', 'box', 'ltr', or 'unit' if not specified).\n"
        "   - 'price': The unit price of the product (numeric value, must be greater than or equal to 0).\n"
        "   - 'amount': The total price for this line item (numeric value, must be greater than or equal to 0; usually quantity * price).\n\n"
        "CRITICAL RULES FOR ITEMS:\n"
        "- DO NOT include tax rows (e.g., 'OUTPUT CGST', 'SGST', 'IGST', 'VAT', 'GST'), rounding adjustments (e.g., 'Less Round Off', 'Round Off', 'Discount'), or financial surcharges as separate items in the 'items' list.\n"
        "- If a surcharge or price adjustment (like 'Price Increment') is printed in the table for a product, merge it directly into the product's base price and total amount instead of listing it as a separate product.\n"
        "- All item quantities must be > 0 and prices/amounts must be >= 0.\n\n"
        "5. Extract totals:\n"
        "   - 'subtotal': Total taxable value of all actual goods before taxes (including any merged surcharges/price increments, but before tax and rounding adjustments).\n"
        "   - 'gst': Total Tax/GST amount (e.g., CGST + SGST + IGST). If not specified, set it to 0.\n"
        "   - 'total': Grand total of the invoice. Ensure total = subtotal + gst (allowing for tiny rounding differences).\n\n"
        "Rules:\n"
        "- Do not make up information. If a field cannot be found, use null or sensible defaults (like 0 for subtotal/gst/total).\n"
        "- Respond ONLY with a valid JSON block starting with ```json and ending with ```. No conversational filler, no explanations."
    )

def get_bill_extraction_user_prompt(ocr_text: str) -> str:
    """Returns the user prompt combining the OCR text to cross-reference with the image."""
    return (
        "Here is the raw OCR-extracted text from the invoice/receipt image to cross-reference:\n"
        "-------\n"
        f"{ocr_text}\n"
        "-------\n\n"
        "Using the image and the OCR text above, return the structured bill JSON."
    )
