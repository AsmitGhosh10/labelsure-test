from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from typing import List, Annotated
from sqlalchemy.ext.asyncio import AsyncSession
import shutil
from pathlib import Path

from ....core.dependencies import get_db
from ....services.ingestion_service import IngestionService
from ....core.exceptions import RAGException
from ....utils.file_handlers import extract_text_from_upload

router = APIRouter(tags=["ingest"])

ingestion_service = IngestionService()


@router.post(
    "/ingest",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a document (text + optional images)",
    description="Upload text content and/or image files. Images field is optional."
)
async def ingest_document(
    title: Annotated[str, Form(description="Title of the document")],
    file_name: Annotated[str, Form(description="Original filename")],
    file_type: Annotated[str, Form(description="File type e.g. txt, pdf, jpg")],
    file : Annotated[UploadFile | None, File(description="Optional document file")] = None,
    content: Annotated[str | None, Form(description="Raw text content (for text documents)")] = None,
    images: Annotated[List[UploadFile] | None, File(description="Optional image files (leave empty if none)")] = None,
    user_id: Annotated[int | None, Form(description="User ID (optional)")] = None,
    db: AsyncSession = Depends(get_db),
):
    """Fixed for Swagger UI: proper default + safe handling of empty images."""


    try:
        #================
        #Text Extraction
        #================
        extracted_content = content or ""
        if file and not content:
            extracted_content = await extract_text_from_upload(file, file_type)
        


        image_paths: List[str] = []

        if images:  # Skip if Swagger sends empty placeholder
            upload_dir = Path("data/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)

            valid_images = [img for img in (images or []) if img.filename]

            for image in valid_images:
                  if image.filename:  # Only process real files
                        file_path = upload_dir / image.filename
                        with open(file_path, "wb") as buffer:
                              shutil.copyfileobj(image.file, buffer)
                        image_paths.append(str(file_path))

        result = await ingestion_service.ingest(
            db=db,
            title=title,
            file_name=file_name,
            file_type=file_type,
            content=extracted_content,
            images=image_paths if image_paths else None,
            user_id=user_id,
        )

        return {
            **result,
            "message": "Document ingested successfully via Swagger UI.",
            "uploaded_images": len(image_paths)
        }

    except Exception as e:
        raise RAGException(detail=f"Ingestion failed: {str(e)}")
    finally:
        # Clean up file handles
        for image in images or []:
            if hasattr(image, "file") and not image.file.closed:
                  image.file.close()