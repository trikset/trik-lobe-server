# TRIK Lobe Server

[![CI](https://github.com/trikset/trik-lobe-server/actions/workflows/python-app.yml/badge.svg)](https://github.com/trikset/trik-lobe-server/actions/workflows/python-app.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)

Сервер для выполнения инференса ML-моделей (ONNX / TFLite) на ПК и отправки результатов
на робота TRIK или в TRIK Studio по TCP.

## Установка

1. Скачайте `.zip` с последней версией сервера
   [здесь](https://github.com/khodand/trik-lobe-server/releases/latest).
1. Распакуйте архив.
1. Отредактируйте `settings.ini` (см. ниже).

## Настройка (`settings.ini`)

| Параметр | Описание |
|---|---|
| `SERVER_IP` | IP робота или студии. Для студии обычно `127.0.0.1` |
| `MY_HULL_NUMBER` | Борт-номер этого сервера. Выберите незанятый. |
| `SERVER_PORT` | Порт TCP-сервера на роботе/студии. Обычно `8889` |
| `MODEL_PATH` | Путь к папке с моделью. Оставьте пустым, если папка рядом с .exe |
| `PHOTO_URL` | URL snapshot беспроводной камеры (например, `http://192.168.1.100:8080/?action=snapshot`). Оставьте пустым для других режимов |
| `GET_IMAGES_FROM_ROBOT` | `True` — получать кадр с камеры робота. `PHOTO_URL` должно быть пустым |
| `CAMERA_NUMBER` | Номер веб-камеры ПК (0, 1, 2…). Используется только если `PHOTO_URL` пуст и `GET_IMAGES_FROM_ROBOT=False` |
| `USERNAME` / `PASSWORD` | Аутентификация для `PHOTO_URL` (если требуется) |

## Подготовка модели

В папку модели положите `model.onnx` или `model.tflite` (или любой другой `.tflite`/`.onnx` файл).

Labels загружаются в следующем приоритете:

1. **`labels.txt`** — одна строка на класс. **Приоритет выше, чем signature.json**
1. **`signature.json` → `classes.Label`** — если `labels.txt` нет

### labels.txt (рекомендуется)

```
кошка
собака
птица
```

### `signature.json` (если нужно явное имя файла или нет labels.txt)

| Поле | Обязательно | Описание |
|------|-------------|----------|
| `classes.Label` | да (если нет labels.txt) | Список имён классов |
| `filename` | нет | Имя файла модели (если в папке несколько) |

```json
{
    "classes": {"Label": ["кошка", "собака"]},
    "filename": "model.onnx"
}
```

**Microsoft Lobe (легаси)** — полный `signature.json` тоже работает, читается только `classes.Label` и `filename`.

## Использование

### С беспроводной камерой

```
PHOTO_URL=http://192.168.1.100:8080/?action=snapshot
GET_IMAGES_FROM_ROBOT=False
```

### С камерой TRIK

```
PHOTO_URL=
GET_IMAGES_FROM_ROBOT=True
```

Включите камеру на роботе перед запуском.

### С камерой ПК

```
PHOTO_URL=
GET_IMAGES_FROM_ROBOT=False
CAMERA_NUMBER=0
```

## Чтение данных в TRIK

Запустите скрипт на TRIK с помощью TRIK Studio:

```python
def main():
  while True:
      predict = mailbox.receive(True)
      print(predict)
      script.wait(1000)
```

## Поддерживаемые модели

Сервер работает с любой моделью классификации изображений:

- **ONNX** (`*.onnx`) — прямой запуск через onnxruntime.
- **TFLite** (`*.tflite`) — прямой запуск через ai_edge_litert (LiteRT).

Формат авто-определяется по расширению файла. Labels — из `labels.txt` или `signature.json` → `classes.Label` (приоритет у `labels.txt`).

## Сборка из исходников

```bash
uv sync
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

Готовый .exe появится в `dist/`.
