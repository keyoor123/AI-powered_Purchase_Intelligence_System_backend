import logging
import os
import shutil
import uuid
import asyncio
import tempfile
import time
from datetime import datetime
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pathlib import Path

from app.database.database import get_database, db_manager
from app.schemas.bill import BillDataSchema
from app.schemas.category import CategoryCreateSchema, CategoryResponseSchema
from app.models.models import (
    BillDocument,
    BillItemDB,
    DealerDocument,
    ProductDocument,
    ProcessingLogDocument,
    CategoryDocument
)
from app.services.image_preprocess import image_preprocessor
from app.services.ocr_service import ocr_service
from app.services.llm_extractor import llm_extractor
from app.utils.config import settings
from app.utils.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_single_file(file: UploadFile) -> dict:
    """
    Helper to process a single uploaded invoice file asynchronously through the pipeline.
    Runs CPU-bound operations in threads and awaits async functions.
    """
    t_start = time.time()
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".jpg", ".jpeg", ".png", ".pdf", ".webp"]:
        logger.error(f"Unsupported file type uploaded: {file_ext}")
        return {
            "filename": file.filename,
            "success": False,
            "detail": "Unsupported file format. Please upload JPG, JPEG, PNG, WEBP, or PDF."
        }

    # Use a separate temporary directory for each file to ensure processing isolation
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        original_file_path = temp_dir_path / f"original_upload{file_ext}"

        # 1. Save uploaded file to temporary path
        t_save_start = time.time()
        try:
            def write_file():
                with open(original_file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            await asyncio.to_thread(write_file)
            t_save = time.time() - t_save_start
            logger.info(f"[{file.filename}] Original file saved temporarily in {t_save:.4f}s at: {original_file_path}")
        except Exception as e:
            logger.error(f"Failed to save uploaded file {file.filename}: {e}")
            return {
                "filename": file.filename,
                "success": False,
                "detail": f"Failed to save uploaded file: {str(e)}"
            }

        # 2. Run Image Preprocessing (offloaded to thread)
        t_prep_start = time.time()
        try:
            preprocessed_path = await asyncio.to_thread(
                image_preprocessor.preprocess,
                str(original_file_path),
                str(temp_dir_path)
            )
            t_prep = time.time() - t_prep_start
            logger.info(f"[{file.filename}] Preprocessing completed in {t_prep:.4f}s")
        except Exception as e:
            logger.error(f"Preprocessing failed for {file.filename}: {e}")
            return {
                "filename": file.filename,
                "success": False,
                "detail": f"Preprocessing failed: {str(e)}"
            }

        # 3. Run OCR extraction asynchronously
        t_ocr_start = time.time()
        try:
            ocr_text = await ocr_service.extract_text(preprocessed_path)
            t_ocr = time.time() - t_ocr_start
            logger.info(f"[{file.filename}] OCR completed in {t_ocr:.4f}s")
        except Exception as e:
            logger.error(f"OCR extraction failed for {file.filename}: {e}")
            return {
                "filename": file.filename,
                "success": False,
                "detail": f"OCR text extraction failed: {str(e)}"
            }

        # 4. Run Vision LLM Extraction
        t_llm_start = time.time()
        try:
            extracted_data = await llm_extractor.extract_bill_data(
                ocr_text=ocr_text,
                image_path=preprocessed_path
            )
            t_llm = time.time() - t_llm_start
            logger.info(f"[{file.filename}] Vision LLM extraction completed in {t_llm:.4f}s")
        except Exception as e:
            logger.error(f"Vision LLM extraction failed for {file.filename}: {e}")
            return {
                "filename": file.filename,
                "success": False,
                "detail": f"Vision LLM data extraction failed: {str(e)}"
            }

    # Add bill image metadata (original filename)
    extracted_data["bill_image"] = file.filename

    # 5. Validate output using Pydantic
    t_val_start = time.time()
    try:
        validated_bill = BillDataSchema(**extracted_data)
        t_val = time.time() - t_val_start
        t_total = time.time() - t_start
        logger.info(f"[{file.filename}] Structured JSON validated successfully in {t_val:.4f}s. Total pipeline time: {t_total:.4f}s")
        return {
            "filename": file.filename,
            "success": True,
            "bill_data": validated_bill.model_dump()
        }
    except Exception as e:
        logger.error(f"Pydantic validation failed for {file.filename}: {e}")
        return {
            "filename": file.filename,
            "success": False,
            "validation_errors": str(e),
            "bill_data": extracted_data
        }


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_bill(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    """
    Ingests a paper bill image or PDF, runs the preprocessing & OCR pipeline,
    extracts structured data using the LLM Vision model, and validates it.
    Uses temporary files which are deleted immediately after processing.
    """
    logger.info(f"Received file upload request from user {user_id} for file: {file.filename}")
    result = await process_single_file(file)
    
    if not result["success"]:
        if "validation_errors" in result:
            return {
                "success": False,
                "validation_errors": result["validation_errors"],
                "bill_data": result["bill_data"]
            }
        
        # Determine status code based on error type
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        if "Vision LLM" in result["detail"]:
            status_code = status.HTTP_502_BAD_GATEWAY
        elif "Unsupported file format" in result["detail"]:
            status_code = status.HTTP_400_BAD_REQUEST
            
        raise HTTPException(
            status_code=status_code,
            detail=result["detail"]
        )

    return {
        "success": True,
        "bill_data": result["bill_data"]
    }


@router.post("/upload/batch", status_code=status.HTTP_200_OK)
async def upload_bills_batch(files: List[UploadFile] = File(...), user_id: str = Depends(get_current_user_id)):
    """
    Concurrently processes a list of uploaded bill images/PDFs using asyncio.gather.
    Returns a list of processing results.
    """
    logger.info(f"Received batch file upload request from user {user_id} for {len(files)} files.")
    
    # Run all file process tasks concurrently in the event loop
    tasks = [process_single_file(file) for file in files]
    results = await asyncio.gather(*tasks)
    
    return {
        "processed_count": len(files),
        "results": results
    }


@router.post("/save", status_code=status.HTTP_201_CREATED)
async def save_bill(
    bill_payload: BillDataSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Saves validated JSON input into MongoDB under the current user's account.
    Performs upserts on user-specific products and dealers, writes the processing log, and stores the bill.
    """
    logger.info(f"Received request from user {user_id} to save validated bill data to MongoDB.")
    
    # Enforce strict category requirement on save
    if not bill_payload.category or not bill_payload.category.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category is strictly required to save the bill."
        )

    try:
        # 1. Check & Update Dealer (isolated by user_id)
        dealer_collection = db_manager.get_dealers_collection()
        dealer_name = bill_payload.dealer_name.strip()
        existing_dealer = await dealer_collection.find_one({"name": dealer_name, "user_id": user_id})
        
        if not existing_dealer:
            dealer_doc = DealerDocument(
                user_id=user_id,
                name=dealer_name,
                created_at=datetime.utcnow()
            )
            dealer_res = await dealer_collection.insert_one(dealer_doc.model_dump(by_alias=True, exclude={"id"}))
            logger.info(f"Created new dealer record for user {user_id}: {dealer_name} (ID: {dealer_res.inserted_id})")
        else:
            logger.info(f"Dealer already exists for user {user_id}: {dealer_name}")

        # 2. Check & Update Products (isolated by user_id)
        product_collection = db_manager.get_products_collection()
        for item in bill_payload.items:
            prod_name = item.product.strip()
            
            # Upsert the product: only set category on creation to avoid overwriting existing categories
            await product_collection.update_one(
                {"name": prod_name, "user_id": user_id},
                {
                    "$set": {
                        "default_unit": item.unit
                    },
                    "$setOnInsert": {
                        "category": bill_payload.category
                    }
                },
                upsert=True
            )
            logger.info(f"Upserted product record for user {user_id}: {prod_name} with category: {bill_payload.category}")

        # 3. Create and save the Bill Document
        bills_collection = db_manager.get_bills_collection()
        
        # Build list of items matching the Database Model structure
        db_items = [
            BillItemDB(
                product=item.product,
                quantity=item.quantity,
                unit=item.unit,
                price=item.price,
                amount=item.amount
            ) for item in bill_payload.items
        ]
        
        # Get bill_image from payload extra keys if present, or set default
        # Since BillDataSchema might not have bill_image, we allow it to be passed or default it.
        # We can extract it from additional values or a fallback.
        bill_image_name = getattr(bill_payload, "bill_image", "placeholder.png")
        if hasattr(bill_payload, "model_extra") and bill_payload.model_extra and "bill_image" in bill_payload.model_extra:
            bill_image_name = bill_payload.model_extra["bill_image"]
            
        bill_doc = BillDocument(
            user_id=user_id,
            dealer_name=bill_payload.dealer_name,
            invoice_no=bill_payload.invoice_no,
            date=bill_payload.date,
            bill_image=bill_image_name,
            subtotal=bill_payload.subtotal,
            gst=bill_payload.gst,
            total=bill_payload.total,
            category=bill_payload.category,
            status=bill_payload.status or "pending",
            items=db_items,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        bill_res = await bills_collection.insert_one(bill_doc.model_dump(by_alias=True, exclude={"id"}))
        bill_id = str(bill_res.inserted_id)
        logger.info(f"Successfully saved bill document to MongoDB. Assigned ID: {bill_id}")

        # 4. Insert processing log record
        logs_collection = db_manager.get_processing_logs_collection()
        log_doc = ProcessingLogDocument(
            bill_id=bill_id,
            ocr_status="success",
            llm_status="success",
            validation_status="success",
            message="Bill processed and saved successfully during verification.",
            created_at=datetime.utcnow()
        )
        await logs_collection.insert_one(log_doc.model_dump(by_alias=True, exclude={"id"}))
        
        return {
            "success": True,
            "id": bill_id
        }

    except Exception as e:
        logger.error(f"Error saving bill to database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database save operation failed: {str(e)}"
        )


@router.get("/bills", response_model=List[BillDocument], status_code=status.HTTP_200_OK)
async def get_all_bills(user_id: str = Depends(get_current_user_id), db: AsyncIOMotorDatabase = Depends(get_database)):
    """Returns all bills stored in the system under the current user's account."""
    logger.info(f"Fetching all bills from database for user: {user_id}")
    try:
        bills_collection = db_manager.get_bills_collection()
        cursor = bills_collection.find({"user_id": user_id})
        bills = []
        async for doc in cursor:
            # Convert _id to string for model instantiation
            doc["_id"] = str(doc["_id"])
            bills.append(BillDocument(**doc))
        return bills
    except Exception as e:
        logger.error(f"Failed to fetch bills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bills: {str(e)}"
        )


@router.get("/bill/{id}", response_model=BillDocument, status_code=status.HTTP_200_OK)
async def get_bill_by_id(id: str, user_id: str = Depends(get_current_user_id), db: AsyncIOMotorDatabase = Depends(get_database)):
    """Returns a single bill by its unique ID, restricted to the owner."""
    logger.info(f"Fetching bill details for ID: {id} for user: {user_id}")
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB ObjectId format."
        )

    try:
        bills_collection = db_manager.get_bills_collection()
        doc = await bills_collection.find_one({"_id": ObjectId(id), "user_id": user_id})
        
        if not doc:
            logger.warning(f"Bill not found with ID: {id} for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bill with ID {id} not found."
            )
            
        doc["_id"] = str(doc["_id"])
        return BillDocument(**doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching bill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching bill: {str(e)}"
        )


@router.put("/bill/{id}", status_code=status.HTTP_200_OK)
async def update_bill_fields(
    id: str,
    updated_fields: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Updates specific fields of an existing bill document owned by the current user.
    """
    logger.info(f"Updating bill ID: {id} for user: {user_id} with human verification edits.")
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB ObjectId format."
        )

    try:
        bills_collection = db_manager.get_bills_collection()
        existing_doc = await bills_collection.find_one({"_id": ObjectId(id), "user_id": user_id})
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bill with ID {id} not found."
            )

        # Strip immutable/protected fields from the update payload
        for key in ["_id", "id", "user_id"]:
            updated_fields.pop(key, None)

        # Set human verified status and timestamps
        updated_fields["status"] = "verified"
        updated_fields["updated_at"] = datetime.utcnow()

        # Update document in MongoDB
        result = await bills_collection.update_one(
            {"_id": ObjectId(id), "user_id": user_id},
            {"$set": updated_fields}
        )

        if result.modified_count == 0:
            logger.info("No modifications were made to the document (values might be identical).")
            
        return {
            "success": True,
            "message": "Bill updated and verified successfully."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating bill document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update bill: {str(e)}"
        )


# ==========================================
# Category CRUD API Endpoints
# ==========================================

@router.get("/categories", response_model=List[CategoryResponseSchema], status_code=status.HTTP_200_OK)
async def get_all_categories(user_id: str = Depends(get_current_user_id), db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Returns all categories stored in the system under the user's account.
    """
    logger.info(f"Fetching all categories from database for user: {user_id}")
    try:
        categories_collection = db_manager.get_categories_collection()
        cursor = categories_collection.find({"user_id": user_id})
        categories = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            categories.append(CategoryResponseSchema(**doc))
        return categories
    except Exception as e:
        logger.error(f"Failed to fetch categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch categories: {str(e)}"
        )


@router.post("/categories", response_model=CategoryResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_payload: CategoryCreateSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Creates a new category in the database for the authenticated user.
    """
    name = category_payload.name.strip()
    logger.info(f"User {user_id} attempting to create category: {name}")
    try:
        categories_collection = db_manager.get_categories_collection()
        # Case insensitive check for duplicate under this user
        existing = await categories_collection.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}, "user_id": user_id})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with name '{name}' already exists."
            )
        
        category_doc = CategoryDocument(user_id=user_id, name=name)
        res = await categories_collection.insert_one(category_doc.model_dump(by_alias=True, exclude={"id"}))
        category_id = str(res.inserted_id)
        logger.info(f"Created category '{name}' for user {user_id} with ID: {category_id}")
        
        return CategoryResponseSchema(id=category_id, name=name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create category: {str(e)}"
        )


@router.put("/categories/{id}", response_model=CategoryResponseSchema, status_code=status.HTTP_200_OK)
async def update_category(
    id: str,
    category_payload: CategoryCreateSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Updates a category's name and cascades changes to associated products and bills for the current user.
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB ObjectId format."
        )
    
    new_name = category_payload.name.strip()
    logger.info(f"User {user_id} updating category ID: {id} to new name: {new_name}")
    
    try:
        categories_collection = db_manager.get_categories_collection()
        existing_doc = await categories_collection.find_one({"_id": ObjectId(id), "user_id": user_id})
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {id} not found."
            )
            
        old_name = existing_doc["name"]
        
        # Check if the new name already exists on another category for this user
        if new_name.lower() != old_name.lower():
            dup = await categories_collection.find_one({"name": {"$regex": f"^{new_name}$", "$options": "i"}, "user_id": user_id})
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category with name '{new_name}' already exists."
                )

        # Update category name
        await categories_collection.update_one(
            {"_id": ObjectId(id), "user_id": user_id},
            {"$set": {"name": new_name}}
        )

        # Cascade updates to products collection (limited to user)
        products_collection = db_manager.get_products_collection()
        prod_res = await products_collection.update_many(
            {"category": old_name, "user_id": user_id},
            {"$set": {"category": new_name}}
        )
        logger.info(f"Cascaded category name update to {prod_res.modified_count} products.")

        # Cascade updates to bills collection (limited to user)
        bills_collection = db_manager.get_bills_collection()
        bill_res = await bills_collection.update_many(
            {"category": old_name, "user_id": user_id},
            {"$set": {"category": new_name}}
        )
        logger.info(f"Cascaded category name update to {bill_res.modified_count} bills.")

        return CategoryResponseSchema(id=id, name=new_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update category: {str(e)}"
        )


@router.delete("/categories/{id}", status_code=status.HTTP_200_OK)
async def delete_category(
    id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a category and resets references in products and bills to empty string (limited to user).
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB ObjectId format."
        )
        
    logger.info(f"User {user_id} deleting category ID: {id}")
    try:
        categories_collection = db_manager.get_categories_collection()
        existing_doc = await categories_collection.find_one({"_id": ObjectId(id), "user_id": user_id})
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {id} not found."
            )
            
        category_name = existing_doc["name"]

        # Delete category document
        await categories_collection.delete_one({"_id": ObjectId(id), "user_id": user_id})

        # Reset category of associated products to ""
        products_collection = db_manager.get_products_collection()
        prod_res = await products_collection.update_many(
            {"category": category_name, "user_id": user_id},
            {"$set": {"category": ""}}
        )
        logger.info(f"Cleared category references for {prod_res.modified_count} products.")

        # Reset category of associated bills to ""
        bills_collection = db_manager.get_bills_collection()
        bill_res = await bills_collection.update_many(
            {"category": category_name, "user_id": user_id},
            {"$set": {"category": ""}}
        )
        logger.info(f"Cleared category references for {bill_res.modified_count} bills.")

        return {
            "success": True,
            "message": f"Category '{category_name}' deleted successfully."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete category: {str(e)}"
        )


# ==========================================
# Invoice, Product & Supplier Deletion APIs
# ==========================================

@router.delete("/bill/{id}", status_code=status.HTTP_200_OK)
async def delete_bill(
    id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a bill (invoice) by ID and cleans up any orphaned products and suppliers.
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB ObjectId format."
        )

    logger.info(f"User {user_id} requesting deletion of bill: {id}")
    try:
        bills_collection = db_manager.get_bills_collection()
        bill = await bills_collection.find_one({"_id": ObjectId(id), "user_id": user_id})
        if not bill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bill with ID {id} not found."
            )

        dealer_name = bill.get("dealer_name")
        product_names = [item["product"] for item in bill.get("items", [])]

        # 1. Delete the bill document
        await bills_collection.delete_one({"_id": ObjectId(id), "user_id": user_id})
        logger.info(f"Deleted bill ID {id}")

        # 2. Cleanup orphaned products
        products_collection = db_manager.get_products_collection()
        deleted_products = 0
        for prod_name in product_names:
            still_exists = await bills_collection.find_one({"user_id": user_id, "items.product": prod_name})
            if not still_exists:
                await products_collection.delete_one({"name": prod_name, "user_id": user_id})
                deleted_products += 1
                logger.info(f"Deleted orphaned product: '{prod_name}'")

        # 3. Cleanup orphaned supplier
        dealers_collection = db_manager.get_dealers_collection()
        deleted_dealers = 0
        if dealer_name:
            still_exists = await bills_collection.find_one({"user_id": user_id, "dealer_name": dealer_name})
            if not still_exists:
                await dealers_collection.delete_one({"name": dealer_name, "user_id": user_id})
                deleted_dealers += 1
                logger.info(f"Deleted orphaned supplier: '{dealer_name}'")

        return {
            "success": True,
            "message": "Invoice deleted successfully.",
            "deleted_products_count": deleted_products,
            "deleted_dealers_count": deleted_dealers
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete bill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete bill: {str(e)}"
        )


@router.delete("/products/{name}", status_code=status.HTTP_200_OK)
async def delete_product(
    name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a product, removes it from all associated invoices (updating totals),
    and deletes invoices that become empty.
    """
    name_clean = name.strip()
    logger.info(f"User {user_id} requesting deletion of product: '{name_clean}'")
    try:
        products_collection = db_manager.get_products_collection()
        prod = await products_collection.find_one({"name": name_clean, "user_id": user_id})
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{name_clean}' not found."
            )

        # 1. Delete product document
        await products_collection.delete_one({"name": name_clean, "user_id": user_id})
        logger.info(f"Deleted product record: '{name_clean}'")

        # 2. Update/Delete associated bills
        bills_collection = db_manager.get_bills_collection()
        dealers_collection = db_manager.get_dealers_collection()
        
        cursor = bills_collection.find({"user_id": user_id, "items.product": name_clean})
        bills_to_update = await cursor.to_list(length=1000)

        updated_bills = 0
        deleted_bills = 0
        deleted_dealers = 0

        for bill in bills_to_update:
            bill_id = bill["_id"]
            dealer_name = bill.get("dealer_name")
            new_items = [item for item in bill.get("items", []) if item["product"] != name_clean]

            if len(new_items) == 0:
                # Delete empty bill
                await bills_collection.delete_one({"_id": bill_id})
                deleted_bills += 1
                logger.info(f"Deleted invoice {bill.get('invoice_no')} because it became empty.")
                
                # Cleanup orphaned supplier
                if dealer_name:
                    still_exists = await bills_collection.find_one({"user_id": user_id, "dealer_name": dealer_name})
                    if not still_exists:
                        await dealers_collection.delete_one({"name": dealer_name, "user_id": user_id})
                        deleted_dealers += 1
                        logger.info(f"Deleted orphaned supplier: '{dealer_name}'")
            else:
                # Recalculate bill totals
                old_subtotal = bill.get("subtotal", 0.0)
                old_gst = bill.get("gst", 0.0)
                
                new_subtotal = sum(item["price"] * item["quantity"] for item in new_items)
                gst_ratio = old_gst / old_subtotal if old_subtotal > 0 else 0.18  # default to 18% if zero
                new_gst = new_subtotal * gst_ratio
                new_total = new_subtotal + new_gst

                await bills_collection.update_one(
                    {"_id": bill_id},
                    {
                        "$set": {
                            "items": new_items,
                            "subtotal": round(new_subtotal, 2),
                            "gst": round(new_gst, 2),
                            "total": round(new_total, 2),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                updated_bills += 1
                logger.info(f"Recalculated totals for invoice {bill.get('invoice_no')}")

        return {
            "success": True,
            "message": f"Product '{name_clean}' deleted successfully.",
            "updated_invoices_count": updated_bills,
            "deleted_invoices_count": deleted_bills,
            "deleted_dealers_count": deleted_dealers
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete product: {str(e)}"
        )


@router.delete("/dealers/{name}", status_code=status.HTTP_200_OK)
async def delete_supplier(
    name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a supplier (dealer), all associated invoices, and cleans up orphaned products.
    """
    name_clean = name.strip()
    logger.info(f"User {user_id} requesting deletion of supplier: '{name_clean}'")
    try:
        dealers_collection = db_manager.get_dealers_collection()
        dealer = await dealers_collection.find_one({"name": name_clean, "user_id": user_id})
        if not dealer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supplier '{name_clean}' not found."
            )

        # 1. Delete dealer document
        await dealers_collection.delete_one({"name": name_clean, "user_id": user_id})
        logger.info(f"Deleted supplier record: '{name_clean}'")

        # 2. Find and delete associated invoices
        bills_collection = db_manager.get_bills_collection()
        cursor = bills_collection.find({"dealer_name": name_clean, "user_id": user_id})
        bills_to_delete = await cursor.to_list(length=1000)

        invoices_count = len(bills_to_delete)
        products_collection = db_manager.get_products_collection()
        deleted_products = 0

        # Delete invoices and collect products for orphan checks
        for bill in bills_to_delete:
            bill_id = bill["_id"]
            product_names = [item["product"] for item in bill.get("items", [])]

            # Delete the invoice
            await bills_collection.delete_one({"_id": bill_id})
            logger.info(f"Deleted bill ID {bill_id} for supplier '{name_clean}'")

            # Check products for orphans
            for prod_name in product_names:
                still_exists = await bills_collection.find_one({"user_id": user_id, "items.product": prod_name})
                if not still_exists:
                    await products_collection.delete_one({"name": prod_name, "user_id": user_id})
                    deleted_products += 1
                    logger.info(f"Deleted orphaned product: '{prod_name}'")

        return {
            "success": True,
            "message": f"Supplier '{name_clean}' and all associated data deleted successfully.",
            "deleted_invoices_count": invoices_count,
            "deleted_products_count": deleted_products
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete supplier: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete supplier: {str(e)}"
        )
