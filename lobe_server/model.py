"""
Image classification model loader with dual ONNX/TFLite backend.

Auto-detects format by scanning model directory for .tflite or .onnx files.
Labels are loaded from labels.txt or signature.json (in that priority).

Labels source priority:
  1. labels.txt (one label per line, index = class id)
  2. signature.json -> classes.Label

signature.json may also contain:
  "filename" — optional, overrides auto-detect of model file

Legacy Microsoft Lobe format is supported — only "classes.Label" and
"filename" are read, everything else is ignored.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import ai_edge_litert.interpreter as tflite
import numpy as np
import numpy.typing as npt
import onnxruntime as _ort

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

_NCHW_CHANNEL_DIM = 1
_NHWC_CHANNEL_DIM = 3
_TENSOR_4D = 4
_TENSOR_3D = 3
_TENSOR_2D = 2


class ClassificationResult:
    def __init__(self, labels: list[tuple[str, float]]) -> None:
        self._labels = labels

    @property
    def prediction(self) -> str:
        return self._labels[0][0]

    @property
    def labels(self) -> list[tuple[str, float]]:
        return self._labels


class ImageModel(Protocol):
    def predict(self, image: Image.Image) -> ClassificationResult: ...


def load_model(path: str | Path) -> ImageModel:
    model_path = Path(path)
    sig_path = model_path / "signature.json"

    filename: str | None = None
    if sig_path.exists():
        with sig_path.open(encoding="utf-8-sig") as f:
            sig = json.load(f)
        filename = sig.get("filename")

    if filename:
        model_file = model_path / filename
        if not model_file.exists():
            msg = f"Model file specified in signature.json not found: {model_file}"
            raise FileNotFoundError(msg)
        ext = model_file.suffix.lower()
        if ext == ".tflite":
            logger.info("Loading model: %s", model_file)
            return TFLiteImageModel.load(model_path, filename)
        if ext == ".onnx":
            logger.info("Loading model: %s", model_file)
            return ONNXImageModel.load(model_path, filename)
        msg = f"Unknown model format in signature.json filename: {ext}"
        raise ValueError(msg)

    tflite_files = sorted(model_path.glob("*.tflite"))
    onnx_files = sorted(model_path.glob("*.onnx"))

    if tflite_files and not onnx_files:
        logger.info("Loading model: %s", model_path / tflite_files[0].name)
        return TFLiteImageModel.load(model_path, tflite_files[0].name)
    if onnx_files:
        logger.info("Loading model: %s", model_path / onnx_files[0].name)
        return ONNXImageModel.load(model_path, onnx_files[0].name)

    msg = f"No model found at {model_path}. Need a .tflite or .onnx file."
    raise FileNotFoundError(msg)


def _read_labels(model_path: Path) -> list[str]:
    labels_path = model_path / "labels.txt"
    if labels_path.exists():
        labels = labels_path.read_text(encoding="utf-8-sig").strip().splitlines()
        labels = [ln for ln in labels if ln]
        if not labels:
            msg = f"labels.txt at {model_path} is empty."
            raise ValueError(msg)
        return labels

    sig_path = model_path / "signature.json"
    if sig_path.exists():
        with sig_path.open(encoding="utf-8-sig") as f:
            sig = json.load(f)
        if "classes" in sig and "Label" in sig["classes"]:
            return sig["classes"]["Label"]
        msg = f"signature.json at {model_path} is missing 'classes.Label'."
        raise ValueError(msg)

    msg = f"No labels found at {model_path}. Provide labels.txt or signature.json with classes.Label."
    raise FileNotFoundError(msg)


class ONNXImageModel:
    def __init__(self, session: Any, labels: list[str], input_name: str, input_size: tuple[int, int]) -> None:  # noqa: ANN401
        self._session = session
        self._labels = labels
        self._input_name = input_name
        self._input_size = input_size
        self._is_nchw = False
        shape = session.get_inputs()[0].shape
        # Heuristic: detect NCHW vs NHWC layout for 4D tensors.
        # NCHW: channels in dim 1 (e.g., [1, 3, 224, 224])
        # NHWC: channels in dim 3 (e.g., [1, 224, 224, 3])
        # When both dims 1 and 3 are plausible channel counts (1 or 3),
        # fall back to NHWC (common for TF-exported ONNX models). This
        # mis-detects NCHW with 1x1 spatial dims like [1, 3, 1, 1].
        if len(shape) == _TENSOR_4D and shape[_NCHW_CHANNEL_DIM] in (1, 3) and shape[_NHWC_CHANNEL_DIM] not in (1, 3):
            self._is_nchw = True

    @classmethod
    def load(cls, model_path: str | Path, filename: str = "model.onnx") -> ONNXImageModel:
        onnx_path = Path(model_path) / filename
        session = _ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

        input_meta = session.get_inputs()[0]  # type: ignore[reportUnknownMemberType, reportUnknownVariableType]
        input_name: str = input_meta.name  # type: ignore[reportUnknownMemberType, reportUnknownVariableType]
        shape: list[int | str | None] = list(input_meta.shape)  # type: ignore[reportUnknownMemberType]
        dims = [int(d) for d in shape if isinstance(d, (int, float)) and d != -1]

        if len(dims) >= _TENSOR_4D:
            dims = dims[1:]
        if len(dims) == _TENSOR_3D:
            if dims[0] in (1, 3):
                _, h, w = dims
            else:
                h, w, _ = dims
        elif len(dims) == _TENSOR_2D:
            h, w = dims
        else:
            h, w = 224, 224

        input_size = (h, w)

        input_name = input_name.removesuffix(":0")  # type: ignore[reportUnknownVariableType]  # strip TF SavedModel :0 suffix

        labels = _read_labels(Path(model_path))

        return cls(session, labels, input_name, input_size)  # type: ignore[reportUnknownArgumentType]

    def predict(self, image: Image.Image) -> ClassificationResult:
        processed: npt.NDArray[np.float32] = _preprocess(image, self._input_size)
        if self._is_nchw:
            processed = np.transpose(processed, (0, 3, 1, 2))
        output = self._session.run(None, {self._input_name: processed})
        raw = output[0]
        confidences = raw[0].tolist() if raw.ndim > 1 else raw.tolist()
        if len(self._labels) != len(confidences):
            msg = f"Model returned {len(confidences)} classes but labels have {len(self._labels)}"
            raise ValueError(msg)
        paired = list(zip(self._labels, confidences, strict=True))
        paired.sort(key=lambda x: x[1], reverse=True)
        return ClassificationResult(paired)


class TFLiteImageModel:
    def __init__(self, interpreter: Any, labels: list[str], input_size: tuple[int, int]) -> None:  # noqa: ANN401
        self._interpreter = interpreter
        self._labels = labels
        self._input_size = input_size
        self._input_index = interpreter.get_input_details()[0]["index"]
        self._output_index = interpreter.get_output_details()[0]["index"]

    @classmethod
    def load(cls, model_path: str | Path, filename: str = "model.tflite") -> TFLiteImageModel:
        tflite_path = Path(model_path) / filename
        interpreter = tflite.Interpreter(model_path=str(tflite_path))
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()[0]  # type: ignore[reportUnknownVariableType]
        shape: list[int] = list(input_details["shape"])  # type: ignore[arg-type]
        _, h, w, _ = shape
        input_size = (h, w)

        labels = _read_labels(Path(model_path))

        return cls(interpreter, labels, input_size)

    def predict(self, image: Image.Image) -> ClassificationResult:
        processed: npt.NDArray[np.float32] = _preprocess(image, self._input_size)
        self._interpreter.set_tensor(self._input_index, processed)
        self._interpreter.invoke()
        raw = self._interpreter.get_tensor(self._output_index)
        confidences = raw[0].tolist() if raw.ndim > 1 else raw.tolist()
        if len(self._labels) != len(confidences):
            msg = f"Model returned {len(confidences)} classes but labels have {len(self._labels)}"
            raise ValueError(msg)
        paired = list(zip(self._labels, confidences, strict=True))
        paired.sort(key=lambda x: x[1], reverse=True)
        return ClassificationResult(paired)


def _preprocess(image: Image.Image, target_size: tuple[int, int]) -> npt.NDArray[np.float32]:
    image = image.convert("RGB")
    image = _resize_uniform_to_fill(image, target_size)
    image = _crop_center(image, target_size)
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


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
