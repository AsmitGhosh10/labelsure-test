from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/legal_metrology"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Image Quality Thresholds
    BLUR_THRESHOLD: float = 100.0  # Laplacian variance
    BRIGHTNESS_MIN: float = 50.0
    BRIGHTNESS_MAX: float = 240.0
    CONTRAST_THRESHOLD: float = 30.0
    GLARE_THRESHOLD: float = 0.15  # percentage of overexposed pixels
    PERSPECTIVE_THRESHOLD: float = 0.3  # max skew ratio
    
    # Confidence Thresholds
    HIGH_CONFIDENCE: float = 0.90
    REVIEW_THRESHOLD: float = 0.70
    
    # PaddleOCR
    OCR_LANGUAGE: str = "en"
    OCR_USE_GPU: bool = False
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
