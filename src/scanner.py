"""
Validator scanner + action layer.

Sorumluluklar:
- Klasör tarama (top-level veya recursive)
- Validation sonuçlarına göre aksiyon uygulama (move / delete)
- Aksiyon raporu yazma (sidecar JSON)
- Rapor üzerinden undo (move action için)
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPORT_VERSION = "1"
REPORT_TOOL = "media-validator"
# Back-compat: v0.2.x'te tool adı "image-validator" idi. Eski raporları da kabul et.
ACCEPTED_TOOL_NAMES = frozenset({"media-validator", "image-validator"})
DEFAULT_REPORT_NAME = "validate_report.json"

DEFAULT_IMAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"
})


@dataclass
class ActionEntry:
    """Tek bir validation-sonrası aksiyonun kaydı (sidecar JSON için)."""
    original: str
    reason: str
    moved_to: str | None = None
    deleted: bool = False

    def to_dict(self) -> dict:
        d = {"original": self.original, "reason": self.reason}
        if self.moved_to is not None:
            d["moved_to"] = self.moved_to
        if self.deleted:
            d["deleted"] = True
        return d


@dataclass
class ActionResult:
    """apply_action çıktısı."""
    action: str  # "none" | "move" | "delete"
    invalid_dir: str | None
    entries: list[ActionEntry] = field(default_factory=list)
    skipped: int = 0  # var olmayan / izin sorunu yaşanan dosyalar


def collect_images(
    directory: Path | str,
    *,
    recursive: bool = False,
    allowed_exts: Iterable[str] = DEFAULT_IMAGE_EXTS,
) -> list[Path]:
    """
    Bir dizindeki görsel dosyaları topla.

    Args:
        directory: Taranacak kök dizin
        recursive: True → alt klasörleri de tara
        allowed_exts: Hangi uzantılar dahil (lowercase, nokta dahil)

    Returns:
        Sıralı (deterministik) Path listesi
    """
    root = Path(directory)
    if not root.is_dir():
        return []

    exts = {e.lower() for e in allowed_exts}
    out: list[Path] = []

    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix.lower() in exts:
                    out.append(p)
    else:
        for entry in root.iterdir():
            if entry.is_file() and entry.suffix.lower() in exts:
                out.append(entry)

    out.sort()
    return out


def apply_action(
    results: list[dict],
    *,
    source_root: Path | str,
    action: str = "none",
    invalid_dir: Path | str | None = None,
    dry_run: bool = False,
) -> ActionResult:
    """
    Validation sonuçlarına göre invalid dosyaları taşı / sil.

    Args:
        results: FileValidationResult.to_dict() listesi (içinde 'filename' var)
        source_root: results'taki path'lerin köken dizini (relative path resolve için)
        action: "none" (sadece rapor), "move" (invalid_dir'e taşı), "delete" (sil)
        invalid_dir: action="move" için hedef dizin
        dry_run: True → fiziksel değişiklik yapma, sadece log üret

    Returns:
        ActionResult — log + sayaçlar
    """
    if action not in {"none", "move", "delete"}:
        raise ValueError(f"action must be 'none', 'move', or 'delete', got {action!r}")

    if action == "move" and invalid_dir is None:
        raise ValueError("action='move' requires invalid_dir")

    src_root = Path(source_root).resolve()
    dst_root = Path(invalid_dir).resolve() if invalid_dir else None

    result = ActionResult(
        action=action,
        invalid_dir=str(dst_root) if dst_root else None,
    )

    if action == "none":
        return result

    if action == "move" and dst_root and not dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)

    for r in results:
        if r.get("valid"):
            continue
        # Önce absolute path (FileValidationResult.path, v0.2.1+).
        # Yoksa eski rapor formatına fallback: filename ile rglob ara.
        # Path-based çözüm, recursive senaryoda aynı isimli dosyaların karışmasını
        # önler (örn. group_a/dup.jpg vs group_b/dup.jpg).
        original: Path | None = None
        path_str = r.get("path") or ""
        if path_str:
            candidate = Path(path_str)
            if candidate.is_file():
                original = candidate
        if original is None:
            original = _resolve_invalid_path(src_root, r.get("filename", ""))
        if original is None:
            result.skipped += 1
            continue

        reason = r.get("reason") or "unknown"

        if action == "delete":
            if not dry_run:
                try:
                    original.unlink()
                except OSError:
                    result.skipped += 1
                    continue
            result.entries.append(ActionEntry(
                original=str(original),
                reason=reason,
                deleted=True,
            ))
        elif action == "move" and dst_root:
            target = _unique_target(dst_root / original.name)
            if not dry_run:
                try:
                    shutil.move(str(original), str(target))
                except OSError:
                    result.skipped += 1
                    continue
            result.entries.append(ActionEntry(
                original=str(original),
                reason=reason,
                moved_to=str(target),
            ))

    return result


def _resolve_invalid_path(src_root: Path, filename: str) -> Path | None:
    """
    FileValidationResult sadece filename tutuyor. Recursive scan'de aynı isim birden çok
    alt klasörde olabilir; ilk eşleşeni dön. Top-level senaryoda direct join.
    """
    if not filename:
        return None
    direct = src_root / filename
    if direct.is_file():
        return direct
    # recursive arama
    for p in src_root.rglob(filename):
        if p.is_file():
            return p
    return None


def _unique_target(path: Path) -> Path:
    """İsim çakışırsa _1, _2 ekleyerek benzersiz hale getir."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def write_report(
    report_path: Path | str,
    *,
    source_root: Path | str,
    recursive: bool,
    allowed_exts: Iterable[str],
    summary: dict,
    results: list[dict],
    action_result: ActionResult,
    config_summary: dict,
) -> Path:
    """Sidecar JSON rapor yaz. organizer pattern'iyle simetrik."""
    payload = {
        "version": REPORT_VERSION,
        "tool": REPORT_TOOL,
        "source_root": str(Path(source_root).resolve()),
        "recursive": recursive,
        "allowed_exts": sorted(set(allowed_exts)),
        "config": config_summary,
        "summary": summary,
        "action": action_result.action,
        "invalid_dir": action_result.invalid_dir,
        "actions": [e.to_dict() for e in action_result.entries],
        "skipped": action_result.skipped,
        "results": results,
    }
    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out


def undo_from_report(
    report_path: Path | str,
    *,
    dry_run: bool = False,
) -> dict:
    """
    Rapor üzerinden geri alma:
    - moved_to: hedeften original'a taşı
    - deleted: ❌ undo edilemez, sayılır

    Returns:
        {"restored": N, "skipped": N, "irreversible_deletes": N}
    """
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    report_tool = report.get("tool")
    if report_tool not in ACCEPTED_TOOL_NAMES:
        raise ValueError(
            f"Report tool mismatch: expected one of {sorted(ACCEPTED_TOOL_NAMES)}, "
            f"got {report_tool!r}"
        )

    restored = 0
    skipped = 0
    irreversible = 0

    for entry in report.get("actions", []):
        if entry.get("deleted"):
            irreversible += 1
            continue
        moved_to = entry.get("moved_to")
        original = entry.get("original")
        if not moved_to or not original:
            skipped += 1
            continue
        src = Path(moved_to)
        dst = Path(original)
        if not src.exists():
            skipped += 1
            continue
        if dst.exists():
            # original konumunda yeni bir dosya var; üzerine yazmıyoruz
            skipped += 1
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                skipped += 1
                continue
        restored += 1

    return {
        "restored": restored,
        "skipped": skipped,
        "irreversible_deletes": irreversible,
    }
