# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# ruff: noqa: RUF001  # intentional Cyrillic in translation strings

"""
Locale and translation support using Python stdlib (gettext + locale).

Usage in application code::  # noqa: D415

    from lobe_server.locale import _
    raise RuntimeError(_("Model file not found: {path}").format(path=...))

The ``_()`` builtin is installed by :func:`setup_locale`. Log messages stay in
simple English — only user-visible strings are translated.
"""

from __future__ import annotations

import gettext
import os

_RU: dict[str, str] = {
    # --- model.py ---
    "Model file specified in signature.json not found: {path}":
        "Файл модели, указанный в signature.json, не найден: {path}",
    "Unknown model format in signature.json filename: {ext}":
        "Неизвестный формат модели в signature.json: {ext}",
    "No model found at {path}. Need a .tflite or .onnx file.":
        "Модель не найдена в {path}. Необходим файл .tflite или .onnx.",
    "labels.txt at {path} is empty.":
        "labels.txt в {path} пустой.",
    "signature.json at {path} is missing 'classes.Label'.":
        "signature.json в {path} не содержит 'classes.Label'.",
    "No labels found at {path}. Provide labels.txt or signature.json with classes.Label.":
        "Метки не найдены в {path}. Укажите labels.txt или signature.json с classes.Label.",
    "ONNX model file not found: {path}":
        "ONNX модель не найдена: {path}",
    "Failed to load ONNX model: {path}. File is corrupt or not a valid ONNX model.":
        "Не удалось загрузить ONNX модель: {path}. Файл повреждён или не является моделью ONNX.",
    "Model returned {n_classes} classes but labels have {n_labels}":
        "Модель вернула {n_classes} классов, но меток {n_labels}",
    "TFLite model file not found: {path}":
        "TFLite модель не найдена: {path}",
    "Failed to load TFLite model: {path}. File is corrupt or not a valid TFLite model.":
        "Не удалось загрузить TFLite модель: {path}. Файл повреждён или не является моделью TFLite.",

    # --- camera.py ---
    "Camera source {source!r} not found or busy. Check CAMERA_SOURCE in settings.ini.":
        "Источник камеры {source!r} не найден или занят. Проверьте CAMERA_SOURCE в settings.ini.",

    # --- config.py ---
    "Invalid {key} in settings.ini: {raw!r}":
        "Неверное значение {key} в settings.ini: {raw!r}",
    "settings.ini not found at {path}":
        "settings.ini не найден: {path}",
    "settings.ini at {path} is missing the [Settings] section.":
        "В settings.ini ({path}) отсутствует раздел [Settings].",
    "ROBOT_PORT out of range (1-{max}): {port}":
        "ROBOT_PORT вне диапазона (1-{max}): {port}",
    "ROBOT_VIDEO_PORT out of range (1-{max}): {port}":
        "ROBOT_VIDEO_PORT вне диапазона (1-{max}): {port}",
    "MY_HULL_NUMBER must be positive: {hull}":
        "MY_HULL_NUMBER должен быть положительным: {hull}",
    "Invalid OUTPUT_MODE in settings.ini: {mode!r}":
        "Неверный OUTPUT_MODE в settings.ini: {mode!r}",
    "settings.ini: {old} is deprecated \u2014 use {new} instead":
        "settings.ini: {old} устарел \u2014 используйте {new}",

    # --- TRIKLobeServer.py ---
    "settings.ini not found":
        "settings.ini не найден",
    "settings.ini has invalid values":
        "settings.ini содержит неверные значения",
    "Failed to create server (check model file)":
        "Не удалось создать сервер (проверьте файл модели)",
    "Press any key to close the window...":
        "Нажмите любую клавишу для закрытия окна...",
    "Shutting down...":
        "Завершение работы...",

    # --- output.py ---
    "  (no data)":
        "  (нет данных)",
    "  camera error":
        "  ошибка камеры",
    "(held {time:.1f}s, {count} detections)":
        "(продолжение {time:.1f}с, {count} обнаружений)",

    # --- server.py (dashboard badges only) ---
    "connecting":
        "подключение",
    "reconnecting":
        "переподключение",
}

_ES: dict[str, str] = {
    # --- model.py ---
    "Model file specified in signature.json not found: {path}":
        "Archivo de modelo especificado en signature.json no encontrado: {path}",
    "Unknown model format in signature.json filename: {ext}":
        "Formato de modelo desconocido en signature.json: {ext}",
    "No model found at {path}. Need a .tflite or .onnx file.":
        "Modelo no encontrado en {path}. Se necesita un archivo .tflite o .onnx.",
    "labels.txt at {path} is empty.":
        "labels.txt en {path} est\u00e1 vac\u00edo.",
    "signature.json at {path} is missing 'classes.Label'.":
        "signature.json en {path} no contiene 'classes.Label'.",
    "No labels found at {path}. Provide labels.txt or signature.json with classes.Label.":
        "Etiquetas no encontradas en {path}. Proporcione labels.txt o signature.json con classes.Label.",
    "ONNX model file not found: {path}":
        "Archivo de modelo ONNX no encontrado: {path}",
    "Failed to load ONNX model: {path}. File is corrupt or not a valid ONNX model.":
        "Error al cargar el modelo ONNX: {path}. El archivo est\u00e1 corrupto o no es un modelo ONNX v\u00e1lido.",
    "Model returned {n_classes} classes but labels have {n_labels}":
        "El modelo devolvi\u00f3 {n_classes} clases pero las etiquetas tienen {n_labels}",
    "TFLite model file not found: {path}":
        "Archivo de modelo TFLite no encontrado: {path}",
    "Failed to load TFLite model: {path}. File is corrupt or not a valid TFLite model.":
        "Error al cargar el modelo TFLite: {path}. El archivo est\u00e1 corrupto o no es un modelo TFLite v\u00e1lido.",

    # --- camera.py ---
    "Camera source {source!r} not found or busy. Check CAMERA_SOURCE in settings.ini.":
        "Fuente de c\u00e1mara {source!r} no encontrada u ocupada. Verifique CAMERA_SOURCE en settings.ini.",

    # --- config.py ---
    "Invalid {key} in settings.ini: {raw!r}":
        "Valor inv\u00e1lido {key} en settings.ini: {raw!r}",
    "settings.ini not found at {path}":
        "settings.ini no encontrado en {path}",
    "settings.ini at {path} is missing the [Settings] section.":
        "settings.ini ({path}) no tiene la secci\u00f3n [Settings].",
    "ROBOT_PORT out of range (1-{max}): {port}":
        "ROBOT_PORT fuera de rango (1-{max}): {port}",
    "ROBOT_VIDEO_PORT out of range (1-{max}): {port}":
        "ROBOT_VIDEO_PORT fuera de rango (1-{max}): {port}",
    "MY_HULL_NUMBER must be positive: {hull}":
        "MY_HULL_NUMBER debe ser positivo: {hull}",
    "Invalid OUTPUT_MODE in settings.ini: {mode!r}":
        "OUTPUT_MODE inv\u00e1lido en settings.ini: {mode!r}",
    "settings.ini: {old} is deprecated \u2014 use {new} instead":
        "settings.ini: {old} est\u00e1 obsoleto \u2014 use {new}",

    # --- TRIKLobeServer.py ---
    "settings.ini not found":
        "settings.ini no encontrado",
    "settings.ini has invalid values":
        "settings.ini tiene valores inv\u00e1lidos",
    "Failed to create server (check model file)":
        "Error al crear el servidor (verifique el archivo del modelo)",
    "Press any key to close the window...":
        "Presione cualquier tecla para cerrar la ventana...",
    "Shutting down...":
        "Apagando...",

    # --- output.py ---
    "  (no data)":
        "  (sin datos)",
    "  camera error":
        "  error de c\u00e1mara",
    "(held {time:.1f}s, {count} detections)":
        "(durante {time:.1f}s, {count} detecciones)",

    # --- server.py (dashboard badges only) ---
    "connecting":
        "conectando",
    "reconnecting":
        "reconectando",
}


class _LobeTranslations(gettext.NullTranslations):
    """Translation catalog using gettext API — English strings as message keys."""

    def __init__(self, lang: str = "en") -> None:
        super().__init__()
        self._catalog = _RU if lang == "ru" else _ES if lang == "es" else {}

    def gettext(self, message: str) -> str:
        return self._catalog.get(message, message)

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return self.gettext(msgid1 if n == 1 else msgid2)


def detect_locale() -> str:
    """Detect system locale from environment, fallback to 'en'."""
    try:
        lang = os.environ.get("LANG") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
        if lang:
            code = lang.split("_")[0].split(".")[0]
            if code in ("ru", "es", "en"):
                return code
    except Exception:  # noqa: BLE001,S110
        pass
    return "en"


def setup_locale(lang: str | None = None) -> str:
    """Install translations — makes _() available as builtin. Returns the effective lang code."""
    code = lang if lang and lang in ("ru", "es") else detect_locale()
    _LobeTranslations(code).install()
    return code
