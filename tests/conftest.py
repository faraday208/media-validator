"""Test fixture'ları — image-validator için."""
import sys
from pathlib import Path

import pytest
from PIL import Image

# Repo kökünü path'e ekle ki `from src import ...` çalışsın
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


DEFAULT_CONFIG = {
    "file_validation": {
        "allowed_formats": ["jpg", "jpeg", "png", "webp"],
        "min_file_size_kb": 0.5,  # test için düşük
        "max_file_size_mb": 50,
    },
    "dimensions": {
        "min_short_edge": 512,
        "max_short_edge": 8192,
        "aspect_ratio": {"min": 0.5, "max": 2.0},
    },
}


def _save_jpg(path: Path, size: tuple[int, int], color: str = "red") -> None:
    Image.new("RGB", size, color).save(path, "JPEG", quality=85)


@pytest.fixture
def validator_config() -> dict:
    """Standart test config'i (her test bunu kopyalayıp ezleyebilir)."""
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


@pytest.fixture
def mixed_dataset(tmp_path: Path) -> Path:
    """
    Geçerli + geçersiz görsellerin karışımı.

    Yapı:
        tmp_path/
            ok1.jpg              (1024x1024 — valid)
            ok2.jpg              (1024x768  — valid)
            tiny.jpg             (200x200   — too_small)
            wide.jpg             (4096x600  — aspect_too_wide)
            broken.jpg           (rastgele bytes — corrupted)
            x.gif                (gif sayılmıyor — invalid_format)
            sub/
                ok3.jpg          (1024x1024 — valid)
                narrow.jpg       (600x4096  — aspect_too_narrow)
    """
    _save_jpg(tmp_path / "ok1.jpg", (1024, 1024), "red")
    _save_jpg(tmp_path / "ok2.jpg", (1024, 768), "green")
    _save_jpg(tmp_path / "tiny.jpg", (200, 200), "white")
    _save_jpg(tmp_path / "wide.jpg", (4096, 600), "yellow")
    (tmp_path / "broken.jpg").write_bytes(b"not a real jpeg")
    (tmp_path / "x.gif").write_bytes(b"GIF89a" + b"\x00" * 1000)

    sub = tmp_path / "sub"
    sub.mkdir()
    _save_jpg(sub / "ok3.jpg", (1024, 1024), "blue")
    _save_jpg(sub / "narrow.jpg", (600, 4096), "magenta")

    return tmp_path


@pytest.fixture
def all_valid_dataset(tmp_path: Path) -> Path:
    """Tamamen geçerli 3 görsel (top-level)."""
    _save_jpg(tmp_path / "a.jpg", (1024, 1024))
    _save_jpg(tmp_path / "b.jpg", (1024, 768))
    _save_jpg(tmp_path / "c.png", (800, 1200), "blue")
    return tmp_path
