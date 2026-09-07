from pathlib import Path
from typing import BinaryIO
from pypdf import PdfReader
from docx import Document
import asyncio
import shutil
import structlog

logger = structlog.get_logger()


async def save_upload_file(file: BinaryIO, filename: str, upload_dir: str = "data/uploads/file") -> str:
      """Save uploaded file safely and return path."""
      upload_path = Path(upload_dir)
      upload_path.mkdir(parents=True, exist_ok=True)


      file_path = upload_path / filename
      with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file, buffer)

      return str(file_path)

async def extract_text_from_upload(file_path : str, file_type: str) -> str:
      """
            Extract text from uploaded file.
            Currently supports txt, pdf, docx files.
            Safe fallback for unknown types.
      """
      file_type = file_type.lower()
      
      loop = asyncio.get_running_loop()

      def _extract() -> str:
            try:
                  # ✅ TXT
                  if file_type in ["txt", "text"]:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                              return f.read()
                  
                  elif file_type == "pdf":
                        reader = PdfReader(file_path)
                        texts = []

                        for page in reader.pages:
                              text = page.extract_text()
                              if text :
                                    texts.append(text)
                              
                        return "\n".join(texts)
                  
                  elif file_type == "docx":
                        doc = Document(file_path)
                        return "\n".join([para.text for para in doc.paragraphs])
                  
                  return ""
            
            except Exception  as e:
                  logger.error(
                        f"Extract Error",
                        file_path = file_path,
                        file_type = file_type,
                        error_msg = str(e)
                  )

                  return ""

      return await loop.run_in_executor(None, _extract)
