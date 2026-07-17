#!/usr/bin/env python3
"""a3 search/pareto：二维非支配排序。"""
from __future__ import annotations

from typing import Iterable


def is_dominated(candidate: dict, others: Iterable[dict]) -> bool:
    """按 area (min)、arrival (min) 判断是否被支配。缺失值视为 +inf。"""
    a = candidate.get("area", float("inf"))
    ar = candidate.get("arrival", float("inf"))
    for o in others:
        oa = o.get("area", float("inf"))
        oar = o.get("arrival", float("inf"))
        if oa <= a and oar <= ar and (oa < a or oar < ar):
            return True
    return False


def non_dominated_set(candidates: list[dict]) -> list[dict]:
    result = []
    for i, c in enumerate(candidates):
        others = candidates[:i] + candidates[i + 1:]
        if not is_dominated(c, others):
            result.append(c)
    return result
