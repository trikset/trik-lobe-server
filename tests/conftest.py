# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false

"""
Install English identity translations before each test.

Production calls setup_locale() in TRIKLobeServer.main(); pytest doesn't run
that entry point. An autouse fixture (not a session hook) guarantees the
builtin ``_`` exists and stays English even after tests install other
catalogs (test_locale.py calls setup_locale("ru") / setup_locale("es")).
"""

import pytest

from lobe_server.locale import _LobeTranslations


@pytest.fixture(autouse=True)
def _english_translations() -> None:
    _LobeTranslations("en").install()
