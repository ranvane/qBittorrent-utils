# -*- coding: utf-8 -*-
"""
remove_by_match() 的回归测试

覆盖两条语义：
1. 原有通配符：`*` -> 非贪婪 `.*?`，其余字面量，且是全局替换；
2. 新增正则扩展：pattern 以 `^` 开头时整条按正则处理（用于删除开头数字前缀）。

运行：python3 -m pytest test_remove_by_match.py -q
"""

import pytest

from qb_utils import remove_by_match
from RuleEngine_utils import RuleEngine


def test_wildcard_non_greedy():
    """* 是非贪婪匹配：replace:【*】 只删到最近的 】"""
    assert remove_by_match("【广告】资源名【x】", "【*】") == "资源名"


def test_literal_is_global():
    """字面量规则是全局替换，不锚定位置（旧行为，必须保持）"""
    assert remove_by_match("a17b资源17", "17") == "ab资源"


def test_regex_strips_leading_digits():
    """^ 开头的模式按正则处理：删除开头数字及其后的分隔符"""
    pat = r"^[0-9]+[-_. ]*"
    assert remove_by_match("1754-资源名", pat) == "资源名"
    assert remove_by_match("17 资源名", pat) == "资源名"
    assert remove_by_match("2024.资源名", pat) == "资源名"
    assert remove_by_match("资源名1754-", pat) == "资源名1754-"  # 只删开头


def test_regex_empty_result_is_kept():
    """全数字名会被删空，交给上层空名保护处理，这里只保证不抛异常"""
    assert remove_by_match("1754", r"^[0-9]+[-_. ]*") == ""


def test_invalid_regex_falls_back_to_literal():
    """写坏的正则不能拖垮整轮处理，退回字面量删除"""
    assert remove_by_match("^[0-9 资源", "^[0-9") == " 资源"


def test_engine_applies_regex_rule(tmp_path):
    """规则引擎端到端：rules.txt 里的 ^ 规则能同时作用于目录与文件名"""
    rules = tmp_path / "rules.txt"
    rules.write_text("replace:^[0-9]+[-_. ]*\n", encoding="utf-8")

    engine = RuleEngine(str(rules))
    engine.load()

    assert engine.rename("1754-资源名", is_folder=True) == "资源名"
    assert engine.rename("a/1754-文件.mp4") == "a/文件.mp4"  # rename 只换末级文件名
    assert engine.explain_deep("1754-目录/1754-文件.mp4").result == "目录/文件.mp4"
