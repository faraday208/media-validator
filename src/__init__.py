"""image-validator — public API.

In-process kullanım için:
    from src import FileValidator, collect_images, apply_action, undo_from_report
"""
from .scanner import (
    DEFAULT_IMAGE_EXTS,
    DEFAULT_REPORT_NAME,
    REPORT_VERSION,
    ActionEntry,
    ActionResult,
    apply_action,
    collect_images,
    undo_from_report,
    write_report,
)
from .validators.file_validator import FileValidationResult, FileValidator

__all__ = [
    "FileValidator",
    "FileValidationResult",
    "collect_images",
    "apply_action",
    "undo_from_report",
    "write_report",
    "ActionEntry",
    "ActionResult",
    "DEFAULT_IMAGE_EXTS",
    "DEFAULT_REPORT_NAME",
    "REPORT_VERSION",
]
