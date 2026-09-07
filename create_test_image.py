import numpy as np
import cv2
import os

def create_test_package_image(output_path: str = "test_images/sample_package.jpg"):
    """Create a synthetic package image for initial testing."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Create a 800x600 image simulating a product package
    img = np.ones((600, 800, 3), dtype=np.uint8) * 240  # light gray background
    
    # Package border
    cv2.rectangle(img, (50, 50), (750, 550), (0, 0, 0), 3)
    cv2.rectangle(img, (50, 50), (750, 550), (255, 255, 255), -1)
    
    # Product name
    cv2.putText(img, "PREMIUM BISCUITS", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    
    # Net quantity
    cv2.putText(img, "Net Qty: 500g", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    
    # MRP
    cv2.putText(img, "MRP: Rs. 250.00", (100, 280), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 139), 3)
    
    # Manufacturer
    cv2.putText(img, "Manufactured By:", (100, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.putText(img, "ABC Foods Pvt. Ltd.", (100, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(img, "Mumbai, Maharashtra", (100, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)
    
    # Date
    cv2.putText(img, "Mfg. Date: 15/08/2024", (400, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(img, "Best Before: 6 months from Mfg.", (400, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    
    # Consumer care
    cv2.putText(img, "Customer Care: 1800-123-4567", (100, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 100, 0), 2)
    cv2.putText(img, "Email: care@abcfoods.com", (100, 550), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 0), 2)
    
    cv2.imwrite(output_path, img)
    print(f"Created test image: {output_path}")
    return output_path

if __name__ == "__main__":
    create_test_package_image()
    print("\nNow run: python test_ocr.py test_images/sample_package.jpg")
