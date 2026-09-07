"""Create a synthetic 2-surface demo package (front + back) for multi-image
inspection testing, in the same style as create_test_image.py."""

import cv2
import numpy as np
import os


def make_surface(lines, output_path, size=(800, 600)):
    img = np.ones((size[1], size[0], 3), dtype=np.uint8) * 240
    cv2.rectangle(img, (30, 30), (size[0] - 30, size[1] - 30), (0, 0, 0), 2)
    y = 100
    for text, scale, color, thickness in lines:
        cv2.putText(img, text, (70, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)
        y += int(55 + scale * 20)
    cv2.imwrite(output_path, img)
    print(f"Created: {output_path}")
    return output_path


def create_demo_package(output_dir="test_packages/demo_snack"):
    os.makedirs(output_dir, exist_ok=True)

    front = [
        ("DEMO SNACK", 1.4, (0, 0, 0), 3),
        ("Net Qty: 100 g", 0.9, (0, 0, 0), 2),
        ("MRP: Rs. 20.00", 1.1, (0, 0, 139), 3),
        ("(Inclusive of all taxes)", 0.6, (80, 80, 80), 2),
    ]
    back = [
        ("Manufactured By:", 0.8, (0, 0, 0), 2),
        ("ABC Foods Pvt. Ltd.", 0.8, (0, 0, 0), 2),
        ("Mumbai, Maharashtra, India", 0.6, (80, 80, 80), 2),
        ("Mfg. Date: 15/01/2026", 0.8, (0, 0, 0), 2),
        ("Batch No.: A25X77", 0.8, (0, 0, 0), 2),
        ("Customer Care: 1800-123-4567", 0.7, (0, 100, 0), 2),
        ("Email: care@abcfoods.com", 0.7, (0, 100, 0), 2),
        ("Product of India", 0.8, (0, 0, 0), 2),
    ]

    make_surface(front, os.path.join(output_dir, "front.jpg"), size=(800, 600))
    make_surface(back, os.path.join(output_dir, "back.jpg"), size=(800, 850))
    print(f"\nDemo package ready in {output_dir}/")
    print("Run: python run_pipeline.py test_packages")


if __name__ == "__main__":
    create_demo_package()
