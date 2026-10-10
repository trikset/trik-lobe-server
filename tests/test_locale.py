# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0621,W0212  # pytest fixtures; tests inspect privates

import os
import sys
from unittest.mock import patch

from lobe_server.locale import _ES, _RU, _LobeTranslations, detect_locale, setup_locale
from TRIKLobeServer import _parse_args


class TestDetectLocale:
    def test_fallback_to_english(self) -> None:
        with patch.dict(os.environ, {"LANG": ""}, clear=True):
            assert detect_locale() == "en"

    def test_russian_detected(self) -> None:
        with patch.dict(os.environ, {"LANG": "ru_RU.UTF-8"}):
            assert detect_locale() == "ru"

    def test_spanish_detected(self) -> None:
        with patch.dict(os.environ, {"LANG": "es_ES.UTF-8"}):
            assert detect_locale() == "es"

    def test_mexican_spanish_detected(self) -> None:
        with patch.dict(os.environ, {"LANG": "es_MX.UTF-8"}):
            assert detect_locale() == "es"

    def test_german_falls_back_to_english(self) -> None:
        with patch.dict(os.environ, {"LANG": "de_DE.UTF-8"}):
            assert detect_locale() == "en"

    def test_empty_lang_returns_english(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert detect_locale() == "en"

    def test_exception_in_detect_falls_back(self) -> None:
        with patch.object(os.environ, "get", side_effect=AttributeError("mock")):
            assert detect_locale() == "en"


class TestSetupLocale:
    def test_override_explicit(self) -> None:
        code = setup_locale("ru")
        assert code == "ru"

    def test_explicit_spanish(self) -> None:
        code = setup_locale("es")
        assert code == "es"

    def test_invalid_lang_falls_back_to_detected(self) -> None:
        with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
            code = setup_locale("de")
        assert code == "en"

    def test_none_uses_detected(self) -> None:
        with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
            code = setup_locale(None)
        assert code == "en"

    def test_install_makes_translation(self) -> None:
        t = _LobeTranslations("ru")
        t.install()
        result = t.gettext("Press any key to close the window...")
        assert "\u041d\u0430\u0436\u043c\u0438\u0442\u0435" in result


class TestLobeTranslations:
    def test_english_returns_identity(self) -> None:
        t = _LobeTranslations("en")
        assert t.gettext("Hello, World!") == "Hello, World!"

    def test_russian_translates(self) -> None:
        t = _LobeTranslations("ru")
        result = t.gettext("Press any key to close the window...")
        assert "Нажмите" in result
        assert result != "Press any key to close the window..."

    def test_spanish_translates(self) -> None:
        t = _LobeTranslations("es")
        result = t.gettext("Press any key to close the window...")
        assert "Presione" in result
        assert result != "Press any key to close the window..."

    def test_unknown_key_falls_back_to_english(self) -> None:
        t = _LobeTranslations("ru")
        assert t.gettext("Some untranslated string") == "Some untranslated string"

    def test_ngettext_singular(self) -> None:
        t = _LobeTranslations("ru")
        result = t.ngettext("connecting", "reconnecting", 1)
        assert result == t.gettext("connecting")

    def test_ngettext_plural(self) -> None:
        t = _LobeTranslations("ru")
        result = t.ngettext("connecting", "reconnecting", 2)
        assert result == t.gettext("reconnecting")


class TestCatalogCoverage:
    def test_ru_and_es_have_same_keys(self) -> None:
        ru_keys = set(_RU.keys())
        es_keys = set(_ES.keys())
        only_ru = ru_keys - es_keys
        only_es = es_keys - ru_keys
        assert not only_ru, f"Keys in RU but missing in ES: {only_ru}"
        assert not only_es, f"Keys in ES but missing in RU: {only_es}"

    def test_all_keys_and_values_are_nonempty_strings(self) -> None:
        for cat_name, cat in [("_RU", _RU), ("_ES", _ES)]:
            for key, val in cat.items():
                assert isinstance(key, str), f"{cat_name} key is not str: {key!r}"
                assert isinstance(val, str), f"{cat_name}[{key!r}] is not str: {val!r}"
                assert key, f"{cat_name} has empty key"
                assert val, f"{cat_name}[{key!r}] has empty value"


class TestCLI:
    def test_lang_flag_in_parse_args(self) -> None:
        with patch.object(sys, "argv", ["prog", "--lang", "ru"]):
            args = _parse_args()
        assert args.lang == "ru"

    def test_lang_flag_default_none(self) -> None:
        with patch.object(sys, "argv", ["prog"]):
            args = _parse_args()
        assert args.lang is None
