# Locale and translation support

## Goal
User-visible messages (console output, error messages, settings.ini comments) in user's language. Logs stay in simple English.

## Scope
- **Translated:** user-mode dashboard strings, error messages shown to user, settings.ini comments, README
- **NOT translated:** log messages (always simple English), code comments (always simple English), internal variable names

## 3 language support

| Language | Locale | Detection |
|----------|--------|-----------|
| English | `en` | Default for unsupported locales |
| Russian | `ru` | `ru_RU`, `ru`, `be`, `uk` |
| Spanish | `es` | `es_ES`, `es_MX`, `es_AR`, `es` |

## Architecture (std lib only)

Use Python's standard `locale` + `gettext` libraries — no custom frameworks.

### Locale detection

```python
import locale

def detect_locale() -> str:
    try:
        lang = locale.getdefaultlocale()[0]
        code = lang.split("_")[0] if lang else "en"
    except Exception:
        code = "en"
    if code not in ("ru", "es", "en"):
        code = "en"
    return code
```

### Translation catalog

Use `gettext.NullTranslations` subclass with embedded dictionaries for each language:

```python
import gettext

_RU = {
    "Failed to load TFLite model: {path}.": "Не удалось загрузить модель: {path}.",
    "settings.ini not found": "settings.ini не найден",
    "Connection error": "Ошибка соединения",
    "Reconnecting in {sec}s...": "Переподключение через {sec}с...",
    "Shutting down...": "Завершение работы...",
}

_ES = {
    "Failed to load TFLite model: {path}.": "Error al cargar el modelo: {path}.",
    "settings.ini not found": "settings.ini no encontrado",
    "Connection error": "Error de conexión",
    "Reconnecting in {sec}s...": "Reconectando en {sec}s...",
    "Shutting down...": "Apagando...",
}

class _LobeTranslations(gettext.NullTranslations):
    def __init__(self, lang: str = "en") -> None:
        super().__init__()
        self._catalog = _RU if lang == "ru" else _ES if lang == "es" else {}

    def gettext(self, message: str) -> str:
        return self._catalog.get(message, message)

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return self.gettext(msgid1 if n == 1 else msgid2)


def setup_locale() -> str:
    code = detect_locale()
    t = _LobeTranslations(code)
    t.install()  # makes _() available as builtin
    return code
```

### Usage

```python
# After setup_locale() in TRIKLobeServer.py:
_("Failed to load TFLite model: {path}.").format(path=str(tflite_path))
```

The `gettext.NullTranslations` base class provides `.install()`, standard `_()`, `ngettext()`, etc.

### Locale override

CLI flag `--lang en|ru|es` overrides auto-detection.

### Implementation order

1. Create `lobe_server/locale.py` with `_LobeTranslations` + `setup_locale()` + `detect_locale()`
2. Call `setup_locale()` in `TRIKLobeServer.py`; add `--lang` CLI flag
3. Replace user-visible strings in `model.py`, `server.py`, `output.py`, `TRIKLobeServer.py`
4. Update settings.ini comments (bilingual)
5. Tests: verify every message ID exists in all 3 locales, verify fallback to English
6. Test: `--lang ru` flag overrides detection

### Files to change

| File | Change |
|------|--------|
| `lobe_server/locale.py` | NEW: `detect_locale()`, `_LobeTranslations`, `setup_locale()` |
| `TRIKLobeServer.py` | Call `setup_locale()`, add `--lang` flag |
| `lobe_server/model.py` | Replace user-facing error messages with `_(...)` |
| `lobe_server/server.py` | Replace user-facing messages with `_(...)` |
| `lobe_server/output.py` | Replace dashboard labels with `_(...)` |
| `settings.ini` | Bilingual comments |
| `tests/test_locale.py` | NEW: verify all IDs in all locales, --lang flag |