import json
import os
from datetime import datetime

def generate_md_report(json_path: str, output_path: str):
    with open(json_path, 'r') as f:
        results = json.load(f)
    
    # Filter only the 4 real images (not sample_package or synthetic)
    real_images = [r for r in results if 'image' in r and os.path.basename(r['image']).startswith('image')]
    
    lines = []
    lines.append("# OCR Test Report — Real Package Images")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Images Tested:** {len(real_images)}")
    lines.append(f"**Engine:** PaddleOCR v3.7.0 (PP-OCRv6_medium)")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Summary Table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Image | Quality Score | Usable | MRP | Net Qty | Manufacturer | Date | Consumer Care |")
    lines.append("|-------|--------------|--------|-----|---------|--------------|------|---------------|")
    
    for r in real_images:
        img_name = os.path.basename(r['image'])
        q = r.get('quality', {})
        score = q.get('score', 0)
        usable = "Yes" if q.get('usable') else "No"
        fields = r.get('detected_fields', {})
        
        def field_status(field):
            f = fields.get(field, {})
            return "Found" if f.get('found') else "Missing"
        
        lines.append(f"| {img_name} | {score}/100 | {usable} | {field_status('mrp')} | {field_status('net_quantity')} | {field_status('manufacturer')} | {field_status('date')} | {field_status('consumer_care')} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Per-image detailed breakdown
    for r in real_images:
        img_name = os.path.basename(r['image'])
        lines.append(f"## {img_name}")
        lines.append("")
        
        # Quality
        q = r.get('quality', {})
        lines.append("### Image Quality Assessment")
        lines.append("")
        lines.append(f"- **Overall Score:** {q.get('score', 0)}/100")
        lines.append(f"- **Usable for OCR:** {'Yes' if q.get('usable') else 'No'}")
        lines.append("")
        lines.append("| Check | Value | Threshold | Status |")
        lines.append("|-------|-------|-----------|--------|")
        for check_name, check_data in q.get('checks', {}).items():
            status = "PASS" if check_data.get('pass') else "FAIL"
            if check_name == 'brightness':
                thresh = f"{check_data.get('min', 0)}-{check_data.get('max', 0)}"
            else:
                thresh = str(check_data.get('threshold', 'N/A'))
            lines.append(f"| {check_name.capitalize()} | {check_data.get('value', 'N/A')} | {thresh} | {status} |")
        lines.append("")
        
        # OCR Results
        ocr = r.get('ocr')
        if ocr:
            lines.append("### OCR Results")
            lines.append("")
            lines.append(f"- **Lines Detected:** {len(ocr.get('texts', []))}")
            lines.append(f"- **Average Confidence:** {ocr.get('avg_confidence', 0):.3f}")
            lines.append("")
            lines.append("#### All Detected Text")
            lines.append("")
            lines.append("| # | Confidence | Text |")
            lines.append("|---|-----------|------|")
            for i, (text, conf) in enumerate(zip(ocr.get('texts', []), ocr.get('confidences', [])), 1):
                # Escape pipe characters in text
                safe_text = text.replace('|', '\\|').replace('\n', ' ')
                lines.append(f"| {i} | {conf:.3f} | {safe_text} |")
            lines.append("")
        
        # Field Detection
        fields = r.get('detected_fields', {})
        lines.append("### Mandatory Field Detection")
        lines.append("")
        lines.append("| Field | Status | Extracted Value | Confidence |")
        lines.append("|-------|--------|-----------------|------------|")
        
        field_names = {
            'mrp': 'MRP (Max Retail Price)',
            'net_quantity': 'Net Quantity',
            'manufacturer': 'Manufacturer',
            'date': 'Manufacturing/Packing Date',
            'consumer_care': 'Consumer Care Info'
        }
        
        for key, label in field_names.items():
            f = fields.get(key, {})
            if f.get('found'):
                val = f.get('value', 'N/A')
                conf = f.get('confidence', 0)
                lines.append(f"| {label} | Found | {val} | {conf:.3f} |")
            else:
                lines.append(f"| {label} | **MISSING** | — | — |")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Overall Analysis
    lines.append("## Overall Analysis")
    lines.append("")
    
    total = len(real_images)
    mrp_found = sum(1 for r in real_images if r.get('detected_fields', {}).get('mrp', {}).get('found'))
    qty_found = sum(1 for r in real_images if r.get('detected_fields', {}).get('net_quantity', {}).get('found'))
    mfg_found = sum(1 for r in real_images if r.get('detected_fields', {}).get('manufacturer', {}).get('found'))
    date_found = sum(1 for r in real_images if r.get('detected_fields', {}).get('date', {}).get('found'))
    care_found = sum(1 for r in real_images if r.get('detected_fields', {}).get('consumer_care', {}).get('found'))
    
    lines.append(f"- **MRP Detection Rate:** {mrp_found}/{total} ({mrp_found/total*100:.0f}%)")
    lines.append(f"- **Net Quantity Detection Rate:** {qty_found}/{total} ({qty_found/total*100:.0f}%)")
    lines.append(f"- **Manufacturer Detection Rate:** {mfg_found}/{total} ({mfg_found/total*100:.0f}%)")
    lines.append(f"- **Date Detection Rate:** {date_found}/{total} ({date_found/total*100:.0f}%)")
    lines.append(f"- **Consumer Care Detection Rate:** {care_found}/{total} ({care_found/total*100:.0f}%)")
    lines.append("")
    
    lines.append("### Key Observations")
    lines.append("")
    lines.append("1. **Net Quantity & Manufacturer:** Detected in 100% of images. Strong performance.")
    lines.append("2. **Consumer Care:** Detected in 100% of images. Phone numbers and emails are well-recognized.")
    lines.append("3. **MRP:** Only detected in 2/4 images (50%). Real packages often have MRP in small text, on a separate price sticker, or formatted unconventionally (e.g., 'M.R.P. (Inclusive of all taxes).20.00' with no space before the number).")
    lines.append("4. **Date:** Only detected in 1/4 images (25%). Dates are often stamped or printed in very small fonts, or use non-standard formats. This is the weakest detection area.")
    lines.append("5. **Image Quality:** All 4 images passed the quality gate, though glare was flagged in 2 images (threshold may need tuning for glossy packaging).")
    lines.append("")
    
    lines.append("### Recommendations")
    lines.append("")
    lines.append("1. **Improve MRP regex:** Handle edge cases like 'M.R.P.', 'Max Retail Price', 'Unit Selling Price', and numbers directly attached to labels without spaces.")
    lines.append("2. **Improve Date detection:** Add support for stamped dates, batch-code embedded dates, and more Indian formats (e.g., 'Mfd: 17Jul28', 'Use By: 15Nov28').")
    lines.append("3. **Glare threshold:** Consider raising the glare threshold for glossy snack packets where specular reflection is common but does not obstruct text.")
    lines.append("4. **Multi-image support:** As planned, combining front + back + side views would help capture MRP and dates that appear only on specific sides.")
    lines.append("")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Report saved to: {output_path}")

if __name__ == "__main__":
    generate_md_report(
        "ocr_test_results/ocr_test_results.json",
        "ocr_test_results/OCR_TEST_REPORT.md"
    )
