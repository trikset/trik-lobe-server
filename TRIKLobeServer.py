#!/usr/bin/env python3
""" Copyright 2021 Andrei Khodko, CyberTech Labs Ltd.

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License. """
import os
import sys
import asyncio
import socket
import configparser
import requests
from PIL import Image
import cv2
from lobe import ImageModel

print("Starting program")


if os.path.exists("settings.ini"):
    config = configparser.ConfigParser()  # создаём объекта парсера
    config.read("settings.ini", encoding="utf8")  # читаем конфиг
else:
    print("settings.ini not found")
    print("Press any key to close the window...")
    input()
    exit(0)


# IP робота или студии. Для студии обычно использовать SERVER_IP = '127.0.0.1'
SERVER_IP = config["Settings"]["SERVER_IP"]
# Борт номер для этого лобе сервера. Выберите не занятый роботами.
MY_HULL_NUMBER = int(config["Settings"]["MY_HULL_NUMBER"])
# Порт на котором слушает робот сервер или студия. Обычно это 8889
SERVER_PORT = int(config["Settings"]["SERVER_PORT"])

# Путь к директории обученной модели Lobe. Работает с TFLite
# По умолчанию ищет в директории этого скрипта.
# Модель это файлы signature.json и например saved_model.tflite. Если хотите прямой указать путь к модели то,
# указывайте путь к папке содержайщей эти файлы, например MODEL_PATH = 'path/to/exported/model'
if config["Settings"]["MODEL_PATH"] == "":
    if getattr(sys, 'frozen', False):
        MODEL_PATH = os.path.dirname(sys.executable)
    else:
        MODEL_PATH = os.path.dirname(os.path.abspath(__file__))
else:
    MODEL_PATH = config["Settings"]["MODEL_PATH"]

print(MODEL_PATH)
# Установить True если хотим использовать изображение с камеры ТРИК (нужно запустить mjpg-encoder)
# Установить False если хотим использовать изображение с вебкамеры компьютера
GET_IMAGES_FROM_ROBOT = config["Settings"]["GET_IMAGES_FROM_ROBOT"].lower() == "true"

PHOTO_URL = config["Settings"]["PHOTO_URL"]
# Номер камеры в ОС Windows. Разные значения активирует разные подключенные камеры (0, 1, 2...)
CAMERA_NUMBER = int(config["Settings"]["CAMERA_NUMBER"])

KEEPALIVE_TIMER = 5

"""
Простой скрипт для робота или студии. 
while True:
      predict = mailbox.receive(True)
      print(predict)
      script.wait(1000)
"""


try:
    print("Loading lobe model...")
    model = ImageModel.load(MODEL_PATH)
    if not GET_IMAGES_FROM_ROBOT or PHOTO_URL == "":
        CAMERA = cv2.VideoCapture(CAMERA_NUMBER)

    ROBOT_PHOTO_URL = 'http://' + SERVER_IP + ':8080/?action=snapshot'
except Exception as e:
    print(e)
    print("Press any key to close the window...")
    input()
    exit(0)


async def send(message, sock):
    try:
        byte_message = formatted_data_in_bytes(message)
        print("Send:", byte_message)
        async with asyncio.Lock():
            sock.send(byte_message)
        await asyncio.sleep(0.2)
    except ConnectionResetError:
        pass


async def send_message(message: str, sock):
    await send('data:' + message, sock)


def formatted_data_in_bytes(msg: str) -> bytes:
    return bytes(str(len(msg)) + ":" + msg, encoding='UTF-8')


def predict():
    if PHOTO_URL != "":
        im = Image.open(requests.get(PHOTO_URL
                                     , stream=True
                                     , auth=(config["Settings"]["USERNAME"], config["Settings"]["PASSWORD"])).raw)

        return model.predict(im).prediction
    elif GET_IMAGES_FROM_ROBOT:
        return model.predict_from_url(ROBOT_PHOTO_URL).prediction
    else:
        ret, frame = CAMERA.read()
        if not ret:
            return "-1"

        color_converted = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return model.predict(Image.fromarray(color_converted)).prediction


async def send_keepalive(sock):
    while True:
        await send('keepalive', sock)
        await asyncio.sleep(KEEPALIVE_TIMER)


async def send_prediction(sock):
    while True:
        await send_message(predict(), sock)


async def read_data(sock, my_loop):
    data = ""
    while data.find("9:data:quit") == -1:
        await asyncio.sleep(0.2)
        try:
            data = (await my_loop.sock_recv(sock, 255)).decode("utf-8")
        except ConnectionResetError:
            pass

        if data:
            print("Received:", data)

    sock.close()
    my_loop.stop()
    CAMERA.release()


def main():
    loop = asyncio.get_event_loop()
    server = socket.socket()
    try:
        print("Trying to connect to a server")
        server.connect((SERVER_IP, SERVER_PORT))

        ip, port = server.getsockname()
        asyncio.ensure_future(send('register:{}:{}'.format(port, MY_HULL_NUMBER), server))
        asyncio.ensure_future(send('self:{}'.format(MY_HULL_NUMBER), server))

        asyncio.ensure_future(send_keepalive(server))
        asyncio.ensure_future(send_prediction(server))
        asyncio.ensure_future(read_data(server, loop))

        loop.run_forever()
    except Exception as e:
        print(e)
        print("Connection was closed.")
    finally:
        server.close()
        loop.stop()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(e)
    finally:
        print("Press any key to close the window...")
        input()
        exit(0)
