"""
Thin TFLite image classification model.

Replaces the abandoned `lobe` SDK (Microsoft, last release Feb 2022)
with a direct tflite-runtime wrapper. Compatible with models exported
from the Lobe desktop app.

Exported Lobe model directory layout:
    model_path/
        signature.json   # metadata: labels, input shape, model filename
        saved_model.tflite  # or *.tflite (name from signature.json)

signature.json format:
    {
        "format": "tf_lite",
        "filename": "saved_model.tflite",
        "inputs":  {"Image": {"name": "input_1", "shape": [1, 224, 224, 3]}},
        "outputs": {"Confidences": {"name": "dense_1", "shape": [1, N]}},
        "classes": {"Label": ["cat", "dog", ...]},
        "export_model_version": 1
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


class ClassificationResult:
    def __init__(self, labels: list[tuple[str, float]]) -> None:
        self._labels = labels

    @property
    def prediction(self) -> str:
        return self._labels[0][0]

    @property
    def labels(self) -> list[tuple[str, float]]:
        return self._labels


class TFLiteImageModel:
    def __init__(self, interpreter: Any, labels: list[str], input_size: tuple[int, int]) -> None:
        self._interpreter = interpreter
        self._labels = labels
        self._input_size = input_size
        self._input_details = interpreter.get_input_details()
        self._output_details = interpreter.get_output_details()

    @classmethod
    def load(cls, model_path: str | Path) -> TFLiteImageModel:
        try:
            import tflite_runtime.interpreter as tflite
        except ImportError:
            msg = (
                "tflite_runtime is not installed. "
                "Install it from https://google-coral.github.io/py-repo/ "
                "or via your platform package manager."
            )
            raise ImportError(msg) from None

        model_path = Path(model_path)
        sig_path = model_path / "signature.json"

        with open(sig_path, encoding="utf-8") as f:
            signature = json.load(f)

        labels: list[str] = signature["classes"]["Label"]
        input_shape: list[int] = signature["inputs"]["Image"]["shape"]
        input_size = (input_shape[1], input_shape[2])
        filename: str = signature["filename"]

        interpreter = tflite.Interpreter(model_path=str(model_path / filename))
        interpreter.allocate_tensors()

        return cls(interpreter, labels, input_size)

    def predict(self, image: Image.Image) -> ClassificationResult:
        processed = _preprocess(image, self._input_size)
        input_index = self._input_details[0]["index"]
        self._interpreter.set_tensor(input_index, processed)
        self._interpreter.invoke()

        output_index = self._output_details[0]["index"]
        raw = self._interpreter.get_tensor(output_index)

        confidences = raw[0].tolist() if raw.ndim > 1 else raw.tolist()
        paired = list(zip(self._labels, confidences, strict=False))
        paired.sort(key=lambda x: x[1], reverse=True)
        return ClassificationResult(paired)


def _preprocess(image: Image.Image, target_size: tuple[int, int]) -> np.ndarray:
    image = _update_orientation(image)
    image = image.convert("RGB")
    image = _resize_uniform_to_fill(image, target_size)
    image = _crop_center(image, target_size)
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


def _update_orientation(image: Image.Image) -> Image.Image:
    try:
        exif = image._getexif()
    except Exception:
        exif = None
    if exif is None:
        return image

    orientation = exif.get(0x0112, 1)
    ops: list = []
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
