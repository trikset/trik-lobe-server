"""
ONNX image classification model with automatic TFLite conversion.

Loads models exported from Microsoft Lobe or any ONNX image classifier.
If the model is in TFLite format (Lobe default), it is automatically
converted to ONNX on first load using tflite2onnx.

Exported Lobe model directory layout:
    model_path/
        signature.json       # metadata: labels, input shape, model filename
        saved_model.tflite   # original TFLite (kept, converted on first load)
        model.onnx           # converted ONNX (written on first load, used thereafter)

signature.json format:
    {
        "format": "tf_lite" | "onnx",
        "filename": "saved_model.tflite" | "model.onnx",
        "inputs":  {"Image": {"dtype": "float32", "shape": [null, 224, 224, 3], "name": "Image"}},
        "outputs": {"Confidences": {"dtype": "float32", "shape": [null, N], "name": "..."}},
        "classes": {"Label": ["cat", "dog", ...]},
        "export_model_version": 1
    }
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as _ort
from PIL import Image

logger = logging.getLogger(__name__)


class ClassificationResult:
    def __init__(self, labels: list[tuple[str, float]]) -> None:
        self._labels = labels

    @property
    def prediction(self) -> str:
        return self._labels[0][0]

    @property
    def labels(self) -> list[tuple[str, float]]:
        return self._labels


class ONNXImageModel:
    def __init__(self, session: Any, labels: list[str], input_name: str, input_size: tuple[int, int]) -> None:
        self._session = session
        self._labels = labels
        self._input_name = input_name
        self._input_size = input_size

    @classmethod
    def load(cls, model_path: str | Path) -> ONNXImageModel:
        model_path = Path(model_path)
        sig_path = model_path / "signature.json"
        with open(sig_path, encoding="utf-8") as f:
            sig = json.load(f)

        fmt: str = sig.get("format", "tf_lite")
        onnx_path = _ensure_converted(model_path, sig) if fmt in ("tf_lite", "tf") else model_path / sig["filename"]

        labels: list[str] = sig["classes"]["Label"]
        input_shape: list[int] = sig["inputs"]["Image"]["shape"]
        input_size = (input_shape[1], input_shape[2])
        input_name: str = sig["inputs"]["Image"]["name"]
        if input_name.endswith(":0"):
            input_name = input_name[:-2]

        session = _ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        return cls(session, labels, input_name, input_size)

    def predict(self, image: Image.Image) -> ClassificationResult:
        processed: np.ndarray = _preprocess(image, self._input_size)
        output = self._session.run(None, {self._input_name: processed})
        raw = output[0]
        confidences = raw[0].tolist() if raw.ndim > 1 else raw.tolist()
        paired = list(zip(self._labels, confidences, strict=False))
        paired.sort(key=lambda x: x[1], reverse=True)
        return ClassificationResult(paired)


def load_model(path: str | Path) -> ONNXImageModel:
    return ONNXImageModel.load(path)


def _ensure_converted(model_path: Path, sig: dict[str, Any]) -> Path:
    onnx_path = model_path / "model.onnx"
    if onnx_path.exists():
        return onnx_path

    tflite_name = sig.get("filename", "saved_model.tflite")
    tflite_path = model_path / tflite_name
    if not tflite_path.exists():
        msg = f"TFLite model not found: {tflite_path}"
        raise FileNotFoundError(msg)

    logger.info("TFLite model detected. Converting to ONNX (one-time)...")
    try:
        import tflite2onnx  # type: ignore[reportMissingImports]
    except ImportError as exc:
        msg = (
            f"TFLite model at {tflite_path} needs conversion but tflite2onnx is not installed.\n"
            f"  1. Install: pip install tflite2onnx\n"
            f"  2. Convert:  tflite2onnx {tflite_path} {onnx_path}\n"
            f"  3. Update {model_path / 'signature.json'}:\n"
            f"       format = 'onnx', filename = 'model.onnx'"
        )
        raise ImportError(msg) from exc

    tflite2onnx.convert(str(tflite_path), str(onnx_path))

    sig["format"] = "onnx"
    sig["filename"] = "model.onnx"
    sig_path = model_path / "signature.json"
    backup_path = model_path / "signature.json.tflite-backup"
    shutil.copy2(str(sig_path), str(backup_path))
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(sig, f, indent=2)
        f.write("\n")

    logger.info("Conversion complete. Saved as %s", onnx_path)
    return onnx_path


def _preprocess(image: Image.Image, target_size: tuple[int, int]) -> np.ndarray:
    image = _update_orientation(image)
    image = image.convert("RGB")
    image = _resize_uniform_to_fill(image, target_size)
    image = _crop_center(image, target_size)
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


def _update_orientation(image: Image.Image) -> Image.Image:
    try:
        exif = image.getexif()
    except Exception:
        exif = None
    if exif is None:
        return image

    orientation = exif.get(0x0112, 1)
    ops: list[Any] = []
    if orientation >= 4:
        ops.append(Image.Transpose.TRANSPOSE)
    if orientation in (2, 3, 6, 7):
        ops.append(Image.Transpose.FLIP_TOP_BOTTOM)
    if orientation in (1, 2, 5, 6):
        ops.append(Image.Transpose.FLIP_LEFT_RIGHT)
    for op in ops:
        image = image.transpose(op)
    return image


def _resize_uniform_to_fill(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    scale = max(target[0] / image.width, target[1] / image.height)
    new_size = (round(scale * image.width), round(scale * image.height))
    return image.resize(new_size)


def _crop_center(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    left = (image.width - target[0]) // 2
    top = (image.height - target[1]) // 2
    right = left + target[0]
    bottom = top + target[1]
    return image.crop((left, top, right, bottom))
