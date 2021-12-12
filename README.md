# TRIK Lobe Server

## Установка

Скачайте архив `.zip` с последней версией сервера по [ссылке](https://github.com/khodand/trik-lobe-server/releases/latest).
Распакуйте архив.

В файле `settings.ini` установите значения переменных `SERVER_IP`, `MY_HULL_NUMBER`, `SERVER_PORT` и `MODEL_PATH` cоответственно комментарию.

## Использование с беспроводной камерой или получение изображений по URL
- Переменной `PHOTO_URL` присвоить значение ссылки на snapshot вебкамеры. `PHOTO_URL=http://127.0.0.1:8080/?action=snapshot`.
- Данные для аутентификации, если требуется, присвоить переменным `USERNAME` и `PASSWORD`.

## Использование с камерой TRIK
- Активировать камеру на роботе.
- В `settings.ini` значение параметра `PHOTO_URL` **оставить пустым** `PHOTO_URL=`
- `GET_IMAGES_FROM_ROBOT` присвоить `True` - `GET_IMAGES_FROM_ROBOT=True`

## Использование с камерой ПК
- Значение параметра `PHOTO_URL` **оставить пустым** `PHOTO_URL=`
- `GET_IMAGES_FROM_ROBOT` присвоить `False` - `GET_IMAGES_FROM_ROBOT=False`
- `CAMERA_NUMBER` присвоить номер камеры в ОС Windows (0, 1, 2...) - `CAMERA_NUMBER=0`
