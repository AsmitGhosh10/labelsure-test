import cv2
import numpy as np
import os

def generate_distorted_variants(input_image: str, output_dir: str = "test_images/synthetic"):
    """Generate distorted variants of a single image for testing."""
    os.makedirs(output_dir, exist_ok=True)
    
    img = cv2.imread(input_image)
    if img is None:
        print(f"Could not load {input_image}")
        return
    
    base_name = os.path.splitext(os.path.basename(input_image))[0]
    h, w = img.shape[:2]
    
    variants = []
    
    # 1. Perspective distortion
    pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    pts2 = np.float32([[w*0.1, h*0.05], [w*0.9, 0], [w*0.05, h*0.95], [w*0.95, h]])
    M = cv2.getPerspectiveTransform(pts1, pts2)
    perspective = cv2.warpPerspective(img, M, (w, h))
    variants.append(("perspective", perspective))
    
    # 2. Blur (motion + gaussian)
    blurred = cv2.GaussianBlur(img, (15, 15), 0)
    variants.append(("blur", blurred))
    
    # 3. Glare (bright spot overlay)
    glare = img.copy()
    cv2.circle(glare, (w//3, h//3), min(w,h)//4, (255, 255, 255), -1)
    glare = cv2.addWeighted(img, 0.7, glare, 0.3, 0)
    variants.append(("glare", glare))
    
    # 4. Rotation
    angle = 15
    M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    rotated = cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))
    variants.append(("rotation", rotated))
    
    # 5. Low contrast
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    low_contrast = cv2.merge([l, a, b])
    low_contrast = cv2.cvtColor(low_contrast, cv2.COLOR_LAB2BGR)
    variants.append(("low_contrast", low_contrast))
    
    # 6. Partial obstruction (black bar)
    obstructed = img.copy()
    cv2.rectangle(obstructed, (0, h//3), (w, 2*h//3), (0, 0, 0), -1)
    variants.append(("obstructed", obstructed))
    
    # 7. Brightness (overexposed)
    bright = cv2.convertScaleAbs(img, alpha=1.5, beta=50)
    variants.append(("bright", bright))
    
    # 8. Dark (underexposed)
    dark = cv2.convertScaleAbs(img, alpha=0.4, beta=-30)
    variants.append(("dark", dark))
    
    # Save all variants
    for name, variant in variants:
        out_path = os.path.join(output_dir, f"{base_name}_{name}.jpg")
        cv2.imwrite(out_path, variant)
        print(f"Generated: {out_path}")
    
    # Also copy original
    orig_path = os.path.join(output_dir, f"{base_name}_original.jpg")
    cv2.imwrite(orig_path, img)
    print(f"Copied original: {orig_path}")
    
    print(f"\nGenerated {len(variants) + 1} variants in {output_dir}/")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        generate_distorted_variants(sys.argv[1])
    else:
        print("Usage: python generate_synthetic.py <image_file>")
        print("This will create distorted variants for testing.")
