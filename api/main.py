"""
Image Validator API
Gradio UI ve diğer tüketiciler için FastAPI.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import tempfile
import shutil
import yaml
import os
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validators.file_validator import FileValidator, FileValidationResult

# Load config
CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


default_config = load_config()

# Default validator (settings.yaml ile)
default_validator = FileValidator(default_config)

# FastAPI app
app = FastAPI(
    title="Image Validator API",
    description="Dataset hazırlama için dosya/boyut doğrulama.",
    version="1.0.0"
)


# ============================================================
# Request/Response Models
# ============================================================

class ValidationConfig(BaseModel):
    """Override validation config - tüm alanlar opsiyonel."""
    # File validation
    allowed_formats: Optional[List[str]] = Field(None, description="İzin verilen formatlar: jpg, png, webp")
    min_file_size_kb: Optional[int] = Field(None, description="Min dosya boyutu KB")
    max_file_size_mb: Optional[int] = Field(None, description="Max dosya boyutu MB")

    # Dimensions
    min_short_edge: Optional[int] = Field(None, description="Min kısa kenar px")
    max_short_edge: Optional[int] = Field(None, description="Max kısa kenar px")
    min_aspect_ratio: Optional[float] = Field(None, description="Min aspect ratio (0.5 = 1:2)")
    max_aspect_ratio: Optional[float] = Field(None, description="Max aspect ratio (2.0 = 2:1)")


class DirectoryValidationRequest(BaseModel):
    """Directory validation için request body."""
    directory: str = Field(..., description="Klasör yolu")
    limit: int = Field(0, description="Max dosya sayısı (0=unlimited)")
    config: Optional[ValidationConfig] = Field(None, description="Override config (opsiyonel)")


class ValidationResponse(BaseModel):
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
    mode: str


class BatchValidationResponse(BaseModel):
    total: int
    valid_count: int
    invalid_count: int
    config_used: dict
    results: List[ValidationResponse]


class HealthResponse(BaseModel):
    status: str
    version: str
    default_config: dict


def build_config_from_override(override: Optional[ValidationConfig]) -> Dict[str, Any]:
    """Override config'i settings.yaml formatına çevir."""
    # Default config'den başla
    config = {
        'file_validation': {
            'allowed_formats': default_config.get('file_validation', {}).get('allowed_formats', ['jpg', 'jpeg', 'png', 'webp']),
            'min_file_size_kb': default_config.get('file_validation', {}).get('min_file_size_kb', 100),
            'max_file_size_mb': default_config.get('file_validation', {}).get('max_file_size_mb', 50),
        },
        'dimensions': {
            'min_short_edge': default_config.get('dimensions', {}).get('min_short_edge', 512),
            'max_short_edge': default_config.get('dimensions', {}).get('max_short_edge', 8192),
            'aspect_ratio': {
                'min': default_config.get('dimensions', {}).get('aspect_ratio', {}).get('min', 0.5),
                'max': default_config.get('dimensions', {}).get('aspect_ratio', {}).get('max', 2.0),
            }
        }
    }

    # Override varsa uygula
    if override:
        if override.allowed_formats is not None:
            config['file_validation']['allowed_formats'] = override.allowed_formats
        if override.min_file_size_kb is not None:
            config['file_validation']['min_file_size_kb'] = override.min_file_size_kb
        if override.max_file_size_mb is not None:
            config['file_validation']['max_file_size_mb'] = override.max_file_size_mb
        if override.min_short_edge is not None:
            config['dimensions']['min_short_edge'] = override.min_short_edge
        if override.max_short_edge is not None:
            config['dimensions']['max_short_edge'] = override.max_short_edge
        if override.min_aspect_ratio is not None:
            config['dimensions']['aspect_ratio']['min'] = override.min_aspect_ratio
        if override.max_aspect_ratio is not None:
            config['dimensions']['aspect_ratio']['max'] = override.max_aspect_ratio

    return config


# ============================================================
# Endpoints
# ============================================================

@app.get("/", response_model=HealthResponse)
async def root():
    """API durumu ve default config bilgisi."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "default_config": default_validator.get_config_summary()
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/validate/file", response_model=ValidationResponse)
async def validate_file(file: UploadFile = File(...)):
    """
    Tek dosya validasyonu (upload).

    HTTP Request ile kullanım:
    - Method: POST
    - URL: http://host:8100/validate/file
    - Body: form-data, key: file
    """
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = default_validator.validate(tmp_path)
        # Override filename with original
        result.filename = file.filename
        return result.to_dict()
    finally:
        os.unlink(tmp_path)


@app.post("/validate/path", response_model=ValidationResponse)
async def validate_path(path: str = Query(..., description="Sunucudaki dosya yolu")):
    """
    Sunucudaki dosyayı validate et (path ile).

    HTTP Request ile kullanım:
    - Method: POST
    - URL: http://host:8100/validate/path?path=/path/to/image.jpg
    """
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    result = default_validator.validate(path)
    return result.to_dict()


@app.post("/validate/directory", response_model=BatchValidationResponse)
async def validate_directory(request: DirectoryValidationRequest):
    """
    Klasördeki tüm görselleri validate et.

    HTTP Request ile kullanım:
    - Method: POST
    - URL: http://host:8100/validate/directory
    - Body (JSON):
    ```json
    {
      "directory": "/path/to/images",
      "limit": 0,
      "config": {
        "min_short_edge": 1024,
        "min_file_size_kb": 50
      }
    }
    ```

    Config opsiyonel - verilmezse default (settings.yaml) kullanılır.
    """
    dir_path = Path(request.directory)

    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.directory}")

    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.directory}")

    # Build config (default + override)
    merged_config = build_config_from_override(request.config)

    # Create validator with merged config
    validator = FileValidator(merged_config)

    # Find images
    extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
    images = [f for f in dir_path.iterdir() if f.is_file() and f.suffix.lower() in extensions]

    if request.limit > 0:
        images = images[:request.limit]

    # Validate all
    results = []
    valid_count = 0
    invalid_count = 0

    for img_path in images:
        result = validator.validate(img_path)
        results.append(result.to_dict())
        if result.valid:
            valid_count += 1
        else:
            invalid_count += 1

    return {
        "total": len(results),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "config_used": validator.get_config_summary(),
        "results": results
    }


@app.get("/config")
async def get_config():
    """Default konfigürasyonu döndür."""
    return {
        "file_validation": default_validator.get_config_summary(),
        "raw_config": default_config
    }


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    import uvicorn

    config = load_config()
    host = config.get('server', {}).get('host', '0.0.0.0')
    port = config.get('server', {}).get('port', 8100)

    print(f"Starting Image Validator API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
