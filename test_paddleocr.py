import sys
sys.path.insert(0, '/Users/mohit/Documents/Default Project')

print("Testing PaddleOCR import...")
try:
    from paddleocr import PaddleOCR
    print("PaddleOCR imported successfully!")
    
    # Initialize OCR (will download models on first run)
    print("Initializing PaddleOCR (this may download models)...")
    ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False, show_log=False)
    print("PaddleOCR initialized successfully!")
    print("Ready to process images.")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
