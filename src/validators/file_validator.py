"""
Adım 1: Dosya Validasyonu

Kontroller:
- Format (jpg, png, webp, etc.)
- Dosya boyutu (min/max)
- Görüntü boyutları (width, height, short edge)
- Aspect ratio
- Dosya bütünlüğü (corruption check)
"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict
from PIL import Image
import os


@dataclass
class FileValidationResult:
    """Validation sonucu."""
    valid: bool
    reason: Optional[str]
    filename: str
    file_size_kb: float
    width: int
    height: int
    short_edge: int
    long_edge: int
    aspect_ratio: float
    format: str
    mode: str  # RGB, RGBA, L, etc.

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FileValidator:
    """Dosya validasyonu - Adım 1."""

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: settings.yaml'dan gelen config
        """
        file_config = config.get('file_validation', {})
        dim_config = config.get('dimensions', {})

        # File validation settings
        self.allowed_formats = set(file_config.get('allowed_formats', ['jpg', 'jpeg', 'png', 'webp']))
        self.min_file_size = file_config.get('min_file_size_kb', 20) * 1024  # KB -> bytes
        self.max_file_size = file_config.get('max_file_size_mb', 50) * 1024 * 1024  # MB -> bytes

        # Dimension settings
        self.min_short_edge = dim_config.get('min_short_edge', 512)
        self.max_short_edge = dim_config.get('max_short_edge', 8192)

        aspect_config = dim_config.get('aspect_ratio', {})
        self.min_aspect = aspect_config.get('min', 0.5)
        self.max_aspect = aspect_config.get('max', 2.0)

    def validate(self, image_path: str | Path) -> FileValidationResult:
        """
        Tek bir görüntüyü validate et.

        Args:
            image_path: Görüntü dosyası yolu

        Returns:
            FileValidationResult
        """
        path = Path(image_path)

        # Default result for errors
        def error_result(reason: str) -> FileValidationResult:
            return FileValidationResult(
                valid=False,
                reason=reason,
                filename=path.name,
                file_size_kb=0,
                width=0,
                height=0,
                short_edge=0,
                long_edge=0,
                aspect_ratio=0,
                format="",
                mode=""
            )

        # 1. Dosya var mı?
        if not path.exists():
            return error_result("file_not_found")

        if not path.is_file():
            return error_result("not_a_file")

        # 2. Dosya boyutu
        file_size = path.stat().st_size
        file_size_kb = file_size / 1024

        if file_size < self.min_file_size:
            return FileValidationResult(
                valid=False,
                reason="file_too_small",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=0, height=0, short_edge=0, long_edge=0,
                aspect_ratio=0, format=path.suffix.lower().lstrip('.'), mode=""
            )

        if file_size > self.max_file_size:
            return FileValidationResult(
                valid=False,
                reason="file_too_large",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=0, height=0, short_edge=0, long_edge=0,
                aspect_ratio=0, format=path.suffix.lower().lstrip('.'), mode=""
            )

        # 3. Format kontrolü
        ext = path.suffix.lower().lstrip('.')
        if ext not in self.allowed_formats:
            return FileValidationResult(
                valid=False,
                reason="invalid_format",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=0, height=0, short_edge=0, long_edge=0,
                aspect_ratio=0, format=ext, mode=""
            )

        # 4. Görüntü açma ve boyut kontrolü
        try:
            with Image.open(path) as img:
                width, height = img.size
                mode = img.mode
                img_format = img.format or ext.upper()

                # Verify (header check)
                img.verify()

            # 5. Full decode check (corruption için)
            with Image.open(path) as img:
                img.load()  # Force decode

        except Exception as e:
            return FileValidationResult(
                valid=False,
                reason=f"corrupted: {str(e)[:50]}",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=0, height=0, short_edge=0, long_edge=0,
                aspect_ratio=0, format=ext, mode=""
            )

        # 6. Boyut hesaplamaları
        short_edge = min(width, height)
        long_edge = max(width, height)
        aspect_ratio = round(width / height, 3) if height > 0 else 0

        # 7. Short edge kontrolü
        if short_edge < self.min_short_edge:
            return FileValidationResult(
                valid=False,
                reason="too_small",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=width, height=height,
                short_edge=short_edge, long_edge=long_edge,
                aspect_ratio=aspect_ratio, format=ext, mode=mode
            )

        if short_edge > self.max_short_edge:
            return FileValidationResult(
                valid=False,
                reason="too_large",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=width, height=height,
                short_edge=short_edge, long_edge=long_edge,
                aspect_ratio=aspect_ratio, format=ext, mode=mode
            )

        # 8. Aspect ratio kontrolü
        if aspect_ratio < self.min_aspect:
            return FileValidationResult(
                valid=False,
                reason="aspect_too_narrow",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=width, height=height,
                short_edge=short_edge, long_edge=long_edge,
                aspect_ratio=aspect_ratio, format=ext, mode=mode
            )

        if aspect_ratio > self.max_aspect:
            return FileValidationResult(
                valid=False,
                reason="aspect_too_wide",
                filename=path.name,
                file_size_kb=round(file_size_kb, 1),
                width=width, height=height,
                short_edge=short_edge, long_edge=long_edge,
                aspect_ratio=aspect_ratio, format=ext, mode=mode
            )

        # Tüm kontroller geçti
        return FileValidationResult(
            valid=True,
            reason=None,
            filename=path.name,
            file_size_kb=round(file_size_kb, 1),
            width=width,
            height=height,
            short_edge=short_edge,
            long_edge=long_edge,
            aspect_ratio=aspect_ratio,
            format=ext,
            mode=mode
        )

    def validate_batch(self, image_paths: list) -> list[FileValidationResult]:
        """Birden fazla görüntüyü validate et."""
        return [self.validate(p) for p in image_paths]

    def get_config_summary(self) -> Dict[str, Any]:
        """Mevcut config özetini döndür."""
        return {
            "allowed_formats": list(self.allowed_formats),
            "min_file_size_kb": self.min_file_size / 1024,
            "max_file_size_mb": self.max_file_size / (1024 * 1024),
            "min_short_edge": self.min_short_edge,
            "max_short_edge": self.max_short_edge,
            "aspect_ratio_range": f"{self.min_aspect} - {self.max_aspect}"
        }
