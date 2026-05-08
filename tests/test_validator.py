"""FileValidator unit testleri — tek dosya validation senaryoları."""
from pathlib import Path

from PIL import Image

from src.validators.file_validator import FileValidator


def _save_jpg(path: Path, size: tuple[int, int], color="red") -> None:
    Image.new("RGB", size, color).save(path, "JPEG", quality=85)


def test_valid_image_passes(tmp_path: Path, validator_config):
    p = tmp_path / "ok.jpg"
    _save_jpg(p, (1024, 1024))
    r = FileValidator(validator_config).validate(p)
    assert r.valid
    assert r.reason is None
    assert r.width == 1024 and r.height == 1024
    assert r.short_edge == 1024
    assert r.format == "jpg"


def test_too_small_short_edge(tmp_path: Path, validator_config):
    p = tmp_path / "small.jpg"
    _save_jpg(p, (400, 400))
    r = FileValidator(validator_config).validate(p)
    assert not r.valid
    assert r.reason == "too_small"


def test_aspect_too_wide(tmp_path: Path, validator_config):
    p = tmp_path / "wide.jpg"
    _save_jpg(p, (4096, 600))
    r = FileValidator(validator_config).validate(p)
    assert not r.valid
    assert r.reason == "aspect_too_wide"


def test_aspect_too_narrow(tmp_path: Path, validator_config):
    p = tmp_path / "narrow.jpg"
    _save_jpg(p, (600, 4096))
    r = FileValidator(validator_config).validate(p)
    assert not r.valid
    assert r.reason == "aspect_too_narrow"


def test_corrupted_file(tmp_path: Path, validator_config):
    p = tmp_path / "broken.jpg"
    p.write_bytes(b"absolutely not a jpeg")
    r = FileValidator(validator_config).validate(p)
    assert not r.valid
    # PIL bozuk dosyada genelde "file_too_small" veya "corrupted: ..." döner
    assert r.reason.startswith("corrupted") or r.reason == "file_too_small"


def test_invalid_format(tmp_path: Path, validator_config):
    p = tmp_path / "x.gif"
    p.write_bytes(b"GIF89a" + b"\x00" * 1000)
    r = FileValidator(validator_config).validate(p)
    assert not r.valid
    assert r.reason == "invalid_format"


def test_file_not_found(tmp_path: Path, validator_config):
    r = FileValidator(validator_config).validate(tmp_path / "yok.jpg")
    assert not r.valid
    assert r.reason == "file_not_found"


def test_threshold_override_via_config(tmp_path: Path, validator_config):
    """Config değiştirildiğinde validator buna göre davranır."""
    p = tmp_path / "small.jpg"
    _save_jpg(p, (300, 300))
    # Default config'te 512 px reddeder, ezelim
    validator_config["dimensions"]["min_short_edge"] = 256
    r = FileValidator(validator_config).validate(p)
    assert r.valid


def test_aspect_override(tmp_path: Path, validator_config):
    """Aspect override ile dar görsel kabul edilir."""
    p = tmp_path / "narrow.jpg"
    _save_jpg(p, (600, 1500))  # aspect 0.4
    validator_config["dimensions"]["aspect_ratio"]["min"] = 0.3
    r = FileValidator(validator_config).validate(p)
    assert r.valid


def test_get_config_summary_returns_keys(validator_config):
    s = FileValidator(validator_config).get_config_summary()
    assert "allowed_formats" in s
    assert "min_short_edge" in s
    assert "aspect_ratio_range" in s
