"""Compact callback data factories (Telegram limit: 64 bytes). One prefix per permission area."""
from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="n"):
    to: str  # home | support | cancel


class St(CallbackData, prefix="s"):   # student area
    a: str
    x: int = 0
    p: int = 0
    n: int = 0   # wizard nonce: buttons of an older wizard can never act on the current one


class Rv(CallbackData, prefix="r"):   # review area (uploader + admin)
    a: str
    x: int = 0
    y: int = 0
    p: int = 0


class Ad(CallbackData, prefix="a"):   # admin area
    a: str
    x: int = 0
    y: int = 0
    p: int = 0
