#!/usr/bin/env python3
"""
Image Validator — CLI

Kullanım örnekleri:
  # Sadece raporla (default), top-level scan
  python run.py -i ./dataset

  # Recursive + raporu özel yere yaz
  python run.py -i ./dataset --recursive -o ./reports/validate.json

  # Hatalıları /rejected'a taşı (undoable)
  python run.py -i ./dataset --recursive --invalid-action move --invalid-dir ./rejected

  # Hatalıları sil (irreversible — uyarı verir)
  python run.py -i ./dataset --invalid-action delete

  # Threshold override (config'i ezer)
  python run.py -i ./dataset --min-short-edge 256 --min-aspect 0.4 --max-aspect 2.5

  # Geri al (move-action raporundan)
  python run.py --undo ./rejected/validate_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from tqdm import tqdm

from src.scanner import (
    DEFAULT_IMAGE_EXTS,
    DEFAULT_REPORT_NAME,
    apply_action,
    collect_images,
    undo_from_report,
    write_report,
)
from src.validators.file_validator import FileValidator


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Image Validator (CLI) — format/boyut/aspect/bütünlük doğrulama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-i", "--input", help="Input klasörü (validation modu için zorunlu)")
    p.add_argument("-o", "--output", help=f"JSON rapor çıktısı (default: <input>/{DEFAULT_REPORT_NAME})")
    p.add_argument("--recursive", action="store_true", help="Alt klasörleri de tara")
    p.add_argument("--limit", type=int, default=0, help="Max dosya sayısı (0 = limitsiz)")

    # Aksiyon
    p.add_argument(
        "--invalid-action",
        choices=["none", "move", "delete"],
        default="none",
        help="Hatalı dosyalar için aksiyon (default: none = sadece rapor)",
    )
    p.add_argument("--invalid-dir", help="--invalid-action move için hedef klasör")
    p.add_argument("--dry-run", action="store_true", help="Aksiyonu simüle et, dosyalara dokunma (rapor yine yazılır)")
    p.add_argument("--yes", action="store_true", help="Onay sorma (özellikle --invalid-action delete için)")

    # Threshold override (config'i ezer)
    p.add_argument("--min-short-edge", type=int, help="Min kısa kenar (px) — config'i ezer")
    p.add_argument("--max-short-edge", type=int, help="Max kısa kenar (px)")
    p.add_argument("--min-aspect", type=float, help="Min aspect ratio (w/h)")
    p.add_argument("--max-aspect", type=float, help="Max aspect ratio (w/h)")
    p.add_argument("--min-file-size-kb", type=float, help="Min dosya boyutu (KB)")
    p.add_argument("--max-file-size-mb", type=float, help="Max dosya boyutu (MB)")
    p.add_argument(
        "--allowed-formats",
        help="Geçerli format listesi virgülle (örn: jpg,jpeg,png,webp). Config'i ezer.",
    )

    # Undo
    p.add_argument("--undo", help="Validate raporundan aksiyonu geri al (sadece move-action)")

    p.add_argument("--config", help="settings.yaml yolu (default: ./config/settings.yaml)")
    return p


def _load_config(path: Path | None) -> dict:
    cfg_path = path or (Path(__file__).parent / "config" / "settings.yaml")
    if not cfg_path.exists():
        return {}
    with open(cfg_path) as f:
        return yaml.safe_load(f) or {}


def _apply_overrides(config: dict, args: argparse.Namespace) -> dict:
    """CLI threshold flag'leri config dict'ine yedirir."""
    cfg = json.loads(json.dumps(config))  # deep copy via json
    file_v = cfg.setdefault("file_validation", {})
    dims = cfg.setdefault("dimensions", {})
    aspect = dims.setdefault("aspect_ratio", {})

    if args.allowed_formats:
        file_v["allowed_formats"] = [f.strip().lower() for f in args.allowed_formats.split(",") if f.strip()]
    if args.min_file_size_kb is not None:
        file_v["min_file_size_kb"] = args.min_file_size_kb
    if args.max_file_size_mb is not None:
        file_v["max_file_size_mb"] = args.max_file_size_mb
    if args.min_short_edge is not None:
        dims["min_short_edge"] = args.min_short_edge
    if args.max_short_edge is not None:
        dims["max_short_edge"] = args.max_short_edge
    if args.min_aspect is not None:
        aspect["min"] = args.min_aspect
    if args.max_aspect is not None:
        aspect["max"] = args.max_aspect
    return cfg


def _confirm_delete(invalid_count: int, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    print(f"\n⚠  {invalid_count} hatalı dosya KALICI olarak silinecek. Bu işlem GERİ ALINAMAZ.")
    answer = input("Devam? [y/N]: ").strip().lower()
    return answer in {"y", "yes", "evet"}


def _run_undo(args: argparse.Namespace) -> int:
    report_path = Path(args.undo)
    if not report_path.exists():
        print(f"Rapor bulunamadı: {report_path}", file=sys.stderr)
        return 1
    print(f"Undo başlıyor (dry-run={args.dry_run}): {report_path}")
    summary = undo_from_report(report_path, dry_run=args.dry_run)
    print(f"  Restored:               {summary['restored']}")
    print(f"  Skipped:                {summary['skipped']}")
    print(f"  Irreversible (deleted): {summary['irreversible_deletes']}")
    if summary["irreversible_deletes"]:
        print("  → Silinmiş dosyalar geri getirilemez. (--invalid-action delete kullanılmıştı)")
    return 0


def _resolve_report_path(args: argparse.Namespace, input_dir: Path) -> Path:
    if args.output:
        return Path(args.output)
    if args.invalid_action == "move" and args.invalid_dir:
        # move modunda raporu hedef dizine koymak undo'yu kolaylaştırır
        return Path(args.invalid_dir) / DEFAULT_REPORT_NAME
    return input_dir / DEFAULT_REPORT_NAME


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Undo modu — diğer her şeyi atla
    if args.undo:
        return _run_undo(args)

    if not args.input:
        parser.error("--input gerekli (veya --undo kullan)")

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"Geçerli bir dizin değil: {input_dir}", file=sys.stderr)
        return 1

    if args.invalid_action == "move" and not args.invalid_dir:
        parser.error("--invalid-action move için --invalid-dir gerekli")

    # Config + override'lar
    config = _load_config(Path(args.config) if args.config else None)
    config = _apply_overrides(config, args)
    validator = FileValidator(config)

    # Tarama uzantıları: config'in allowed_formats'ı + default genel set BİRLEŞİMİ.
    # Birleşim sayesinde config dışı bir uzantı (örn. bmp/gif) da taranır ve
    # validator tarafından "invalid_format" diye redde uğrar (rapora çıkar).
    file_v = config.get("file_validation", {})
    allowed = {f.lower().lstrip(".") for f in file_v.get("allowed_formats", [])}
    scan_exts: set[str] = {f".{f}" for f in allowed} | set(DEFAULT_IMAGE_EXTS)

    images = collect_images(input_dir, recursive=args.recursive, allowed_exts=scan_exts)
    if args.limit > 0:
        images = images[: args.limit]

    print(f"\n{'='*60}")
    print(f"Image Validator")
    print(f"{'='*60}")
    print(f"Input:     {input_dir}")
    print(f"Recursive: {args.recursive}")
    print(f"Files:     {len(images)}")
    print(f"Action:    {args.invalid_action}{' (DRY-RUN)' if args.dry_run else ''}")
    print(f"Config:    {validator.get_config_summary()}")
    print(f"{'='*60}\n")

    if not images:
        print("Hiç dosya bulunamadı.")
        return 0

    results: list[dict] = []
    valid = invalid = 0
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
    total = len(results)
    print(f"Total:   {total}")
    print(f"Valid:   {valid} ({valid/total*100:.1f}%)")
    print(f"Invalid: {invalid} ({invalid/total*100:.1f}%)")
    if reasons:
        print(f"\nRed Sebepleri:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")

    # Aksiyon
    if args.invalid_action == "delete" and invalid > 0 and not args.dry_run:
        if not _confirm_delete(invalid, assume_yes=args.yes):
            print("İptal edildi.")
            return 2

    action_res = apply_action(
        results,
        source_root=input_dir,
        action=args.invalid_action,
        invalid_dir=args.invalid_dir,
        dry_run=args.dry_run,
    )

    if args.invalid_action != "none":
        print(f"\nAksiyon: {args.invalid_action}{' (DRY-RUN)' if args.dry_run else ''}")
        if action_res.action == "move":
            print(f"  Taşınan:  {len(action_res.entries)}")
            print(f"  Hedef:    {action_res.invalid_dir}")
        elif action_res.action == "delete":
            print(f"  Silinen:  {len(action_res.entries)}")
        if action_res.skipped:
            print(f"  Atlanan:  {action_res.skipped} (dosya bulunamadı / izin)")

    # Rapor
    report_path = _resolve_report_path(args, input_dir)
    summary = {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "reasons": reasons,
    }
    write_report(
        report_path,
        source_root=input_dir,
        recursive=args.recursive,
        allowed_exts=scan_exts,
        summary=summary,
        results=results,
        action_result=action_res,
        config_summary=validator.get_config_summary(),
    )
    print(f"\nRapor: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
