# media-validator

> Medya dataset'leri için format / boyut / aspect / bütünlük validasyonu.
> Şu an **görsel** odaklı; video desteği gelecek sürümlerde planlanıyor.
> Hatalı dosyaları rapor eder, opsiyonel olarak `/rejected`'a taşır veya siler.

[![tests](https://github.com/faraday208/media-validator/actions/workflows/tests.yml/badge.svg)](https://github.com/faraday208/media-validator/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/built%20with-uv-261230)](https://github.com/astral-sh/uv)

`media-dataset-prep` pipeline'ının **01. adımı**. Standalone kullanılabilir; meta repo'ya bağlı değil.

---

## 🎯 Ne yapıyor?

Bir dataset klasörünü tarar ve her görseli yedi kontrolden geçirir:

| # | Kontrol | Reason kodları |
|---|---|---|
| 1 | Dosya var ve okunabilir mi? | `file_not_found`, `not_a_file` |
| 2 | Dosya boyutu sınırlar içinde mi? | `file_too_small`, `file_too_large` |
| 3 | Format (uzantı) izinli mi? | `invalid_format` |
| 4 | PIL header + decode bütünlüğü | `corrupted: <detay>` |
| 5 | Kısa kenar (px) sınırlar içinde mi? | `too_small`, `too_large` |
| 6 | Aspect ratio (w/h) sınırlar içinde mi? | `aspect_too_narrow`, `aspect_too_wide` |
| 7 | Sadece geçerliler için: tüm metadata raporlanır | (reason yok) |

Threshold'lar `config/settings.yaml`'den okunur, **CLI flag'leri** ile ezilebilir.

---

## 🚀 Kurulum

```bash
git clone https://github.com/faraday208/media-validator
cd media-validator
uv sync
```

veya `media-dataset-prep` workspace'i altında:

```bash
cd media-dataset-prep
make install   # tüm tool'lar tek venv'e
```

---

## 🛠️ Kullanım — CLI

### Sadece raporla (default, dosyalara dokunmaz)

```bash
uv run python run.py -i ./dataset
```

Çıktı:
- Console: özet + reason kırılımı
- JSON: `./dataset/validate_report.json` (per-file detay)

### Recursive scan

```bash
uv run python run.py -i ./dataset --recursive
```

### Hatalıları taşı (undoable)

```bash
uv run python run.py -i ./dataset --recursive \
    --invalid-action move \
    --invalid-dir ./rejected
```

`./rejected/validate_report.json` da yazılır — **undo için bunu kullanırsın**.

### Hatalıları sil (irreversible — onay sorar)

```bash
uv run python run.py -i ./dataset --invalid-action delete

# Onay sormadan:
uv run python run.py -i ./dataset --invalid-action delete --yes
```

### Threshold override

```bash
uv run python run.py -i ./dataset \
    --min-short-edge 256 \
    --min-aspect 0.4 --max-aspect 2.5 \
    --allowed-formats jpg,png,webp
```

### Dry-run (aksiyonu simüle et)

```bash
uv run python run.py -i ./dataset \
    --invalid-action move --invalid-dir ./rejected \
    --dry-run
```

Rapor yazılır, dosyalar yerinde kalır — UI önizlemesi için ideal.

### Geri al (undo)

```bash
uv run python run.py --undo ./rejected/validate_report.json
```

`move` aksiyonu undoable; `delete` değildir (rapor `irreversible_deletes` sayısı raporlar).

---

## 📋 Operation modes — özet

| Mod | Komut | Etki | Undo |
|---|---|---|---|
| **Sadece rapor** | `--invalid-action none` (default) | Dosyalara dokunulmaz | – |
| **Move** | `--invalid-action move --invalid-dir D` | Hatalılar D'ye taşınır | ✓ |
| **Delete** | `--invalid-action delete` | Hatalılar silinir | ✗ irreversible |
| **Dry-run** | + `--dry-run` | Rapor üretilir, fiziksel değişiklik yok | – |
| **Undo** | `--undo REPORT` | move-action geri alınır | – |

---

## 🚩 Tüm CLI flag'leri

| Flag | Tip | Default | Açıklama |
|---|---|---|---|
| `-i, --input` | str | – | Input klasörü (zorunlu, `--undo` hariç) |
| `-o, --output` | str | `<input>/validate_report.json` | Rapor JSON çıktısı |
| `--recursive` | flag | False | Alt klasörleri de tara |
| `--limit` | int | 0 (limitsiz) | Max dosya sayısı |
| `--invalid-action` | `none\|move\|delete` | `none` | Hatalılar için aksiyon |
| `--invalid-dir` | str | – | move için hedef klasör |
| `--dry-run` | flag | False | Aksiyonu simüle et |
| `--yes` | flag | False | Onay sorma (delete için) |
| `--min-short-edge` | int | (config'ten) | Min kısa kenar (px) |
| `--max-short-edge` | int | (config'ten) | Max kısa kenar (px) |
| `--min-aspect` | float | (config'ten) | Min aspect ratio (w/h) |
| `--max-aspect` | float | (config'ten) | Max aspect ratio (w/h) |
| `--min-file-size-kb` | float | (config'ten) | Min dosya boyutu |
| `--max-file-size-mb` | float | (config'ten) | Max dosya boyutu |
| `--allowed-formats` | str | (config'ten) | virgülle: `jpg,png,webp` |
| `--undo` | str | – | Validate raporundan undo |
| `--config` | str | `config/settings.yaml` | Config dosyası yolu |

---

## ⚙️ Config — `config/settings.yaml`

```yaml
file_validation:
  allowed_formats: [jpg, jpeg, png, webp]
  min_file_size_kb: 100       # 100 KB altı muhtemelen bozuk/thumbnail
  max_file_size_mb: 50

dimensions:
  min_short_edge: 512         # SDXL minimum
  max_short_edge: 8192
  aspect_ratio:
    min: 0.5                  # 1:2
    max: 2.0                  # 2:1
```

CLI flag'leri **override** eder. Config eksikse default'lar (yukarıdaki değerler) devreye girer.

---

## 🔌 In-process (library) kullanım

```python
from validator_core import FileValidator, collect_images, apply_action, undo_from_report

config = {
    "file_validation": {"allowed_formats": ["jpg", "png"], "min_file_size_kb": 50},
    "dimensions": {"min_short_edge": 512, "aspect_ratio": {"min": 0.5, "max": 2.0}},
}
v = FileValidator(config)

# Tara + validate
images = collect_images("./dataset", recursive=True)
results = [v.validate(p).to_dict() for p in images]

# Aksiyon (opsiyonel)
res = apply_action(
    results,
    source_root="./dataset",
    action="move",
    invalid_dir="./rejected",
    dry_run=False,
)
print(f"Taşınan: {len(res.entries)}")

# Undo (opsiyonel)
# summary = undo_from_report("./rejected/validate_report.json")
```

`media-dataset-prep` meta UI'ı bu yolla in-process kullanıyor — subprocess yok.

---

## 📄 Rapor formatı

```jsonc
{
  "version": "1",
  "tool": "media-validator",
  "source_root": "/abs/path/to/dataset",
  "recursive": true,
  "allowed_exts": [".jpg", ".jpeg", ".png", ".webp"],
  "config": { /* FileValidator config özeti */ },
  "summary": {
    "total": 100,
    "valid": 87,
    "invalid": 13,
    "reasons": {"too_small": 8, "aspect_too_wide": 3, "corrupted: ...": 2}
  },
  "action": "move",
  "invalid_dir": "/abs/path/to/rejected",
  "actions": [
    {"original": "/abs/.../tiny.jpg", "reason": "too_small",
     "moved_to": "/abs/rejected/tiny.jpg"},
    {"original": "/abs/.../broken.jpg", "reason": "corrupted: ...",
     "deleted": true}
  ],
  "skipped": 0,
  "results": [ /* per-file FileValidationResult dict'leri */ ]
}
```

`actions` listesi `--undo` için kullanılır.

---

## 🧪 Test

```bash
uv sync --group dev
uv run pytest
```

43 test: validator unit + scanner (collect/apply/undo) + CLI e2e.

---

## ⚠️ Limitations

- Recursive move'da invalid dosyalar **flat** olarak `invalid_dir`'e iner (alt klasör hiyerarşisi korunmaz). İsim çakışması durumunda `_1`, `_2` eklenir.
- `--invalid-action delete` **irreversible** — silinen dosya geri gelmez. Önce `move` ile dene, sonra silmek istiyorsan `rejected`'i manuel sil.
- Tek thread (Pillow CPU-bound). 10K+ dosyada birkaç dakika sürebilir.
- Şu an sadece **görsel** validasyonu (Pillow). Video desteği planlı (ffprobe entegrasyonu).

---

## 🏷️ Sürüm

**v0.4.0** — pipeline integrasyonu cross-tool tutarlılık. **BC change**: `--recursive` default True (önceki opt-in); diğer tüm tool'larla (dedup, quality, watermark, resize) tutarlı. Opt-out için `--no-recursive` flag eklendi. Ayrıca **tree-preserving move**: recursive + tree-mode dataset'te `--invalid-action move` subdir hiyerarşisini koruyor (`relative_to(source_root)` mirror). +2 regression test (45 toplam).

**v0.3.0** — paket adı `image-validator` → `media-validator` (media-organizer ile tutarlı; ileride video desteği için isim hazır). Rapor `tool: "media-validator"`. Eski raporları (`tool: "image-validator"`) `--undo` hala kabul ediyor (back-compat).

**v0.2.1** — kritik bug fix: `apply_action` artık `FileValidationResult.path` (absolute) kullanıyor; recursive senaryoda aynı isimli dosyaların yanlış silinme/taşınma sorunu giderildi. Eski rapor formatlarına fallback (filename rglob) korunuyor. 43 test (4 yeni regression).

**v0.2.0** — recursive scan, action layer (move/delete), undo, threshold CLI override'ları, 39 unit test, README.

Önceki: v0.1.0 (rapor-only, top-level scan).

---

## 📜 Lisans

[MIT](LICENSE)
