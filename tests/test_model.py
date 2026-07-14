import json
import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from lobe_server.model import (
    ClassificationResult,
    ONNXImageModel,
    _crop_center,
    _ensure_converted,
    _preprocess,
    _resize_uniform_to_fill,
    _update_orientation,
    load_model,
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


def _make_onnx_session(labels_n: int) -> MagicMock:
    session = MagicMock()
    output = np.array([[1.0 / labels_n] * labels_n], dtype=np.float32)
    output[0][0] = 0.8
    output[0][1] = 0.15
    session.run.return_value = [output]
    return session


def _write_fake_model_dir(
    tmp: str,
    fmt: str = "tf_lite",
    labels: list[str] | None = None,
) -> None:
    sig = {
        "format": fmt,
        "filename": "saved_model.tflite" if fmt == "tf_lite" else "model.onnx",
        "inputs": {"Image": {"dtype": "float32", "shape": [None, 224, 224, 3], "name": "Image"}},
        "outputs": {"Confidences": {"dtype": "float32", "shape": [None, 3], "name": "uuid/dense_2/Softmax"}},
        "classes": {"Label": labels or ["cat", "dog", "bird"]},
        "export_model_version": 1,
    }
    (Path(tmp) / "signature.json").write_text(json.dumps(sig), encoding="utf-8")
    (Path(tmp) / "saved_model.tflite").write_bytes(b"fake tflite model")


def test_onnx_model_load() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        _write_fake_model_dir(tmp, fmt="onnx")
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        model = ONNXImageModel.load(tmp)

    assert model._labels == ["cat", "dog", "bird"]
    assert model._input_size == (224, 224)
    assert model._input_name == "Image"


def test_onnx_model_predict() -> None:
    session = _make_onnx_session(2)
    model = ONNXImageModel(session, ["dog", "cat"], "Image", (224, 224))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "dog"
    session.run.assert_called_once_with(None, {"Image": ANY})


def test_onnx_model_predict_ordering() -> None:
    session = MagicMock()
    session.run.return_value = [np.array([[0.3, 0.6, 0.1]], dtype=np.float32)]

    model = ONNXImageModel(session, ["a", "b", "c"], "Image", (224, 224))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "b"
    assert result.labels[0][0] == "b"
    assert result.labels[0][1] == pytest.approx(0.6)
    assert result.labels[1][0] == "a"
    assert result.labels[1][1] == pytest.approx(0.3)
    assert result.labels[2][0] == "c"
    assert result.labels[2][1] == pytest.approx(0.1)


def test_load_model_onnx_direct() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        _write_fake_model_dir(tmp, fmt="onnx")
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        model = load_model(tmp)
    assert isinstance(model, ONNXImageModel)


def test_load_model_tflite_converts() -> None:
    session = _make_onnx_session(3)
    with (
        patch("lobe_server.model._ort.InferenceSession", return_value=session),
        patch("tflite2onnx.convert") as mock_convert,
        tempfile.TemporaryDirectory() as tmp,
    ):
        _write_fake_model_dir(tmp, fmt="tf_lite")
        model = load_model(tmp)

        sig = json.loads((Path(tmp) / "signature.json").read_text(encoding="utf-8"))
        assert sig["format"] == "onnx"
        assert sig["filename"] == "model.onnx"

    assert isinstance(model, ONNXImageModel)
    mock_convert.assert_called_once()


def test_load_model_tflite_cached_onx_exists() -> None:
    session = _make_onnx_session(3)
    with (
        patch("lobe_server.model._ort.InferenceSession", return_value=session),
        patch("tflite2onnx.convert") as mock_convert,
        tempfile.TemporaryDirectory() as tmp,
    ):
        _write_fake_model_dir(tmp, fmt="tf_lite")
        (Path(tmp) / "model.onnx").write_bytes(b"already converted")
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)
    mock_convert.assert_not_called()


def test_ensure_converted_no_tflite_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sig = {"filename": "nonexistent.tflite"}
        with pytest.raises(FileNotFoundError):
            _ensure_converted(Path(tmp), sig)


def test_ensure_converted_missing_tflite2onnx() -> None:
    sig = {"filename": "model.tflite"}
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake")
        with patch.dict("sys.modules", {"tflite2onnx": None}), pytest.raises(ImportError):
            _ensure_converted(Path(tmp), sig)


def test_load_model_tflite_no_convert_no_onnx() -> None:
    session = _make_onnx_session(3)
    with (
        patch("lobe_server.model._ort.InferenceSession", return_value=session),
        patch("tflite2onnx.convert") as mock_convert,
        tempfile.TemporaryDirectory() as tmp,
    ):
        _write_fake_model_dir(tmp, fmt="tf_lite")
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)
    mock_convert.assert_called_once()
