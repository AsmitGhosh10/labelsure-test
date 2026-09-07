import json
import os
from typing import List, Dict, Any
from paddleocr import PaddleOCR
from backend.app.services.quality_gate import ImageQualityGate
from backend.app.services.field_extraction import FieldExtractor

class OCRTester:
    def __init__(self):
        print("Initializing PaddleOCR...")
        self.ocr = PaddleOCR(
            use_textline_orientation=True,
            lang='en'
        )
        self.quality_gate = ImageQualityGate()
        self.field_extractor = FieldExtractor()
        print("Ready.")
    
    def test_image(self, image_path: str) -> Dict[str, Any]:
        """Run full OCR test on a single image."""
        print(f"\n{'='*60}")
        print(f"Testing: {os.path.basename(image_path)}")
        print(f"{'='*60}")
        
        result = {
            "image": image_path,
            "quality": None,
            "ocr": None,
            "extracted_fields": {}
        }
        
        # Step 1: Quality Gate
        print("\n[1/3] Image Quality Assessment...")
        quality = self.quality_gate.assess(image_path)
        result["quality"] = quality
        print(f"  Usable: {quality['usable']} (Score: {quality['score']}/100)")
        for check, data in quality['checks'].items():
            status = "PASS" if data['pass'] else "FAIL"
            print(f"  - {check}: {status} (value={data['value']})")
        
        if not quality['usable']:
            print("  Image quality too poor. Skipping OCR.")
            return result
        
        # Step 2: OCR
        print("\n[2/3] Running PaddleOCR...")
        ocr_result = self.ocr.predict(image_path)
        
        extracted_texts = []
        bounding_boxes = []
        confidences = []
        
        if ocr_result and len(ocr_result) > 0:
            result_data = ocr_result[0]
            rec_texts = result_data.get('rec_texts', [])
            rec_scores = result_data.get('rec_scores', [])
            rec_polys = result_data.get('rec_polys', [])
            
            for text, conf, bbox in zip(rec_texts, rec_scores, rec_polys):
                extracted_texts.append(text)
                bounding_boxes.append(bbox.tolist() if hasattr(bbox, 'tolist') else bbox)
                confidences.append(conf)
                print(f"  [{conf:.3f}] {text}")
        
        result["ocr"] = {
            "texts": extracted_texts,
            "bounding_boxes": bounding_boxes,
            "confidences": confidences,
            "avg_confidence": round(sum(confidences)/len(confidences), 4) if confidences else 0.0
        }
        
        # Step 3: Field Extraction
        print("\n[3/3] Extracting Fields...")
        fields = self.field_extractor.extract_all(extracted_texts, confidences, bounding_boxes)
        
        # Convert to serializable dict
        serializable_fields = {}
        for key, field in fields.items():
            serializable_fields[key] = {
                "field_name": field.field_name,
                "value": field.value,
                "ocr_text": field.ocr_text,
                "ocr_confidence": field.ocr_confidence,
                "extraction_confidence": field.extraction_confidence,
                "confidence_level": field.confidence_level,
                "bbox": field.bbox,
                "reason": field.reason,
                "line_index": field.line_index
            }
            status = field.confidence_level
            print(f"  - {key}: {status} | value={field.value} | reason={field.reason}")
        
        result["extracted_fields"] = serializable_fields
        
        return result
    
    def batch_test(self, image_dir: str, output_dir: str = "ocr_test_results"):
        """Test all images in a directory."""
        os.makedirs(output_dir, exist_ok=True)
        
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            import glob
            image_files.extend(glob.glob(os.path.join(image_dir, ext)))
            image_files.extend(glob.glob(os.path.join(image_dir, ext.upper())))
        
        if not image_files:
            print(f"No images found in {image_dir}")
            return
        
        print(f"Found {len(image_files)} images to test.")
        
        all_results = []
        for img_path in sorted(image_files):
            result = self.test_image(img_path)
            all_results.append(result)
        
        # Save results
        output_file = os.path.join(output_dir, "phase4_extraction_results.json")
        with open(output_file, 'w') as f:
            json.dump(all_results, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"Results saved to: {output_file}")
        print(f"{'='*60}")
        
        # Summary
        print("\nSUMMARY:")
        print(f"Total images: {len(all_results)}")
        print(f"Quality passed: {sum(1 for r in all_results if r['quality']['usable'])}")
        print(f"Quality failed: {sum(1 for r in all_results if not r['quality']['usable'])}")
        
        for field_name in ['mrp', 'net_quantity', 'manufacturer', 'packer', 'importer',
                           'manufacturing_date', 'packing_date', 'best_before', 
                           'batch_number', 'consumer_care', 'country_of_origin']:
            found = sum(1 for r in all_results 
                       if r.get('extracted_fields', {}).get(field_name, {}).get('value') is not None)
            print(f"  {field_name}: detected in {found}/{len(all_results)} images")

if __name__ == "__main__":
    import sys
    
    tester = OCRTester()
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        if os.path.isdir(image_path):
            tester.batch_test(image_path)
        else:
            result = tester.test_image(image_path)
            print("\n" + json.dumps(result, indent=2))
    else:
        print("Usage:")
        print("  python test_ocr.py <image_file>")
        print("  python test_ocr.py <image_directory>")
        print("\nPut your package images in: test_images/")
        print("Then run: python test_ocr.py test_images/")
