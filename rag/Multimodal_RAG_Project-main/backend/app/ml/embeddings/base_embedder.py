from abc import ABC, abstractmethod
from typing import List, Union, Any
import numpy as np
from PIL import Image


class BaseEmbedder(ABC):
      """Abstract base class for all embedders"""

      @abstractmethod
      async def embed_text(self, text: List[str]) -> np.ndarray:
            """Embed a list of text strings"""
            pass

      @abstractmethod
      async def embed_image(self, image: List[Union[str, Image.Image]]) -> np.ndarray:
            """Embed a list of images (file paths or PIL Images)"""
            pass

      @property
      @abstractmethod
      def dimension(self) -> int:
            """Return the embedding dimension """
            pass