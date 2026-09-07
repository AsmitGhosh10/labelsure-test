import glob
import json
import os
import sys

from backend.app.services.pipeline import InspectionPipeline, MAX_SURFACES

IMAGE_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.bmp")


def find_images(directory: str):
    files = []
    for ext in IMAGE_EXTS:
        files.extend(glob.glob(os.path.join(directory, ext)))
        files.extend(glob.glob(os.path.join(directory, ext.upper())))
    return sorted(files)


def run_batch(base_dir: str = "test_images", output_dir: str = "ocr_test_results"):
    os.makedirs(output_dir, exist_ok=True)

    inspections = []

    # Subfolders = one package each (multi-surface inspection)
    subdirs = sorted(
        d
        for d in glob.glob(os.path.join(base_dir, "*/"))
        if os.path.isdir(d)
    )
    for subdir in subdirs:
        images = find_images(subdir)
        if not images:
            continue
        images = images[:MAX_SURFACES]
        name = os.path.basename(os.path.normpath(subdir))
        print(f"{'=' * 70}\nPACKAGE (multi-surface): {name} — {len(images)} surfaces\n{'=' * 70}")
        inspections.append(("package:" + name, images))

    # Top-level loose images = single-surface inspections
    for img in find_images(base_dir):
        inspections.append((os.path.basename(img), [img]))

    if not inspections:
        print(f"No images found in {base_dir}")
        return

    pipeline = InspectionPipeline()
    all_results = []
    for label, images in inspections:
        print(f"\nInspecting: {label}")
        result = pipeline.run_multi(
            images, image_names=[os.path.basename(p) for p in images], product_name=None
        )
        all_results.append(result)

        conf = result.get("confidence")
        cov = result.get("coverage", {})
        print(f"  Coverage : {cov.get('surfaces_usable')}/{cov.get('surfaces_total')} surfaces usable")
        if conf:
            print(f"  Confidence: {conf['overall']:.0%}")
        print(f"  DECISION : {result.get('decision_emoji', '')} {result.get('decision')}")
        for reason in (result.get("decision_reasons") or [])[:5]:
            print(f"    - {reason}")
        for r in result.get("rule_results", []):
            print(f"    [{r['status']:<14}] {r['rule_id']}: {r['reason'][:90]}")
        print(f"  Time: {result.get('processing_time_sec')}s")

    output_file = os.path.join(
        output_dir, f"pipeline_results_{os.path.basename(os.path.normpath(base_dir))}.json"
    )
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {output_file}")

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    counts = {}
    for r in all_results:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    for decision, count in sorted(counts.items()):
        print(f"  {decision}: {count}")
    for r in all_results:
        surfaces = ", ".join(
            img["name"] for img in r.get("images", [])
        )
        conf_str = f"{r['confidence']['overall']:.0%}" if r.get("confidence") else "n/a"
        print(
            f"  {surfaces or r.get('inspection_id', '')[:8]:<30} "
            f"{r.get('decision_emoji', '')} {r['decision']:<15} conf={conf_str}"
        )


if __name__ == "__main__":
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "test_images"
    run_batch(base_dir)
