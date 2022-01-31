# TRIK Lobe Server

## Установка
1. Скачайте архив `.zip` с последней версией сервера по [ссылке](https://github.com/khodand/trik-lobe-server/releases/latest).
2. Распакуйте архив.
3. В файле `settings.ini` установите значения переменных `SERVER_IP`, `MY_HULL_NUMBER`, `SERVER_PORT` и `MODEL_PATH` в соответствии с комментариями внутри файла.

## Использование с беспроводной камерой или получение изображений по URL
1. Переменной `PHOTO_URL` присвойте значение ссылки на snapshot вебкамеры: `PHOTO_URL=http://127.0.0.1:8080/?action=snapshot`.
2. Присвойте переменным `USERNAME` и `PASSWORD` данные для аутентификации (если требуется).

## Использование с камерой TRIK
1. Активируйте камеру на роботе.
2. В `settings.ini` значение параметра `PHOTO_URL` **оставьте пустым**: `PHOTO_URL=`.
3. Параметру `GET_IMAGES_FROM_ROBOT` присвойте `True`: `GET_IMAGES_FROM_ROBOT=True`.

## Использование с камерой ПК
1. Значение параметра `PHOTO_URL` **оставьте пустым**: `PHOTO_URL=`.
2. Параметру `GET_IMAGES_FROM_ROBOT` присвойте `False`: `GET_IMAGES_FROM_ROBOT=False`.
3. Параметру `CAMERA_NUMBER` присвойте номер камеры в ОС Windows (0, 1, 2...): `CAMERA_NUMBER=0`.

## Чтение данных с TRIK
Запустите данный скрипт на TRIK с помощью TRIK Studio:
```python
def main():
  while True:
      predict = mailbox.receive(True)
      print(predict)
      script.wait(1000)

if __name__ == '__main__':
  main()
```
