from typing import List, Union
import numpy as np
from PIL import Image
import torch
import asyncio
from ...core.config import settings

from .base_embedder import BaseEmbedder


class ImageEmbedder(BaseEmbedder):
      """Lazy-loaded CLIP image embedder using transformers."""

      def __init__(self):
            self.model_name = settings.CLIP_MODEL
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = None
            self._processor = None
            self._dimension = None
            self._lock = asyncio.Lock()

      async def _load_model(self):
            async with self._lock:
                  if self._model is None:
                        from transformers import CLIPProcessor, CLIPModel
                        self._model = CLIPModel.from_pretrained(self.model_name).to(self.device)
                        self._processor = CLIPProcessor.from_pretrained(self.model_name)
                        self._dimension = self._model.config.projection_dim

      async def embed_text(self, texts: List[str]) -> np.ndarray:
            await self._load_model()

            loop = asyncio.get_running_loop()

            def _process():
                  inputs = self._processor(text = texts, return_tensors = "pt", padding = True).to(self.device)
                  with torch.no_grad():
                        outputs = self._model.get_text_features(**inputs)
                        if hasattr(outputs, "pooler_output"):
                              features = outputs.pooler_output
                        else:
                              features = outputs
                        features = features / features.norm(dim = 1, keepdim=True)
                  return features.cpu().numpy()

            return await loop.run_in_executor(None, _process)

            

      async def embed_image(self, images: List[Union[str, Image.Image]]) -> np.ndarray:
            if not images:
                  return np.zeros((0, self.dimension), dtype=np.float32)

            await self._load_model()

            loop = asyncio.get_running_loop()

            # Step 1: Parallel image loading
            def _load_images():
                  # Convert paths to PIL
                  pil_images = []
                  valid_indices = []

                  for idx, img in enumerate(images):
                        try:
                              if isinstance(img, str):
                                    with Image.open(img) as im:
                                          pil_images.append(im.convert("RGB"))
                              else:
                                    pil_images.append(img.convert("RGB"))

                              valid_indices.append(idx)
                        except Exception:
                              continue
                  
                  return pil_images, valid_indices

            pil_images , valid_indices = await loop.run_in_executor(None, _load_images)
            
            if not pil_images:
                  return np.zeros((0, self.dimension), dtype=np.float32)

            def _process():
                  inputs = self._processor(
                        images=pil_images, 
                        return_tensors="pt", 
                        padding=True
                  ).to(self.device)

                  with torch.no_grad():
                        outputs = self._model.get_image_features(**inputs)

                        if hasattr(outputs, "pooler_output"):
                              features = outputs.pooler_output

                        features = features / features.norm(dim = 1, keepdim=True)

                  return features.cpu().numpy()

            embeddings =  await loop.run_in_executor(None, _process)

            return embeddings, valid_indices

      @property
      def dimension(self) -> int:
            if self._dimension is None:
                  import asyncio
                  asyncio.run(self._load_model())
            return self._dimension