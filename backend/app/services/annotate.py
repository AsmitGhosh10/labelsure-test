"""Visual evidence overlay (PRD §20).

Draws the OCR bounding box of every extracted declaration onto the surface it
was found on, colour-coded by the verdict of the rules that depend on that
field, and writes an annotated copy next to the inspection report.

Why this exists: a bounding box in JSON is not evidence an inspector can act
on. A highlighted region on the actual photograph is - they can see at a
glance that the MRP the system read is the MRP printed on the pack, and not
a nutrition-table number.

Nothing is invented: only boxes that OCR actually produced are drawn, each
labelled with the field name and the value that was read from it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Colour per verdict of the rules that consume the field
STATUS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "PASS": (26, 127, 55),           # green
    "FAIL": (198, 40, 40),           # red
    "MANUAL_REVIEW": (178, 106, 0),  # amber
    "UNKNOWN": (70, 70, 70),         # grey - detected, no rule consumed it
}

BOX_WIDTH = 4
LABEL_PAD = 4
MAX_LABEL_CHARS = 42


# The ruleset names declarations the way the statute does; the extractor names
# them the way the pipeline does. Without this map the overlay can only colour
# `net_quantity`, the single name both vocabularies happen to share.
DECLARATION_TO_FIELDS: Dict[str, Sequence[str]] = {
    "retail_sale_price": ("mrp",),
    "common_or_generic_name": ("product_name",),
    "commodity_identity": ("product_name",),
    "net_quantity": ("net_quantity",),
    "net_quantity_unit": ("net_quantity",),
    "retail_package_count_or_wholesale_net_quantity": ("net_quantity",),
    "manufacturer_name": ("manufacturer",),
    "manufacturer_address": ("manufacturer",),
    "manufacturer_or_importer_or_packer": ("manufacturer", "packer", "importer"),
    "manufacture_month_year": ("manufacturing_date", "packing_date"),
    "consumer_contact_name": ("consumer_care",),
    "consumer_contact_address": ("consumer_care",),
    "consumer_contact_phone": ("consumer_care",),
    # dimensions / sheet_dimensions / usable_sheet_count have no extracted
    # counterpart - they are physical measurements, deliberately unmapped.
}

# Fallback for the rules that carry no field list at all (22 of 31): the rule's
# category still says which declaration it concerns.
CATEGORY_TO_FIELDS: Dict[str, Sequence[str]] = {
    "mrp": ("mrp",),
    "commodity_identity": ("product_name",),
    "net_quantity": ("net_quantity",),
    "quantity_unit": ("net_quantity",),
    "quantity_language": ("net_quantity",),
    "unit_format": ("net_quantity",),
    "quantity_definition": ("net_quantity",),
    "count_declaration": ("net_quantity",),
    "date_declaration": ("manufacturing_date", "packing_date", "best_before"),
    "manufacturer_details": ("manufacturer", "packer", "importer"),
    "consumer_contact": ("consumer_care",),
}


def fields_for_rule(rule: Dict[str, Any]) -> List[str]:
    """Extractor field names a rule result speaks about."""
    names: List[str] = []
    for declared in rule.get("fields") or []:
        mapped = DECLARATION_TO_FIELDS.get(declared)
        if mapped:
            names.extend(mapped)
        elif declared in FIELD_NAMES_PASSTHROUGH:
            # already an extractor name
            names.append(declared)
    if not names:
        category = (rule.get("source") or {}).get("category") or ""
        names.extend(CATEGORY_TO_FIELDS.get(category, ()))
    # stable order, no duplicates
    seen = set()
    return [n for n in names if not (n in seen or seen.add(n))]


# Extractor field names that may legitimately appear in a rule's field list.
FIELD_NAMES_PASSTHROUGH = frozenset(
    {
        "mrp",
        "product_name",
        "brand",
        "net_quantity",
        "manufacturer",
        "packer",
        "importer",
        "manufacturing_date",
        "packing_date",
        "best_before",
        "batch_number",
        "consumer_care",
        "country_of_origin",
    }
)


def field_statuses(rule_results: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Worst rule status per extracted field (FAIL > MANUAL_REVIEW > PASS).

    A field is shown red if *any* rule that consumes it failed - the inspector
    should look at the worst case, not the most flattering one.
    """
    rank = {"PASS": 0, "MANUAL_REVIEW": 1, "FAIL": 2}
    worst: Dict[str, str] = {}
    for rule in rule_results or []:
        status = rule.get("status", "")
        if status not in rank:
            continue
        for name in fields_for_rule(rule):
            current = worst.get(name)
            if current is None or rank[status] > rank[current]:
                worst[name] = status
    return worst


def _bbox_rect(bbox: Sequence[Sequence[float]]) -> Optional[Tuple[int, int, int, int]]:
    try:
        xs = [float(p[0]) for p in bbox]
        ys = [float(p[1]) for p in bbox]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def plan_annotations(
    extracted_fields: Dict[str, Any],
    rule_results: Sequence[Dict[str, Any]],
    field_labels: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group the boxes to draw by source image name.

    Pure logic (no image I/O) so it is unit-testable without Pillow.
    """
    labels = field_labels or {}
    statuses = field_statuses(rule_results)
    per_image: Dict[str, List[Dict[str, Any]]] = {}
    for name, f in (extracted_fields or {}).items():
        if not isinstance(f, dict) or f.get("value") is None:
            continue
        rect = _bbox_rect(f.get("bbox") or [])
        if rect is None:
            continue
        source = f.get("source_image")
        if not source:
            continue
        status = statuses.get(name, "UNKNOWN")
        per_image.setdefault(source, []).append(
            {
                "field": name,
                "label": labels.get(name, name),
                "value": f.get("value"),
                "rect": rect,
                "status": status,
                "color": STATUS_COLORS.get(status, STATUS_COLORS["UNKNOWN"]),
                "confidence": f.get("extraction_confidence", 0.0),
            }
        )
    return per_image


def annotate_images(
    image_paths: Sequence[str],
    image_names: Sequence[str],
    extracted_fields: Dict[str, Any],
    rule_results: Sequence[Dict[str, Any]],
    output_dir: str,
    field_labels: Optional[Dict[str, str]] = None,
    inspection_id: str = "inspection",
) -> List[Dict[str, Any]]:
    """Write annotated copies of the surfaces that carry evidence.

    Returns one entry per annotated surface:
    ``{"name", "path", "boxes": [...]}``. Returns an empty list (never raises)
    if Pillow is unavailable or an image cannot be opened - a missing overlay
    must not fail an inspection.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []

    plan = plan_annotations(extracted_fields, rule_results, field_labels)
    if not plan:
        return []

    by_name = {name: path for name, path in zip(image_names, image_paths)}
    os.makedirs(output_dir, exist_ok=True)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    annotated: List[Dict[str, Any]] = []
    for name, boxes in plan.items():
        source_path = by_name.get(name)
        if not source_path or not os.path.exists(source_path):
            continue
        try:
            image = Image.open(source_path).convert("RGB")
        except Exception:
            continue
        draw = ImageDraw.Draw(image)
        for box in boxes:
            x0, y0, x1, y1 = box["rect"]
            color = tuple(box["color"])
            draw.rectangle([x0, y0, x1, y1], outline=color, width=BOX_WIDTH)
            caption = f"{box['label']}: {box['value']}"
            if len(caption) > MAX_LABEL_CHARS:
                caption = caption[: MAX_LABEL_CHARS - 1] + "…"
            try:
                tx0, ty0, tx1, ty1 = draw.textbbox((0, 0), caption, font=font)
                tw, th = tx1 - tx0, ty1 - ty0
            except Exception:
                tw, th = len(caption) * 8, 16
            # Caption above the box, or below it when there is no headroom
            ly = y0 - th - 2 * LABEL_PAD
            if ly < 0:
                ly = y1 + LABEL_PAD
            draw.rectangle(
                [x0, ly, x0 + tw + 2 * LABEL_PAD, ly + th + 2 * LABEL_PAD], fill=color
            )
            draw.text((x0 + LABEL_PAD, ly + LABEL_PAD), caption, fill=(255, 255, 255), font=font)

        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        out_path = os.path.join(output_dir, f"{inspection_id}_{safe}.annotated.png")
        try:
            image.save(out_path)
        except Exception:
            continue
        annotated.append(
            {
                "name": name,
                "path": out_path,
                "boxes": [
                    {
                        "field": b["field"],
                        "label": b["label"],
                        "value": b["value"],
                        "bbox": list(b["rect"]),
                        "status": b["status"],
                        "confidence": b["confidence"],
                    }
                    for b in boxes
                ],
            }
        )
    return annotated
