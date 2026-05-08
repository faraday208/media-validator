#!/usr/bin/env python3
"""
Image Validator - CLI

Kullanım:
    python run.py -i /path/to/images [-o report.json] [--limit 100]
"""

import argparse
import json
from pathlib import Path

import yaml
from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser(description="Image Validator (CLI)")
    parser.add_argument('-i', '--input', required=True, help='Input klasörü')
    parser.add_argument('-o', '--output', help='JSON rapor çıktısı')
    parser.add_argument('--limit', type=int, default=0, help='Max dosya sayısı (0 = limitsiz)')
    args = parser.parse_args()

    from src.validators.file_validator import FileValidator

    config_path = Path(__file__).parent / "config" / "settings.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    validator = FileValidator(config)

    input_dir = Path(args.input)
    extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    images = [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in extensions]

    if args.limit > 0:
        images = images[:args.limit]

    print(f"\n{'='*60}")
    print(f"Image Validator - File Validation")
    print(f"{'='*60}")
    print(f"Input: {input_dir}")
    print(f"Files: {len(images)}")
    print(f"Config: {validator.get_config_summary()}")
    print(f"{'='*60}\n")

    results = []
    valid = 0
    invalid = 0
    reasons: dict[str, int] = {}

    for img in tqdm(images, desc="Validating"):
        r = validator.validate(img)
        results.append(r.to_dict())
        if r.valid:
            valid += 1
        else:
            invalid += 1
            reasons[r.reason] = reasons.get(r.reason, 0) + 1

    print(f"\n{'='*60}")
    print(f"SONUÇLAR")
    print(f"{'='*60}")
    if images:
        print(f"Valid:   {valid} ({valid/len(images)*100:.1f}%)")
        print(f"Invalid: {invalid} ({invalid/len(images)*100:.1f}%)")

    if reasons:
        print(f"\nRed Sebepleri:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")

    if args.output:
        report = {
            "input": str(input_dir),
            "total": len(results),
            "valid": valid,
            "invalid": invalid,
            "reasons": reasons,
            "results": results,
        }
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nRapor: {args.output}")


if __name__ == '__main__':
    main()
