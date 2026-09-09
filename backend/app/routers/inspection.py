import os
import tempfile
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, PlainTextResponse

from backend.app.models import (
    QualityResponse,
    OCRResponse,
    EvaluateRulesRequest,
    InspectionResponse,
)
from backend.app.services.pipeline import InspectionPipeline, MAX_SURFACES
from backend.app.services.confidence import ConfidenceEngine
from backend.app.services.report_generator import ReportGenerator
from backend.app.services import hitl, legal, pdf_report
from backend.app import auth, database

router = APIRouter()

_pipeline: InspectionPipeline = None
_report_gen = ReportGenerator(output_dir="reports/inspections")

# --- upload validation (PRD §30 input validation) --------------------------
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp", "image/tiff",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 20 * 1024 * 1024))  # 20 MB


def get_pipeline() -> InspectionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = InspectionPipeline()
    return _pipeline


def _validate_upload(upload: UploadFile) -> None:
    """Reject anything that is not a plausible package photograph.

    Checked before the bytes ever reach disk: extension, declared content
    type, and (after read) size.
    """
    name = upload.filename or ""
    extension = os.path.splitext(name)[1].lower()
    if extension and extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{extension}'. Allowed: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported content type '{content_type}' - images only",
        )


def _save_upload(upload: UploadFile) -> str:
    _validate_upload(upload)
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=422, detail=f"Empty file: {upload.filename}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{upload.filename} is {len(data) // 1024} KB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1024} KB",
        )
    suffix = os.path.splitext(upload.filename or "")[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
    finally:
        tmp.close()
    return tmp.name


@router.post("/inspect")
def inspect_package(
    files: List[UploadFile] = File(...),
    product_name: Optional[str] = Form(None),
    pipeline: InspectionPipeline = Depends(get_pipeline),
    principal: Dict[str, Any] = Depends(auth.require_role(auth.INSPECTOR)),
):
    """Full multi-surface inspection: upload 1-6 photos of one package
    (front / back / sides / top / bottom, or a single flat label image)."""
    if len(files) < 1:
        raise HTTPException(status_code=422, detail="At least one image is required")
    if len(files) > MAX_SURFACES:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_SURFACES} surfaces supported, got {len(files)}",
        )
    paths = []
    try:
        for upload in files:
            paths.append(_save_upload(upload))
        result = pipeline.run_multi(
            paths,
            image_names=[u.filename for u in files],
            product_name=product_name,
        )
        # best-effort history persistence (never fails the inspection)
        database.save_inspection(result)
        database.write_audit(
            action="INSPECTION_RUN",
            actor=auth.principal_id(principal),
            actor_role=auth.principal_role(principal),
            entity_type="inspection",
            entity_id=result.get("inspection_id"),
            details={
                "decision": result.get("decision"),
                "surfaces": len(files),
                "product_name": product_name,
            },
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inspection failed: {e}")
    finally:
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.get("/inspections")
def list_inspections(limit: int = 50):
    """Recent inspection history (summaries)."""
    return {"inspections": database.list_inspections(limit=limit)}


@router.get("/inspections/search")
def search_inspections(
    product: Optional[str] = None,
    manufacturer: Optional[str] = None,
    brand: Optional[str] = None,
    inspection_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    violation_rule_id: Optional[str] = None,
    inspector_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    sort_by: str = "timestamp",
    descending: bool = True,
    limit: int = 100,
):
    """Search the inspection repository (PRD §28).

    Filters combine with AND. `sort_by` accepts timestamp, confidence,
    compliance_score, product_name, manufacturer or decision.
    """
    results = database.search_inspections(
        product=product,
        manufacturer=manufacturer,
        brand=brand,
        inspection_id=inspection_id,
        status=status,
        category=category,
        violation_rule_id=violation_rule_id,
        inspector_status=inspector_status,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        sort_by=sort_by,
        descending=descending,
        limit=limit,
    )
    for item in results:
        item["priority"] = hitl.queue_bucket(item.get("confidence"))
    return {"count": len(results), "inspections": results}


@router.get("/inspections/{inspection_id}")
def get_inspection(inspection_id: str):
    """Full stored response payload for one inspection."""
    result = database.get_inspection(inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return result


@router.get("/inspections/{inspection_id}/report", response_class=PlainTextResponse)
def get_markdown_report(inspection_id: str):
    """The markdown inspection report."""
    result = database.get_inspection(inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _report_gen.generate(
        result, inspector_decision=hitl.get_decision(inspection_id)
    )


@router.get("/inspections/{inspection_id}/report.pdf")
def get_pdf_report(inspection_id: str):
    """The PDF inspection report, including the inspector sign-off if recorded."""
    result = database.get_inspection(inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    output_dir = os.path.join("reports", "inspections")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{inspection_id}.pdf")
    try:
        pdf_report.generate_pdf_report(
            result, path, inspector_decision=hitl.get_decision(inspection_id)
        )
    except pdf_report.PDFUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    return FileResponse(
        path, media_type="application/pdf", filename=f"inspection_{inspection_id}.pdf"
    )


@router.get("/inspections/{inspection_id}/annotated/{index}")
def get_annotated_image(inspection_id: str, index: int):
    """Serve one annotated evidence image for a stored inspection.

    The stored inspection records absolute-ish paths written by the annotation
    service. Those paths came from our own pipeline, but a stored record is
    still data, so the resolved file must sit inside the evidence directory
    before it is served - otherwise a doctored record could read any file on
    the host.
    """
    result = database.get_inspection(inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    images = result.get("annotated_images") or []
    if index < 0 or index >= len(images):
        raise HTTPException(status_code=404, detail="No such annotated image")

    path = os.path.realpath(images[index].get("path", ""))
    root = os.path.realpath(get_pipeline().evidence_dir)
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Annotated image is unavailable")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/assess-quality", response_model=QualityResponse)
def assess_quality(upload: UploadFile = File(...), pipeline: InspectionPipeline = Depends(get_pipeline)):
    path = _save_upload(upload)
    try:
        return pipeline.assess_quality(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quality assessment failed: {e}")
    finally:
        os.unlink(path)


@router.post("/ocr", response_model=OCRResponse)
def run_cr(upload: UploadFile = File(...), pipeline: InspectionPipeline = Depends(get_pipeline)):
    path = _save_upload(upload)
    try:
        return pipeline.ocr(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")
    finally:
        os.unlink(path)


@router.post("/extract-fields")
def extract_fields(payload: Dict[str, Any], pipeline: InspectionPipeline = Depends(get_pipeline)):
    """Extract fields from pre-computed OCR output.

    Body: {"texts": [...], "confidences": [...], "bounding_boxes": [...]}
    """
    try:
        texts = payload["texts"]
        confidences = payload["confidences"]
        bounding_boxes = payload["bounding_boxes"]
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing field: {e}")

    fields = pipeline.extract_fields(texts, confidences, bounding_boxes)
    return {
        name: {
            "field_name": f.field_name,
            "value": f.value,
            "ocr_text": f.ocr_text,
            "ocr_confidence": f.ocr_confidence,
            "extraction_confidence": f.extraction_confidence,
            "confidence_level": f.confidence_level,
            "bbox": f.bbox,
            "reason": f.reason,
            "line_index": f.line_index,
        }
        for name, f in fields.items()
    }


@router.post("/evaluate-rules")
def evaluate_rules(payload: EvaluateRulesRequest, pipeline: InspectionPipeline = Depends(get_pipeline)):
    """Evaluate rules against extracted fields (with optional quality context)."""
    rule_results, compliance = pipeline.evaluate_rules(
        payload.extracted_fields, payload.image_quality
    )

    confidence_engine = ConfidenceEngine()
    ocr_result = (
        {"avg_confidence": payload.ocr_avg_confidence, "texts": [""] * 1}
        if payload.ocr_avg_confidence is not None
        else None
    )
    confidence = confidence_engine.compute(
        ocr_result, payload.extracted_fields, payload.image_quality, rule_results
    )
    confidence = confidence_engine.fuse_decision(confidence, compliance)

    from backend.app.services.compliance_score import compute_compliance_score

    rule_dicts = [r.to_dict() for r in rule_results]
    return {
        "rule_results": rule_dicts,
        "compliance_decision": compliance.to_dict(),
        "confidence": confidence.to_dict(),
        "compliance_score": compute_compliance_score(rule_dicts),
        "disclaimer": legal.SHORT_DISCLAIMER,
    }


@router.get("/rules")
def list_rules(pipeline: InspectionPipeline = Depends(get_pipeline)):
    """List the loaded ruleset (transparency: severity, source, verification)."""
    return {
        "ruleset": pipeline.rule_engine.ruleset_meta,
        "rules": [
            {
                "rule_id": r.get("rule_id"),
                "requirement": r.get("requirement"),
                "rule_type": r.get("rule_type"),
                "fields": r.get("fields"),
                "validation": r.get("validation"),
                "severity": r.get("severity"),
                "source": r.get("source"),
                "verified": r.get("verified", False),
            }
            for r in pipeline.rule_engine.rules
        ],
    }
