from typing import Optional
from pathlib import Path
from fastapi import Form, APIRouter, File, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import shutil

from ....services.ingestion_service import IngestionService
from ....core.dependencies import get_db
from ....utils.file_handlers import extract_text_from_upload,save_upload_file
from ....core.exceptions import RAGException

api_router = APIRouter(tags=["upload"])
ingestion_service = IngestionService()

@api_router.post("/file")
async def upload_file(
      title:str = Form(description="Title of the file"),
      file:UploadFile = File(description="Upload file of type 'txt' "),
      user_id: int | None = Form(default=None),
      db: AsyncSession = Depends(get_db)
):
      """
            Upload a file and extract the file content.
            Extracts file name and type internally.
      """

      file_name = file.filename or "unknown"
      if "." in file_name:
            file_type = file_name.split(".")[-1]
      else:
            file_type = "unknown"
      
      file_path = await save_upload_file(file.file, file.filename)

      extracted_text: str = await extract_text_from_upload(file_path, file_type)

      result = await ingestion_service.ingest_file(
            db= db,
            title = title,
            file_name = file_name,
            file_type = file_type,
            content = extracted_text,
            user_id = user_id,
      )

      return result 

@api_router.post("/image")
async def upload_image(
      title: str = Form(...),
      image: UploadFile = File(...),
      user_id: int | None = None,
      db: AsyncSession = Depends(get_db)
):
      """
            Image only upload for v2
      """
      try:
            file_name = image.filename or "unknown"

            if "." in file_name:
                  file_type = file_name.split(".")[-1]
            else:
                  file_type = "unknown"
            #===================
            #Save image to disk
            #===================
            upload_dir = Path("data/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_path = upload_dir / file_name
            with open(file_path, "wb") as buffer:
                  shutil.copyfileobj(image.file, buffer)
            #===================
            #Call service layer
            #===================
            if "." in file_name:
                  file_name =file_name.split(".")[-2]
            result = await ingestion_service.ingest_image(
                  db = db,
                  title = title,
                  file_name = file_name,
                  file_type = file_type,
                  image_path = str(file_path),
                  user_id = user_id,
            )

            return {
                  **result,
                  "message": "Image ingested successfully",
            }
      except Exception as e:
            raise RAGException(detail = f"Image ingestion failed: {str(e)}")
      finally:
            if hasattr(image, "file") and not image.file.closed:
                  image.file.close()
