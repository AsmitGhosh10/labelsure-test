import cv2
import numpy as np
from typing import Dict, Any, Tuple

class ImageQualityGate:
    """Assess image quality before OCR."""
    
    def __init__(self):
        self.blur_threshold = 100.0
        self.brightness_min = 50.0
        self.brightness_max = 240.0
        self.contrast_threshold = 30.0
        self.glare_threshold = 0.15
        self.perspective_threshold = 0.3
    
    def assess(self, image_path: str) -> Dict[str, Any]:
        img = cv2.imread(image_path)
        if img is None:
            return {"usable": False, "reason": "Could not load image", "score": 0.0}
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        
        # 1. Blur (Laplacian variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_pass = laplacian_var >= self.blur_threshold
        
        # 2. Brightness (mean pixel value)
        brightness = gray.mean()
        brightness_pass = self.brightness_min <= brightness <= self.brightness_max
        
        # 3. Contrast (standard deviation)
        contrast = gray.std()
        contrast_pass = contrast >= self.contrast_threshold
        
        # 4. Glare (overexposed pixels percentage)
        overexposed = np.sum(gray > 250) / gray.size
        glare_pass = overexposed <= self.glare_threshold
        
        # 5. Perspective distortion (skew detection via contour analysis)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=w*0.3, maxLineGap=20)
        
        perspective_pass = True
        skew_ratio = 0.0
        if lines is not None and len(lines) > 0:
            angles = []
            for line in lines:
                # OpenCV 4 yields (N, 1, 4); OpenCV 5 yields (N, 4).
                coords = line[0] if getattr(line, "ndim", 1) > 1 else line
                x1, y1, x2, y2 = coords
                angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180.0 / np.pi)
                if angle > 45:
                    angle = 90 - angle
                angles.append(angle)
            if angles:
                skew_ratio = np.mean(angles) / 90.0
                perspective_pass = skew_ratio <= self.perspective_threshold
        
        # Composite score (0-100)
        score = 0.0
        if blur_pass: score += 25
        if brightness_pass: score += 25
        if contrast_pass: score += 20
        if glare_pass: score += 15
        if perspective_pass: score += 15
        
        usable = score >= 60 and blur_pass and brightness_pass
        
        return {
            "usable": bool(usable),
            "score": float(score),
            "checks": {
                "blur": {"value": float(round(laplacian_var, 2)), "pass": bool(blur_pass), "threshold": float(self.blur_threshold)},
                "brightness": {"value": float(round(brightness, 2)), "pass": bool(brightness_pass), "min": float(self.brightness_min), "max": float(self.brightness_max)},
                "contrast": {"value": float(round(contrast, 2)), "pass": bool(contrast_pass), "threshold": float(self.contrast_threshold)},
                "glare": {"value": float(round(overexposed, 4)), "pass": bool(glare_pass), "threshold": float(self.glare_threshold)},
                "perspective": {"value": float(round(skew_ratio, 4)), "pass": bool(perspective_pass), "threshold": float(self.perspective_threshold)}
            }
        }
