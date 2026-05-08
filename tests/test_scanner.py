"""scanner.py: collect_images, apply_action, undo_from_report."""
from pathlib import Path

import pytest

from src.scanner import (
    DEFAULT_IMAGE_EXTS,
    apply_action,
    collect_images,
    undo_from_report,
    write_report,
)
from src.validators.file_validator import FileValidator


# ---------- collect_images ----------

def test_collect_top_level_only(mixed_dataset: Path):
    files = collect_images(mixed_dataset, recursive=False)
    names = [p.name for p in files]
    assert "ok1.jpg" in names
    assert "ok3.jpg" not in names  # alt klasörde
    assert "narrow.jpg" not in names


def test_collect_recursive(mixed_dataset: Path):
    files = collect_images(mixed_dataset, recursive=True)
    names = [p.name for p in files]
    assert "ok3.jpg" in names
    assert "narrow.jpg" in names
    assert "ok1.jpg" in names


def test_collect_filters_by_extension(tmp_path: Path):
    (tmp_path / "a.jpg").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"hello")
    (tmp_path / "c.png").write_bytes(b"")
    out = collect_images(tmp_path, allowed_exts={".jpg", ".png"})
    names = sorted(p.name for p in out)
    assert names == ["a.jpg", "c.png"]


def test_collect_invalid_dir_returns_empty(tmp_path: Path):
    assert collect_images(tmp_path / "nope") == []


def test_collect_is_sorted(mixed_dataset: Path):
    files = collect_images(mixed_dataset, recursive=False)
    paths = [str(p) for p in files]
    assert paths == sorted(paths)


# ---------- apply_action ----------

def _validate_all(dataset: Path, config: dict) -> list[dict]:
    v = FileValidator(config)
    return [v.validate(p).to_dict() for p in collect_images(dataset, recursive=True)]


def test_action_none_does_nothing(mixed_dataset: Path, validator_config):
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="none")
    assert res.action == "none"
    assert res.entries == []
    # dosyalar yerinde
    assert (mixed_dataset / "ok1.jpg").exists()
    assert (mixed_dataset / "tiny.jpg").exists()


def test_action_move_relocates_invalid(mixed_dataset: Path, tmp_path: Path, validator_config):
    rejected = tmp_path / "rejected"
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="move", invalid_dir=rejected)

    assert res.action == "move"
    assert len(res.entries) >= 4  # tiny, wide, broken, x.gif (+ narrow alt klasörden)
    # Invalid dosyalar artık kaynakta yok
    assert not (mixed_dataset / "tiny.jpg").exists()
    assert not (mixed_dataset / "wide.jpg").exists()
    # Rejected'a taşındılar
    moved_names = {Path(e.moved_to).name for e in res.entries}
    assert "tiny.jpg" in moved_names
    assert "wide.jpg" in moved_names
    # Valid'ler yerinde
    assert (mixed_dataset / "ok1.jpg").exists()


def test_action_move_dry_run_does_not_touch_files(mixed_dataset: Path, tmp_path: Path, validator_config):
    rejected = tmp_path / "rejected"
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="move",
                       invalid_dir=rejected, dry_run=True)

    # Log oluştu ama dosyalar yerinde
    assert len(res.entries) >= 4
    assert (mixed_dataset / "tiny.jpg").exists()
    assert not rejected.exists()  # mkdir bile yapılmadı


def test_action_delete_removes_files(mixed_dataset: Path, validator_config):
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="delete")

    assert res.action == "delete"
    assert all(e.deleted for e in res.entries)
    assert not (mixed_dataset / "tiny.jpg").exists()
    assert not (mixed_dataset / "broken.jpg").exists()
    # Valid'ler yerinde
    assert (mixed_dataset / "ok1.jpg").exists()


def test_action_delete_dry_run_keeps_files(mixed_dataset: Path, validator_config):
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="delete", dry_run=True)
    assert res.action == "delete"
    # Log var, dosyalar yerinde
    assert len(res.entries) >= 4
    assert (mixed_dataset / "tiny.jpg").exists()


def test_action_move_requires_invalid_dir(mixed_dataset: Path, validator_config):
    results = _validate_all(mixed_dataset, validator_config)
    with pytest.raises(ValueError, match="invalid_dir"):
        apply_action(results, source_root=mixed_dataset, action="move", invalid_dir=None)


def test_invalid_action_value_raises(validator_config):
    with pytest.raises(ValueError, match="action"):
        apply_action([], source_root=".", action="burn")


def test_action_skips_unknown_filename(tmp_path: Path):
    """Filename root'ta yoksa skipped sayılır (eski rapor formatı, path yok)."""
    res = apply_action(
        [{"valid": False, "filename": "ghost.jpg", "reason": "missing"}],
        source_root=tmp_path,
        action="delete",
    )
    assert res.entries == []
    assert res.skipped == 1


def test_action_uses_absolute_path_not_filename_lookup(tmp_path: Path, validator_config):
    """
    v0.2.1 regression: aynı isimli dosyalar farklı alt klasörlerde olduğunda,
    apply_action result.path'i kullanır (filename rglob fallback'i değil).
    Önceki davranış: rglob ilk eşleşeni dönüyordu → valid dosya silinebiliyordu.
    """
    from PIL import Image
    from src.validators.file_validator import FileValidator

    root = tmp_path / "ds"
    a = root / "group_a"; a.mkdir(parents=True)
    b = root / "group_b"; b.mkdir(parents=True)

    # group_a/dup.jpg = INVALID (çok küçük)
    Image.new("RGB", (200, 200), "white").save(a / "dup.jpg", quality=85)
    # group_b/dup.jpg = VALID (büyük)
    Image.new("RGB", (1024, 1024), "red").save(b / "dup.jpg", quality=85)

    v = FileValidator(validator_config)
    images = collect_images(root, recursive=True)
    results = [v.validate(p).to_dict() for p in images]

    # Sadece group_a/dup.jpg invalid olmalı
    invalid_results = [r for r in results if not r["valid"]]
    assert len(invalid_results) == 1
    assert "group_a" in invalid_results[0]["path"]

    # apply_action: sadece invalid'i sil, VALID dosyaya dokunma
    res = apply_action(results, source_root=root, action="delete")
    assert len(res.entries) == 1
    assert "group_a" in res.entries[0].original
    # group_a/dup.jpg silindi, group_b/dup.jpg duruyor
    assert not (a / "dup.jpg").exists()
    assert (b / "dup.jpg").exists()


def test_action_path_fallback_to_rglob_for_legacy_reports(tmp_path: Path):
    """Eski rapor formatlarında 'path' field'ı yok — rglob fallback çalışmalı."""
    (tmp_path / "lonely.jpg").write_bytes(b"")
    res = apply_action(
        [{"valid": False, "filename": "lonely.jpg", "reason": "test"}],  # path yok!
        source_root=tmp_path,
        action="delete",
    )
    assert len(res.entries) == 1
    assert not (tmp_path / "lonely.jpg").exists()


# ---------- undo_from_report ----------

def test_undo_restores_moved_files(mixed_dataset: Path, tmp_path: Path, validator_config):
    rejected = tmp_path / "rejected"
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="move", invalid_dir=rejected)

    report = rejected / "validate_report.json"
    write_report(
        report,
        source_root=mixed_dataset,
        recursive=True,
        allowed_exts=DEFAULT_IMAGE_EXTS,
        summary={"total": len(results), "valid": 0, "invalid": len(res.entries), "reasons": {}},
        results=results,
        action_result=res,
        config_summary={},
    )

    summary = undo_from_report(report)
    assert summary["restored"] == len(res.entries)
    assert summary["irreversible_deletes"] == 0
    # Dosyalar geri döndü
    assert (mixed_dataset / "tiny.jpg").exists()
    assert (mixed_dataset / "wide.jpg").exists()


def test_undo_dry_run_does_not_move(mixed_dataset: Path, tmp_path: Path, validator_config):
    rejected = tmp_path / "rejected"
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="move", invalid_dir=rejected)

    report = rejected / "validate_report.json"
    write_report(
        report, source_root=mixed_dataset, recursive=True,
        allowed_exts=DEFAULT_IMAGE_EXTS,
        summary={"total": len(results), "valid": 0, "invalid": len(res.entries), "reasons": {}},
        results=results, action_result=res, config_summary={},
    )

    summary = undo_from_report(report, dry_run=True)
    assert summary["restored"] == len(res.entries)
    # Dosyalar hala rejected'ta (taşınmadı)
    assert not (mixed_dataset / "tiny.jpg").exists()
    assert (rejected / "tiny.jpg").exists()


def test_undo_irreversible_for_delete(mixed_dataset: Path, validator_config, tmp_path: Path):
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="delete")

    report = tmp_path / "report.json"
    write_report(
        report, source_root=mixed_dataset, recursive=True,
        allowed_exts=DEFAULT_IMAGE_EXTS,
        summary={"total": len(results), "valid": 0, "invalid": len(res.entries), "reasons": {}},
        results=results, action_result=res, config_summary={},
    )

    summary = undo_from_report(report)
    assert summary["irreversible_deletes"] == len(res.entries)
    assert summary["restored"] == 0


def test_undo_skips_when_original_path_taken(mixed_dataset: Path, tmp_path: Path, validator_config):
    """Original konumda yeni dosya varsa üzerine yazma yok."""
    rejected = tmp_path / "rejected"
    results = _validate_all(mixed_dataset, validator_config)
    res = apply_action(results, source_root=mixed_dataset, action="move", invalid_dir=rejected)

    # Original konumda farklı dosya yarat
    (mixed_dataset / "tiny.jpg").write_bytes(b"yeni dosya")

    report = rejected / "validate_report.json"
    write_report(
        report, source_root=mixed_dataset, recursive=True,
        allowed_exts=DEFAULT_IMAGE_EXTS,
        summary={"total": len(results), "valid": 0, "invalid": len(res.entries), "reasons": {}},
        results=results, action_result=res, config_summary={},
    )

    summary = undo_from_report(report)
    # tiny.jpg skipped (üzerine yazmaz), diğerleri restored
    assert summary["skipped"] >= 1
    assert (mixed_dataset / "tiny.jpg").read_bytes() == b"yeni dosya"
