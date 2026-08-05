# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212,W0621  # tests inspect privates; pytest fixtures shadow names

import json
import tempfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple, Protocol, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

import lobe_server.model as model_mod
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


class _Model(Protocol):
    _labels: list[str]
    _input_size: tuple[int, int]

    def predict(self, image: Image.Image) -> ClassificationResult:
        raise NotImplementedError


class _Backend(NamedTuple):
    model_cls: type[_Model]
    make: Callable[[int], MagicMock]
    construct: Callable[[MagicMock, list[str]], _Model]
    load: Callable[[Path], _Model]
    patch: Callable[[MagicMock], Any]
    set_output: Callable[[MagicMock, np.ndarray], None]
    file: str
    ext: str


@pytest.fixture(params=["onnx", "tflite"], ids=["onnx", "tflite"])
def backend(request: pytest.FixtureRequest) -> _Backend:
    if request.param == "onnx":
        return _Backend(
            model_cls=ONNXImageModel,
            make=_make_onnx_session,
            construct=_construct_onnx,
            load=ONNXImageModel.load,
            patch=_patch_onnx,
            set_output=_set_onnx_output,
            file="model.onnx",
            ext="onnx",
        )
    return _Backend(
        model_cls=TFLiteImageModel,
        make=_make_tflite_interpreter,
        construct=_construct_tflite,
        load=TFLiteImageModel.load,
        patch=_patch_tflite,
        set_output=_set_tflite_output,
        file="model.tflite",
        ext="tflite",
    )


def _construct_onnx(mock: MagicMock, labels: list[str]) -> _Model:
    return ONNXImageModel(mock, labels, "Image", (224, 224))


def _construct_tflite(mock: MagicMock, labels: list[str]) -> _Model:
    return TFLiteImageModel(mock, labels, (224, 224))


def _patch_onnx(mock: MagicMock) -> Any:
    return patch("lobe_server.model._ort.InferenceSession", return_value=mock)


def _patch_tflite(mock: MagicMock) -> Any:
    return _tflite_patch(mock)


def _set_onnx_output(mock: MagicMock, arr: np.ndarray) -> None:
    mock.run.return_value = [arr]


def _set_tflite_output(mock: MagicMock, arr: np.ndarray) -> None:
    mock.get_tensor.return_value = arr


def _make_input_meta(name: str = "Image", shape: list[Any] | None = None) -> MagicMock:
    meta = MagicMock()
    meta.name = name
    meta.shape = shape or [None, 224, 224, 3]
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


def _make_output_meta(shape: list[Any] | None = None) -> MagicMock:
    meta = MagicMock()
    meta.shape = shape or [None, 3]
    return meta


def _make_tflite_interpreter(num_classes: int = 3, input_shape: list[int] | None = None) -> MagicMock:
    interp = MagicMock()
    interp.get_input_details.return_value = [
        {"index": 0, "shape": input_shape or [1, 224, 224, 3], "dtype": np.float32},
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
    tflite_mock = MagicMock()
    tflite_mock.Interpreter.return_value = interpreter
    return patch.object(model_mod, "tflite", tflite_mock)


@contextmanager
def _model_dir(
    backend: _Backend,
    labels: list[str] | None = None,
    sig: list[str] | None = None,
    sig_filename: str | None = None,
    filename: str | None = None,
) -> Generator[Path, None, None]:
    model_file = filename or backend.file
    mock = backend.make(3)
    with backend.patch(mock), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / model_file).write_bytes(b"fake model")
        if labels is not None:
            _write_labels_txt(tmp, labels)
        elif sig is not None:
            _write_signature(tmp, sig, filename=sig_filename)
        yield Path(tmp)


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


def _setup_labels_txt(tmp: str) -> Path:
    return _write_labels_txt(tmp, ["a", "b"])


def _setup_signature(tmp: str) -> Path:
    return _write_signature(tmp, ["x", "y", "z"])


# ── ClassificationResult ────────────────────────────────────────


def test_classification_result() -> None:
    labels = [("cat", 0.9), ("dog", 0.1)]
    result = ClassificationResult(labels)
    assert result.prediction == "cat"
    assert result.labels == labels


# ── Preprocessing ───────────────────────────────────────────────


def test_resize_uniform_to_fill() -> None:
    im = Image.new("RGB", (100, 200))
    resized = _resize_uniform_to_fill(im, (224, 224))
    assert resized.width >= 224
    assert resized.height >= 224


@pytest.mark.parametrize("size", [(300, 300, 224, 224), (400, 200, 100, 100)])
def test_crop_center(size: tuple[int, int, int, int]) -> None:
    w, h, tw, th = size
    assert _crop_center(Image.new("RGB", (w, h)), (tw, th)).size == (tw, th)


@pytest.mark.parametrize("mode", ["RGB", "L"])
def test_preprocess(mode: str) -> None:
    im = Image.new(mode, (100, 100))
    arr = _preprocess(im, (64, 64))
    assert arr.shape == (1, 64, 64, 3)
    assert arr.dtype == np.float32
    assert 0.0 <= arr.min() <= arr.max() <= 1.0


# ── _read_labels ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (_setup_labels_txt, ["a", "b"]),
        (_setup_signature, ["x", "y", "z"]),
    ],
)
def test_read_labels_sources(setup: Callable[[str], Path], expected: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        setup(tmp)
        assert _read_labels(Path(tmp)) == expected


def test_read_labels_prefers_labels_txt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_labels_txt(tmp, ["from_txt"])
        _write_signature(tmp, ["from_sig"])
        assert _read_labels(Path(tmp)) == ["from_txt"]


def test_read_labels_no_source_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(FileNotFoundError, match=r"No labels found"):
        _read_labels(Path(tmp))


def test_read_labels_signature_missing_classes_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "signature.json").write_text(json.dumps({"format": "tf_lite"}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"missing 'classes.Label'"):
            _read_labels(Path(tmp))


def test_read_labels_empty_txt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "labels.txt").write_text("  \n  \n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"empty"):
            _read_labels(Path(tmp))


# ── Model load / predict (parametrized over ONNX + TFLite) ──────


def test_model_load_labels(backend: _Backend) -> None:
    with _model_dir(backend, labels=["a", "b", "c"]) as tmp:
        model = backend.load(tmp)
    assert model._labels == ["a", "b", "c"]
    assert model._input_size == (224, 224)
    if backend.ext == "onnx":
        assert cast("ONNXImageModel", model)._input_name == "Image"


def test_model_load_signature(backend: _Backend) -> None:
    with _model_dir(backend, sig=["x", "y", "z"]) as tmp:
        model = backend.load(tmp)
    assert model._labels == ["x", "y", "z"]


def test_model_load_no_labels_raises(backend: _Backend) -> None:
    with _model_dir(backend) as tmp, pytest.raises(FileNotFoundError, match=r"No labels found"):
        backend.load(tmp)


def test_model_predict(backend: _Backend) -> None:
    model = backend.construct(backend.make(2), ["dog", "cat"])
    result = model.predict(Image.new("RGB", (10, 10)))
    assert result.prediction == "dog"


def test_model_predict_ordering(backend: _Backend) -> None:
    mock = backend.make(3)
    backend.set_output(mock, np.array([[0.3, 0.6, 0.1]], dtype=np.float32))
    result = backend.construct(mock, ["a", "b", "c"]).predict(Image.new("RGB", (10, 10)))
    assert result.prediction == "b"
    assert result.labels == [
        ("b", pytest.approx(0.6)),
        ("a", pytest.approx(0.3)),
        ("c", pytest.approx(0.1)),
    ]


def test_model_predict_label_mismatch(backend: _Backend) -> None:
    model = backend.construct(backend.make(3), ["a", "b"])
    with pytest.raises(ValueError, match=r"labels have 2"):
        model.predict(Image.new("RGB", (10, 10)))


# ── load_model auto-detect ──────────────────────────────────────


def test_load_model_detects(backend: _Backend) -> None:
    with _model_dir(backend, labels=["a", "b", "c"]) as tmp:
        model = load_model(tmp)
    assert isinstance(model, backend.model_cls)
    assert model._labels == ["a", "b", "c"]


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


def test_load_model_explicit_filename(backend: _Backend) -> None:
    name = "custom." + backend.ext
    with _model_dir(backend, sig=["a", "b", "c"], sig_filename=name, filename=name) as tmp:
        model = load_model(tmp)
    assert isinstance(model, backend.model_cls)
    assert model._labels == ["a", "b", "c"]


def test_load_model_explicit_filename_missing(backend: _Backend) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_signature(tmp, ["a", "b", "c"], filename="missing." + backend.ext)
        with pytest.raises(FileNotFoundError, match=r"signature.json not found"):
            load_model(tmp)


def test_load_model_with_explicit_filename_unknown_ext() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.h5").write_bytes(b"")
        _write_signature(tmp, ["a"], filename="model.h5")
        with pytest.raises(ValueError, match=r"Unknown model format"):
            load_model(tmp)


def test_load_lobe_legacy(backend: _Backend) -> None:
    with backend.patch(backend.make(3)), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / backend.file).write_bytes(b"fake model")
        _write_lobe_signature(tmp, ["a", "b", "c"], filename=backend.file)
        model = load_model(tmp)
    assert isinstance(model, backend.model_cls)
    assert model._labels == ["a", "b", "c"]


# ── ONNX-specific ───────────────────────────────────────────────


@pytest.mark.parametrize("input_shape", [[1, 3, 224, 224], [None, 3, 224, 224], [224, 224], [None]])
def test_onnx_model_load_shape(input_shape: list[Any]) -> None:
    session = _make_onnx_session(3, input_shape=input_shape)
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)
    assert model._input_size == (224, 224)


def test_onnx_model_load_colon_suffix() -> None:
    session = _make_onnx_session(3)
    session.get_inputs.return_value[0].name = "Image:0"
    with patch("lobe_server.model._ort.InferenceSession", return_value=session), tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(tmp, ["a", "b", "c"])
        model = ONNXImageModel.load(tmp)
    assert model._input_name == "Image"


def test_onnx_model_predict_nchw() -> None:
    session = _make_onnx_session(3, input_shape=[None, 3, 224, 224])
    model = ONNXImageModel(session, ["a", "b", "c"], "Image", (224, 224))
    assert model._is_nchw is True
    result = model.predict(Image.new("RGB", (10, 10)))
    assert result.prediction == "a"


def test_load_model_unicode_path() -> None:
    session = _make_onnx_session(3)
    with (
        patch("lobe_server.model._ort.InferenceSession", return_value=session),
        tempfile.TemporaryDirectory() as tmp,
    ):
        model_dir = Path(tmp) / "моя_папка model test"  # Cyrillic + spaces
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"fake onnx")
        _write_labels_txt(str(model_dir), ["a", "b", "c"])
        model = load_model(str(model_dir))

    assert isinstance(model, ONNXImageModel)
    assert model._labels == ["a", "b", "c"]
