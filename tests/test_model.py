import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import ANY, MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from lobe_server.model import (
    ClassificationResult,
    ONNXImageModel,
    TFLiteImageModel,
    _crop_center,
    _preprocess,
    _read_labels,
    _resize_uniform_to_fill,
    load_model,
)


def _make_input_meta(name: str = "Image", shape: list[Any] | None = None) -> MagicMock:
    meta = MagicMock()
    meta.name = name
    meta.shape = shape or [None, 224, 224, 3]
    return meta


def _make_output_meta(shape: list[Any] | None = None) -> MagicMock:
    meta = MagicMock()
    meta.shape = shape or [None, 3]
    return meta


def _make_onnx_session(labels_n: int = 3, input_shape: list[Any] | None = None) -> MagicMock:
    session = MagicMock()
    if labels_n > 0:
        output = np.array([[1.0 / labels_n] * labels_n], dtype=np.float32)
        output[0][0] = 0.8
        if labels_n > 1:
            output[0][1] = 0.15
    else:
        output = np.array([[]], dtype=np.float32)
    session.run.return_value = [output]
    session.get_inputs.return_value = [_make_input_meta(shape=input_shape)]
    session.get_outputs.return_value = [_make_output_meta(shape=[None, labels_n])]
    return session


def _make_tflite_interpreter(
    input_shape: list[int] | None = None,
    num_classes: int = 3,
) -> MagicMock:
    interp = MagicMock()
    interp.get_input_details.return_value = [
        {"index": 0, "shape": input_shape or [1, 224, 224, 3], "dtype": np.float32}
    ]
    interp.get_output_details.return_value = [{"index": 1, "shape": [1, num_classes], "dtype": np.float32}]
    if num_classes > 0:
        output = np.array([[1.0 / num_classes] * num_classes], dtype=np.float32)
        output[0][0] = 0.9
    else:
        output = np.array([[]], dtype=np.float32)
    interp.get_tensor.return_value = output
    return interp


def _tflite_patch(interpreter: MagicMock) -> Any:
    import lobe_server.model as model_mod

    tflite_mock = MagicMock()
    tflite_mock.Interpreter.return_value = interpreter
    return patch.object(model_mod, "tflite", tflite_mock)


def _write_labels_txt(tmp: str, labels: list[str]) -> Path:
    (Path(tmp) / "labels.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")
    return Path(tmp)


def _write_signature(tmp: str, labels: list[str], filename: str | None = None) -> Path:
    sig: dict[str, Any] = {"classes": {"Label": labels}}
    if filename:
        sig["filename"] = filename
    (Path(tmp) / "signature.json").write_text(json.dumps(sig), encoding="utf-8")
    return Path(tmp)


def _write_lobe_signature(tmp: str, labels: list[str] | None = None, filename: str | None = None) -> Path:
    sig = {
        "format": "tf_lite",
        "filename": filename or "model.tflite",
        "inputs": {"Image": {"dtype": "float32", "shape": [None, 224, 224, 3], "name": "Image"}},
        "outputs": {"Confidences": {"dtype": "float32", "shape": [None, 3], "name": "uuid/dense_2/Softmax"}},
        "classes": {"Label": labels or ["cat", "dog", "bird"]},
        "export_model_version": 1,
    }
    (Path(tmp) / "signature.json").write_text(json.dumps(sig), encoding="utf-8")
    return Path(tmp)


# ── ClassificationResult ────────────────────────────────────────


def test_classification_result() -> None:
    labels = [("cat", 0.9), ("dog", 0.1)]
    result = ClassificationResult(labels)
    assert result.prediction == "cat"
    assert result.labels == labels


def test_classification_result_single() -> None:
    result = ClassificationResult([("cat", 1.0)])
    assert result.prediction == "cat"


# ── Preprocessing ───────────────────────────────────────────────


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


# ── _read_labels ────────────────────────────────────────────────


def test_read_labels_from_labels_txt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_labels_txt(tmp, ["a", "b"])
        assert _read_labels(Path(tmp)) == ["a", "b"]


def test_read_labels_from_signature_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_signature(tmp, ["x", "y", "z"])
        assert _read_labels(Path(tmp)) == ["x", "y", "z"]


def test_read_labels_prefers_labels_txt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_labels_txt(tmp, ["from_txt"])
        _write_signature(tmp, ["from_sig"])
        assert _read_labels(Path(tmp)) == ["from_txt"]


def test_read_labels_no_source_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(FileNotFoundError, match=r"No labels found"):
        _read_labels(Path(tmp))


def test_read_labels_signature_missing_classes_label_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "signature.json").write_text(json.dumps({"format": "tf_lite"}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"missing 'classes.Label'"):
            _read_labels(Path(tmp))


# ── ONNXImageModel ──────────────────────────────────────────────


def test_onnx_model_load_with_labels_txt() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["cat", "dog", "bird"])
        model = ONNXImageModel.load(tmp)

    assert model._labels == ["cat", "dog", "bird"]
    assert model._input_size == (224, 224)
    assert model._input_name == "Image"


def test_onnx_model_load_with_signature_json() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_signature(tmp, ["dog", "cat", "bird"])
        model = ONNXImageModel.load(tmp)

    assert model._labels == ["dog", "cat", "bird"]


def test_onnx_model_load_no_labels_raises() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        with pytest.raises(FileNotFoundError, match=r"No labels found"):
            ONNXImageModel.load(tmp)


def test_onnx_model_load_nchw_shape() -> None:
    session = _make_onnx_session(3, input_shape=[None, 3, 224, 224])
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)

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
    session.get_inputs.return_value = [_make_input_meta()]

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


# ── TFLiteImageModel ────────────────────────────────────────────


def test_tflite_model_load_with_labels_txt() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        _write_labels_txt(tmp, ["cat", "dog", "bird"])
        model = TFLiteImageModel.load(tmp)

    assert model._labels == ["cat", "dog", "bird"]
    assert model._input_size == (224, 224)


def test_tflite_model_load_with_signature_json() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        _write_signature(tmp, ["x", "y", "z"])
        model = TFLiteImageModel.load(tmp)

    assert model._labels == ["x", "y", "z"]
    assert model._input_size == (224, 224)


def test_tflite_model_load_no_labels_raises() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        with pytest.raises(FileNotFoundError, match=r"No labels found"):
            TFLiteImageModel.load(tmp)


def test_tflite_model_load_custom_filename() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "custom.tflite").write_bytes(b"fake tflite")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = TFLiteImageModel.load(tmp, filename="custom.tflite")

    assert model._labels == ["a", "b", "c"]


def test_tflite_model_predict() -> None:
    interpreter = _make_tflite_interpreter(num_classes=2)
    model = TFLiteImageModel(interpreter, ["dog", "cat"], (224, 224))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "dog"
    interpreter.set_tensor.assert_called_once()
    interpreter.invoke.assert_called_once()
    interpreter.get_tensor.assert_called_once_with(1)


def test_tflite_model_predict_ordering() -> None:
    interpreter = MagicMock()
    interpreter.get_input_details.return_value = [{"index": 0, "shape": [1, 224, 224, 3], "dtype": np.float32}]
    interpreter.get_output_details.return_value = [{"index": 1, "shape": [1, 3], "dtype": np.float32}]
    interpreter.get_tensor.return_value = np.array([[0.3, 0.6, 0.1]], dtype=np.float32)

    model = TFLiteImageModel(interpreter, ["a", "b", "c"], (224, 224))
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)

    assert result.prediction == "b"
    assert result.labels[0] == ("b", pytest.approx(0.6))
    assert result.labels[1] == ("a", pytest.approx(0.3))
    assert result.labels[2] == ("c", pytest.approx(0.1))


# ── load_model auto-detect ──────────────────────────────────────


def test_load_model_detects_onnx() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)


def test_load_model_without_signature_json_works() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)
    assert model._labels == ["a", "b", "c"]


def test_load_model_detects_tflite() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = load_model(tmp)

    assert isinstance(model, TFLiteImageModel)


def test_load_model_prefers_onnx_over_tflite() -> None:
    session = _make_onnx_session(3)
    interpreter = _make_tflite_interpreter()

    with (
        patch("lobe_server.model._ort.InferenceSession", return_value=session),
        _tflite_patch(interpreter),
        tempfile.TemporaryDirectory() as tmp,
    ):
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)


def test_load_model_no_files_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(FileNotFoundError, match=r"No model found"):
        load_model(tmp)


# ── load_model with explicit filename ───────────────────────────


def test_load_model_with_explicit_tflite_filename() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "custom.tflite").write_bytes(b"fake tflite")
        _write_signature(tmp, ["x", "y", "z"], filename="custom.tflite")
        model = load_model(tmp)

    assert isinstance(model, TFLiteImageModel)
    assert model._labels == ["x", "y", "z"]


def test_load_model_with_explicit_onnx_filename() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "my_model.onnx").write_bytes(b"fake onnx")
        _write_signature(tmp, ["a", "b", "c"], filename="my_model.onnx")
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)
    assert model._labels == ["a", "b", "c"]


def test_load_model_with_explicit_filename_unknown_ext() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.h5").write_bytes(b"")
        _write_signature(tmp, ["a"], filename="model.h5")
        with pytest.raises(ValueError, match=r"Unknown model format"):
            load_model(tmp)


def test_load_model_explicit_tflite_filename_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_signature(tmp, ["a", "b", "c"], filename="missing.tflite")
        with pytest.raises(FileNotFoundError, match=r"signature.json not found"):
            load_model(tmp)


def test_load_model_explicit_onnx_filename_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_signature(tmp, ["a", "b", "c"], filename="missing.onnx")
        with pytest.raises(FileNotFoundError, match=r"signature.json not found"):
            load_model(tmp)


# ── Lobe legacy ─────────────────────────────────────────────────


def test_load_lobe_tflite_legacy() -> None:
    interpreter = _make_tflite_interpreter()
    with _tflite_patch(interpreter), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.tflite").write_bytes(b"fake tflite")
        _write_lobe_signature(tmp, ["a", "b", "c"])
        model = load_model(tmp)

    assert isinstance(model, TFLiteImageModel)
    assert model._labels == ["a", "b", "c"]


def test_load_lobe_onnx_legacy() -> None:
    session = _make_onnx_session(3)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_lobe_signature(tmp, ["x", "y", "z"], filename="model.onnx")
        model = load_model(tmp)

    assert isinstance(model, ONNXImageModel)
    assert model._labels == ["x", "y", "z"]


# ── Edge cases for coverage ──────────────────────────────────────


def test_read_labels_empty_labels_txt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "labels.txt").write_text("\n\n\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"empty"):
            _read_labels(Path(tmp))


def test_onnx_model_load_4d_shape() -> None:
    session = _make_onnx_session(3, input_shape=[1, 3, 224, 224])
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)

    assert model._input_size == (224, 224)


def test_onnx_model_load_2d_shape() -> None:
    session = _make_onnx_session(3, input_shape=[224, 224])
    session.get_inputs.return_value = [_make_input_meta(shape=[224, 224])]
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)

    assert model._input_size == (224, 224)


def test_onnx_model_load_colon_zero_name() -> None:
    session = MagicMock()
    meta = MagicMock()
    meta.name = "serving_default_input:0"
    meta.shape = [None, 224, 224, 3]
    session.get_inputs.return_value = [meta]
    output = np.array([[1.0 / 3] * 3], dtype=np.float32)
    output[0][0] = 0.8
    session.run.return_value = [output]
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)

    assert model._input_name == "serving_default_input"


def test_onnx_model_predict_nchw() -> None:
    session = _make_onnx_session(2, input_shape=[None, 3, 224, 224])
    model = ONNXImageModel(session, ["dog", "cat"], "Image", (224, 224))
    assert model._is_nchw is True
    im = Image.new("RGB", (10, 10))
    result = model.predict(im)
    assert result.prediction == "dog"
    session.run.assert_called_once()


def test_onnx_model_load_hw_shape() -> None:
    session = _make_onnx_session(3, input_shape=[None, 224, 224, 3])
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)

    assert model._input_size == (224, 224)
