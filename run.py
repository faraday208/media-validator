#!/usr/bin/env python3
"""
Image Quality Checker - Başlatıcı

Kullanım:
    python run.py api          # API sunucusu başlat
    python run.py validate     # CLI ile klasör validate et
"""

import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Image Quality Checker")
    subparsers = parser.add_subparsers(dest='command', help='Komutlar')

    # API command
    api_parser = subparsers.add_parser('api', help='API sunucusunu başlat')
    api_parser.add_argument('--host', default='0.0.0.0', help='Host (default: 0.0.0.0)')
    api_parser.add_argument('--port', type=int, default=8100, help='Port (default: 8100)')

    # Validate command
    val_parser = subparsers.add_parser('validate', help='Klasör validate et')
    val_parser.add_argument('-i', '--input', required=True, help='Input klasörü')
    val_parser.add_argument('-o', '--output', help='JSON rapor çıktısı')
    val_parser.add_argument('--limit', type=int, default=0, help='Max dosya sayısı')

    args = parser.parse_args()

    if args.command == 'api':
        import uvicorn
        from api.main import app

        print(f"Starting API on {args.host}:{args.port}")
        print(f"Docs: http://{args.host}:{args.port}/docs")
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == 'validate':
        from src.validators.file_validator import FileValidator
        import yaml
        import json
        from tqdm import tqdm

        # Load config
        config_path = Path(__file__).parent / "config" / "settings.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        validator = FileValidator(config)

        # Find images
        input_dir = Path(args.input)
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        images = [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in extensions]

        if args.limit > 0:
            images = images[:args.limit]

        print(f"\n{'='*60}")
        print(f"Image Quality Checker - File Validation")
        print(f"{'='*60}")
        print(f"Input: {input_dir}")
        print(f"Files: {len(images)}")
        print(f"Config: {validator.get_config_summary()}")
        print(f"{'='*60}\n")

        results = []
        valid = 0
        invalid = 0
        reasons = {}

        for img in tqdm(images, desc="Validating"):
            r = validator.validate(img)
            results.append(r.to_dict())
            if r.valid:
                valid += 1
            else:
                invalid += 1
                reasons[r.reason] = reasons.get(r.reason, 0) + 1

        # Summary
        print(f"\n{'='*60}")
        print(f"SONUÇLAR")
        print(f"{'='*60}")
        print(f"Valid:   {valid} ({valid/len(images)*100:.1f}%)")
        print(f"Invalid: {invalid} ({invalid/len(images)*100:.1f}%)")

        if reasons:
            print(f"\nRed Sebepleri:")
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                print(f"  - {reason}: {count}")

        # Save report
        if args.output:
            report = {
                "input": str(input_dir),
                "total": len(results),
                "valid": valid,
                "invalid": invalid,
                "reasons": reasons,
                "results": results
            }
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\nRapor: {args.output}")

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
