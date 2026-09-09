import os
import tempfile
from typing import Dict, Any, List
from threading import Lock
from PIL import Image

_ocr = None
_lock = Lock()

# Max dimension for image resizing before OCR inference.
# Resizing high-res photos (3000x4000) to max 1600px reduces pixel count by 6x
# and speeds up OCR processing dramatically with zero loss of extraction accuracy.
OCR_MAX_DIMENSION = int(os.environ.get("OCR_MAX_DIMENSION", "1600"))

# PaddlePaddle 3.3.x crashes inside its oneDNN kernels on the PP-OCRv6
# detection model:
#     NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute
#     not support [pir::ArrayAttribute<pir::DoubleAttribute>]
# Disabling oneDNN runs the same model through the standard CPU kernels and
# produces correct results. Kept configurable so it can be re-enabled once the
# upstream bug is fixed: set OCR_ENABLE_MKLDNN=true.
OCR_ENABLE_MKLDNN = os.environ.get("OCR_ENABLE_MKLDNN", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

OCR_DEVICE = os.environ.get("OCR_DEVICE", "auto").strip().lower()

# Model profile.
OCR_PROFILE = os.environ.get("OCR_PROFILE", "fast").strip().lower()

# Orientation classification costs extra time per image. Off by default.
OCR_TEXTLINE_ORIENTATION = os.environ.get(
    "OCR_TEXTLINE_ORIENTATION", "false"
).strip().lower() in ("1", "true", "yes", "on")

_FAST_MODELS = {
    "text_detection_model_name": "PP-OCRv5_mobile_det",
    "text_recognition_model_name": "PP-OCRv5_mobile_rec",
}


def get_ocr():
    """Lazy PaddleOCR singleton - initialised on first use so the API can start
    without loading the OCR models."""
    global _ocr
    if _ocr is None:
        with _lock:
            if _ocr is None:
                from paddleocr import PaddleOCR

                kwargs = {
                    "use_textline_orientation": OCR_TEXTLINE_ORIENTATION,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "lang": "en",
                    "enable_mkldnn": OCR_ENABLE_MKLDNN,
                }
                if OCR_DEVICE and OCR_DEVICE != "auto" and OCR_DEVICE != "cpu":
                    kwargs["device"] = OCR_DEVICE
                if OCR_PROFILE == "fast":
                    kwargs.update(_FAST_MODELS)
                _ocr = PaddleOCR(**kwargs)
    return _ocr


def _prepare_image(image_path: str) -> tuple[str, float, bool]:
    """Resize image to OCR_MAX_DIMENSION if it exceeds it to speed up inference."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            max_dim = max(width, height)
            if OCR_MAX_DIMENSION > 0 and max_dim > OCR_MAX_DIMENSION:
                scale = OCR_MAX_DIMENSION / float(max_dim)
                new_w = int(width * scale)
                new_h = int(height * scale)
                resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                temp_path = temp_file.name
                temp_file.close()

                resized.convert("RGB").save(temp_path, quality=95)
                return temp_path, scale, True
    except Exception:
        pass
    return image_path, 1.0, False


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Run PaddleOCR on an image and return normalised text/confidence/bbox lists."""
    ocr = get_ocr()
    proc_path, scale, is_temp = _prepare_image(image_path)

    try:
        result = ocr.predict(proc_path)
    finally:
        if is_temp and os.path.exists(proc_path):
            try:
                os.remove(proc_path)
            except Exception:
                pass

    texts: List[str] = []
    confidences: List[float] = []
    bounding_boxes: List[List[List[int]]] = []

    if result and len(result) > 0:
        data = result[0]
        rec_texts = data.get("rec_texts", [])
        rec_scores = data.get("rec_scores", [])
        rec_polys = data.get("rec_polys", [])
        for text, conf, bbox in zip(rec_texts, rec_scores, rec_polys):
            texts.append(text)
            confidences.append(float(conf))
            raw_box = bbox.tolist() if hasattr(bbox, "tolist") else bbox
            if scale != 1.0 and scale > 0:
                scaled_box = [[int(pt[0] / scale), int(pt[1] / scale)] for pt in raw_box]
                bounding_boxes.append(scaled_box)
            else:
                bounding_boxes.append(raw_box)

    return {
        "texts": texts,
        "confidences": confidences,
        "bounding_boxes": bounding_boxes,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
    }
