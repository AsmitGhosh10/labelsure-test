"""Targeted manual-review actions.

Post-processor only - it never touches rule evaluation or OCR/extraction
logic. For every MANUAL_REVIEW rule it derives a concrete, targeted action:

- which field is unresolved
- the exact reason
- WHERE to check (base of can, neck of bottle, QR reference, the unreadable
  surface to recapture, ...) instead of "inspect the whole package"
- the source image to look at
- the confidence of the current evidence

All verified (PASS) fields stay PASS - only unresolved items get actions.
"""

from typing import List, Dict, Any, Optional

from backend.app.services.report_generator import FIELD_LABELS
from backend.app.services.rule_engine import MANUAL_REVIEW

# Rule category -> our extracted field names
CATEGORY_FIELDS = {
    "mrp": ["mrp"],
    "commodity_identity": ["product_name"],
    "net_quantity": ["net_quantity"],
    "quantity_unit": ["net_quantity"],
    "quantity_language": ["net_quantity"],
    "unit_format": ["net_quantity"],
    "date_declaration": ["manufacturing_date", "packing_date"],
    "manufacturer_details": ["manufacturer", "packer", "importer"],
    "consumer_contact": ["consumer_care"],
    "declaration_legibility": ["mrp", "net_quantity"],
    "language": [],
}

LOCATION_TEXT = {
    "base": "base/bottom of the package",
    "bottom": "base/bottom of the package",
    "neck": "neck of the bottle/can",
    "lid": "lid of the package",
    "cap": "cap/lid of the package",
    "back": "back label",
    "front": "front label",
    "top": "top of the package",
}

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def build_review_actions(
    rule_results: List[Any],
    extracted_fields: Dict[str, Any],
    pointers: Optional[List[Dict[str, Any]]],
    images: Optional[List[Dict[str, Any]]],
    overall_confidence: float,
) -> List[Dict[str, Any]]:
    """Derive targeted review actions from MANUAL_REVIEW rule results."""

    def field_dict(name: str) -> Optional[Dict[str, Any]]:
        f = extracted_fields.get(name)
        return f if isinstance(f, dict) else None

    actions: List[Dict[str, Any]] = []
    seen: set = set()

    review_results = [r for r in rule_results if getattr(r, "status", None) == MANUAL_REVIEW]
    review_results.sort(key=lambda r: SEVERITY_ORDER.get(getattr(r, "severity", ""), 9))

    for r in review_results:
        category = (getattr(r, "source", {}) or {}).get("category", "")
        our_fields = CATEGORY_FIELDS.get(category, [])
        if category not in CATEGORY_FIELDS:
            # meta-rules (Rule 4 aggregate, language summary) just echo the
            # per-field reviews - no separate action
            continue
        reason = getattr(r, "reason", "")
        reason_l = reason.lower()
        evidence = getattr(r, "evidence", {}) or {}

        # the concrete field instance this review is about
        f = None
        field_name = None
        for name in our_fields:
            cand = field_dict(name)
            if cand is not None:
                f = cand
                field_name = name
                break
        if field_name is None and our_fields:
            field_name = our_fields[0]
            f = field_dict(field_name)

        # --- where to check -------------------------------------------
        pointer = evidence.get("reference_pointer")
        if pointer is not None:
            location = LOCATION_TEXT.get(
                str(pointer.get("location", "")).lower(),
                "another part of the package",
            )
            check = f"{location} - the label states this information is there"
            source_image = pointer.get("image")
        elif "address" in reason_l:
            check = (
                "manufacturing unit address - typically behind the QR code / "
                "first-letter reference on the label"
            )
            source_image = (f or {}).get("source_image")
        elif "telephone" in reason_l:
            check = "consumer care panel - verify the telephone number"
            source_image = (f or {}).get("source_image")
        elif "legibility" in reason_l or "contrast" in reason_l or category == "declaration_legibility":
            check = "MRP / net quantity declaration lines - verify contrast and legibility"
            source_image = None
        elif f is not None and f.get("value") is not None:
            # LOW-confidence or unvalidated detection: re-read that line
            check = (
                f"re-read the declaration on this surface "
                f"(detected value: '{f.get('value')}')"
            )
            source_image = f.get("source_image")
        elif "image quality" in reason_l or "insufficient" in reason_l:
            unusable = [
                (i or {}).get("name") for i in (images or []) if not (i or {}).get("usable", True)
            ]
            unusable = [u for u in unusable if u]
            if unusable:
                check = f"recapture this surface - unreadable (blur/glare): {', '.join(unusable)}"
                source_image = unusable[0]
            else:
                check = "recapture a sharper photo of the package"
                source_image = None
        else:
            check = "remaining package surfaces not captured"
            source_image = None

        if field_name is None:
            field_name = r.rule_id
        field_label = FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())

        dedupe_key = (field_name, check)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        current_value = (f or {}).get("value") if f is not None else None
        confidence = (
            float(f.get("extraction_confidence", 0.0))
            if (f is not None and f.get("value") is not None)
            else float(overall_confidence)
        )

        actions.append(
            {
                "field": field_name,
                "field_label": field_label,
                "rule_id": r.rule_id,
                "rule_reference": (getattr(r, "source", {}) or {}).get("rule", ""),
                "status": "MANUAL_REVIEW",
                "severity": getattr(r, "severity", ""),
                "reason": reason,
                "check_location": check,
                "source_image": source_image,
                "confidence": round(confidence, 3),
                "current_value": current_value,
            }
        )

    return actions
