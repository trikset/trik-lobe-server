import json
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from lobe_server.model import (
    ClassificationResult,
    TFLiteImageModel,
    _crop_center,
    _preprocess,
    _resize_uniform_to_fill,
    _update_orientation,
)


def test_classification_result() -> None:
    labels = [("cat", 0.9), ("dog", 0.1)]
    result = ClassificationResult(labels)
    assert result.prediction == "cat"
    assert result.labels == labels


def test_classification_result_single() -> None:
    result = ClassificationResult([("cat", 1.0)])
    assert result.prediction == "cat"


def test_resize_uniform_to_fill() -> None:
    im = Image.new("RGB", (100, 200))
    resized = _resize_uniform_to_fill(im, (224, 224))
    assert resized.width >= 224
    assert resized.height >= 224


def test_crop_center() -> None:
    im = Image.new("RGB", (300, 300))
    cropped = _crop_center(im, (224, 224))
    assert cropped.size == (224, 224)


def test_crop_center_off_center() -> None:
    im = Image.new("RGB", (400, 200))
    cropped = _crop_center(im, (100, 100))
    assert cropped.size == (100, 100)


def test_preprocess_output_shape() -> None:
    im = Image.new("RGB", (640, 480))
    arr = _preprocess(im, (224, 224))
    assert arr.shape == (1, 224, 224, 3)
    assert arr.dtype == np.float32
    assert 0.0 <= arr.min() <= arr.max() <= 1.0


def test_preprocess_grayscale() -> None:
    im = Image.new("L", (100, 100))
    arr = _preprocess(im, (64, 64))
    assert arr.shape == (1, 64, 64, 3)


def test_update_orientation_no_exif() -> None:
    im = Image.new("RGB", (100, 100))
    result = _update_orientation(im)
    assert result is im or result.size == im.size


def _make_mock_tflite() -> MagicMock:
    mock_tflite = MagicMock()
    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [{"index": 0, "name": "input", "shape": [1, 3, 3, 1]}]
    mock_interp.get_output_details.return_value = [{"index": 1, "name": "output", "shape": [1, 2]}]
    mock_tflite.Interpreter.return_value = mock_interp
    return mock_tflite, mock_interp


def _write_fake_model_dir(tmp: str, labels: list | None = None) -> None:
    sig = {
        "format": "tf_lite",
        "filename": "model.tflite",
        "inputs": {"Image": {"name": "input", "shape": [1, 128, 128, 3]}},
        "outputs": {"Confidences": {"name": "output", "shape": [1, 3]}},
        "classes": {"Label": labels or ["cat", "dog", "bird"]},
        "export_model_version": 1,
    }
    (Path(tmp) / "signature.json").write_text(json.dumps(sig), encoding="utf-8")
    (Path(tmp) / "model.tflite").write_bytes(b"fake model")


def test_model_load() -> None:
    mock_tflite, mock_interp = _make_mock_tflite()
    tflite_mod = types.ModuleType("tflite_runtime")
    interp_mod = types.ModuleType("tflite_runtime.interpreter")
    interp_mod.Interpreter = mock_tflite.Interpreter

    with (
        patch.dict(
            "sys.modules",
            {"tflite_runtime": tflite_mod, "tflite_runtime.interpreter": interp_mod},
        ),
        tempfile.TemporaryDirectory() as tmp,
    ):
        _write_fake_model_dir(tmp)
        model = TFLiteImageModel.load(tmp)

    assert model._labels == ["cat", "dog", "bird"]
    assert model._input_size == (128, 128)
    mock_tflite.Interpreter.assert_called_once()
    mock_interp.allocate_tensors.assert_called_once()


def test_model_predict() -> None:
    _, mock_interp = _make_mock_tflite()
    mock_interp.get_tensor.return_value = np.array([[0.1, 0.9]], dtype=np.float32)

    model = TFLiteImageModel(mock_interp, ["dog", "cat"], (3, 3))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "cat"
    mock_interp.set_tensor.assert_called_once()
    mock_interp.invoke.assert_called_once()


def test_model_predict_ordering() -> None:
    _, mock_interp = _make_mock_tflite()
    mock_interp.get_tensor.return_value = np.array([[0.3, 0.6, 0.1]], dtype=np.float32)

    model = TFLiteImageModel(mock_interp, ["a", "b", "c"], (3, 3))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "b"
    assert result.labels[0][0] == "b"
    assert result.labels[0][1] == pytest.approx(0.6)
    assert result.labels[1][0] == "a"
    assert result.labels[1][1] == pytest.approx(0.3)
    assert result.labels[2][0] == "c"
    assert result.labels[2][1] == pytest.approx(0.1)
