import os
from typing import Dict, Any, List
from threading import Lock

_ocr = None
_lock = Lock()

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

# Model profile. Measured on one CPU core, 1957x2648 label photo,
# paddlepaddle 3.3.1 / paddleocr 3.7.0, oneDNN disabled:
#
#   accurate  PP-OCRv6_medium  ~140 s/image   avg confidence 0.917  (default)
#   fast      PP-OCRv5_mobile   ~62 s/image   avg confidence 0.864
#
# Accuracy is the default because OCR confidence propagates straight into the
# compliance decision: the confidence engine routes anything under 0.70 to
# MANUAL_REVIEW, so a cheaper model buys speed by sending more packages to a
# human. Set OCR_PROFILE=fast to trade the other way.
OCR_PROFILE = os.environ.get("OCR_PROFILE", "accurate").strip().lower()

# Orientation classification costs ~8 s/image and only matters for rotated
# text lines. Off by default for single-line-orientation label photos.
OCR_TEXTLINE_ORIENTATION = os.environ.get(
    "OCR_TEXTLINE_ORIENTATION", "true"
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
                    "lang": "en",
                    "enable_mkldnn": OCR_ENABLE_MKLDNN,
                }
                if OCR_PROFILE == "fast":
                    kwargs.update(_FAST_MODELS)
                _ocr = PaddleOCR(**kwargs)
    return _ocr


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Run PaddleOCR on an image and return normalised text/confidence/bbox lists."""
    ocr = get_ocr()
    result = ocr.predict(image_path)

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
            bounding_boxes.append(bbox.tolist() if hasattr(bbox, "tolist") else bbox)

    return {
        "texts": texts,
        "confidences": confidences,
        "bounding_boxes": bounding_boxes,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
    }
