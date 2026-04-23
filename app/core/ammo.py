# -*- coding: utf-8 -*-
"""弹药计数器 — 全局消耗追踪"""

_ammo_counters = {"text": 0, "image": 0, "speech": 0, "music": 0}


def consume_ammo(key: str, amount: int = 1) -> None:
    """消耗弹药。key: text/image/speech/music"""
    if key in _ammo_counters and amount > 0:
        _ammo_counters[key] += amount


def get_ammo() -> dict:
    """返回当前弹药消耗快照"""
    return dict(_ammo_counters)
