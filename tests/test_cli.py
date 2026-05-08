"""run.py CLI testleri — argparse ve main() davranışı."""
import json
import sys
from pathlib import Path

import pytest

from run import _apply_overrides, _build_parser, _resolve_report_path, main


def test_parser_defaults():
    args = _build_parser().parse_args(["-i", "/tmp/x"])
    assert args.input == "/tmp/x"
    assert args.recursive is False
    assert args.invalid_action == "none"
    assert args.dry_run is False


def test_parser_full_flags():
    args = _build_parser().parse_args([
        "-i", "/tmp/x",
        "--recursive",
        "--invalid-action", "move",
        "--invalid-dir", "/tmp/rejected",
        "--min-short-edge", "256",
        "--max-aspect", "2.5",
        "--allowed-formats", "jpg,png",
        "--dry-run", "--yes",
    ])
    assert args.recursive is True
    assert args.invalid_action == "move"
    assert args.min_short_edge == 256
    assert args.max_aspect == 2.5
    assert args.allowed_formats == "jpg,png"
    assert args.yes is True


def test_apply_overrides_replaces_thresholds():
    cfg = {"file_validation": {}, "dimensions": {"aspect_ratio": {}}}
    args = _build_parser().parse_args([
        "-i", "/tmp/x",
        "--min-short-edge", "300",
        "--min-aspect", "0.4",
        "--allowed-formats", "jpg,webp",
        "--min-file-size-kb", "5",
    ])
    out = _apply_overrides(cfg, args)
    assert out["dimensions"]["min_short_edge"] == 300
    assert out["dimensions"]["aspect_ratio"]["min"] == 0.4
    assert out["file_validation"]["allowed_formats"] == ["jpg", "webp"]
    assert out["file_validation"]["min_file_size_kb"] == 5


def test_apply_overrides_keeps_existing_when_unset():
    cfg = {
        "file_validation": {"min_file_size_kb": 100},
        "dimensions": {"min_short_edge": 512, "aspect_ratio": {"min": 0.5, "max": 2.0}},
    }
    args = _build_parser().parse_args(["-i", "/tmp/x"])
    out = _apply_overrides(cfg, args)
    assert out["file_validation"]["min_file_size_kb"] == 100
    assert out["dimensions"]["min_short_edge"] == 512


def test_resolve_report_path_explicit():
    args = _build_parser().parse_args(["-i", "/tmp/x", "-o", "/tmp/r.json"])
    assert _resolve_report_path(args, Path("/tmp/x")) == Path("/tmp/r.json")


def test_resolve_report_path_move_uses_invalid_dir(tmp_path: Path):
    args = _build_parser().parse_args([
        "-i", str(tmp_path),
        "--invalid-action", "move",
        "--invalid-dir", str(tmp_path / "rej"),
    ])
    out = _resolve_report_path(args, tmp_path)
    assert out == tmp_path / "rej" / "validate_report.json"


def test_resolve_report_path_default_to_input(tmp_path: Path):
    args = _build_parser().parse_args(["-i", str(tmp_path)])
    out = _resolve_report_path(args, tmp_path)
    assert out == tmp_path / "validate_report.json"


def test_main_writes_report(monkeypatch, mixed_dataset: Path):
    """End-to-end CLI: rapor üretiliyor, action=none."""
    # Default config dosyasını yoluyla bypass etmek için --config gönderelim
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    monkeypatch.setattr(sys, "argv", [
        "run.py", "-i", str(mixed_dataset), "--recursive",
        "--config", str(cfg_path),
        "--min-file-size-kb", "0.5",  # broken.jpg gerçekten "corrupted" reason'a düşsün
    ])
    rc = main()
    assert rc == 0
    report = mixed_dataset / "validate_report.json"
    assert report.exists()
    data = json.loads(report.read_text())
    assert data["tool"] == "image-validator"
    assert data["recursive"] is True
    assert data["summary"]["total"] >= 7
    assert data["summary"]["invalid"] >= 4


def test_main_move_action_e2e(monkeypatch, mixed_dataset: Path, tmp_path: Path):
    rejected = tmp_path / "rejected"
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    monkeypatch.setattr(sys, "argv", [
        "run.py", "-i", str(mixed_dataset), "--recursive",
        "--config", str(cfg_path),
        "--min-file-size-kb", "0.5",
        "--invalid-action", "move",
        "--invalid-dir", str(rejected),
    ])
    rc = main()
    assert rc == 0
    # Invalid'ler taşındı
    assert not (mixed_dataset / "tiny.jpg").exists()
    assert (rejected / "tiny.jpg").exists()
    # Rapor invalid_dir'in içinde
    assert (rejected / "validate_report.json").exists()


def test_main_invalid_dir_required_for_move(monkeypatch, mixed_dataset: Path):
    monkeypatch.setattr(sys, "argv", [
        "run.py", "-i", str(mixed_dataset),
        "--invalid-action", "move",
    ])
    with pytest.raises(SystemExit):
        main()


def test_main_undo_cycle(monkeypatch, mixed_dataset: Path, tmp_path: Path):
    """Move → undo döngüsü: dosyalar son durumda yerinde."""
    rejected = tmp_path / "rejected"
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

    # 1) move
    monkeypatch.setattr(sys, "argv", [
        "run.py", "-i", str(mixed_dataset), "--recursive",
        "--config", str(cfg_path),
        "--min-file-size-kb", "0.5",
        "--invalid-action", "move",
        "--invalid-dir", str(rejected),
    ])
    assert main() == 0
    assert not (mixed_dataset / "tiny.jpg").exists()

    # 2) undo
    monkeypatch.setattr(sys, "argv", [
        "run.py", "--undo", str(rejected / "validate_report.json"),
    ])
    assert main() == 0
    assert (mixed_dataset / "tiny.jpg").exists()


def test_main_input_required_when_no_undo(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run.py"])
    with pytest.raises(SystemExit):
        main()
