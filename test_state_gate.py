# -*- coding: utf-8 -*-
"""
处理状态门控（state.json）的回归测试

覆盖 AGENTS.md 中“指纹门控”的关键行为：
1. 首轮全量处理，次轮全部跳过；
2. 新增种子只处理新增的那个；
3. 种子被删除后状态自动清理；
4. 规则文件变更后全量重扫；
5. 处理失败的种子不记账，下一轮自动重试。

运行：python3 -m pytest test_state_gate.py -q
"""

import json

import pytest

import qbmanager
from qb_utils import Torrent


class FakeRawTorrent:
    """模拟 qbittorrentapi 返回的原始种子对象（只带门控需要的字段）"""

    def __init__(self, hash_, name="t", added_on=100, total_size=1000,
                 state="downloading"):
        self.hash = hash_  # 种子哈希
        self.name = name  # 种子名称（刻意不参与指纹）
        self.added_on = added_on  # 添加时间（参与指纹）
        self.total_size = total_size  # 总大小（参与指纹）
        self.state = state  # 下载状态（刻意不参与指纹）


class FakeClient:
    """模拟 qB 客户端，记录每个种子拉取文件列表的次数"""

    def __init__(self, torrents):
        self.torrents = torrents  # 当前种子列表
        self.files_calls = []  # 记录被拉取文件列表的 hash

    def torrents_info(self):
        """返回当前种子列表"""
        return self.torrents

    def torrents_files(self, torrent_hash):
        """记录一次文件列表请求，返回空列表即可（门控逻辑不依赖文件内容）"""
        self.files_calls.append(torrent_hash)
        return []


class FakeQB(qbmanager.QBController):
    """复用真实 QBController.scan()，只替换连接与客户端"""

    def __init__(self, torrents):
        self.client = FakeClient(torrents)
        self.connected = False

    def connect(self):
        """跳过真实登录"""
        self.connected = True


@pytest.fixture
def env(tmp_path, monkeypatch):
    """
    准备隔离环境：临时规则文件 + 临时状态文件 + 关闭 dry_run

    返回:
        dict: 包含 manager、fake qb、种子列表与路径的上下文
    """
    rules = tmp_path / "rules.txt"
    rules.write_text("", encoding="utf-8")

    monkeypatch.setattr(qbmanager, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setitem(qbmanager.CONFIG, "rule_file", str(rules))
    monkeypatch.setitem(qbmanager.CONFIG, "dry_run", False)

    torrents = [FakeRawTorrent("aaa"), FakeRawTorrent("bbb")]
    manager = qbmanager.Manager()
    manager.qb = FakeQB(torrents)

    processed = []  # 记录每轮实际处理过的 hash

    def fake_process(torrent, files):
        """替换真实处理逻辑，只记账；可按需抛出异常或返回 False 模拟失败"""
        processed.append(torrent.hash)
        if torrent.hash in ctx["fail_hashes"]:
            raise RuntimeError("模拟处理失败")
        if torrent.hash in ctx["incomplete_hashes"]:
            return False  # 改名计划未全部成功
        return True

    manager._process_torrent = fake_process

    ctx = {
        "manager": manager,
        "qb": manager.qb,
        "torrents": torrents,
        "rules": rules,
        "state_file": tmp_path / "state.json",
        "processed": processed,
        "fail_hashes": set(),
        "incomplete_hashes": set(),
    }
    return ctx


def test_first_run_processes_all_then_skips(env):
    """首轮处理全部种子，第二轮一个都不处理（核心收益）"""
    env["manager"].run()
    assert env["processed"] == ["aaa", "bbb"]
    assert sorted(env["qb"].client.files_calls) == ["aaa", "bbb"]

    env["processed"].clear()
    env["qb"].client.files_calls.clear()

    env["manager"].run()
    assert env["processed"] == []  # 第二轮无变化 -> 不处理
    assert env["qb"].client.files_calls == []  # 也不再拉文件列表


def test_new_torrent_only(env):
    """新增种子只处理新增的那个"""
    env["manager"].run()
    env["processed"].clear()
    env["qb"].client.files_calls.clear()

    env["torrents"].append(FakeRawTorrent("ccc"))
    env["manager"].run()

    assert env["processed"] == ["ccc"]
    assert env["qb"].client.files_calls == ["ccc"]


def test_deleted_torrent_state_pruned(env):
    """种子被删除后，状态文件里对应条目被清理"""
    env["manager"].run()

    env["torrents"].remove(env["torrents"][1])  # 删除 bbb
    env["manager"].run()

    state = json.loads(env["state_file"].read_text(encoding="utf-8"))
    assert set(state["torrents"]) == {"aaa"}


def test_rules_change_rescans_all(env):
    """规则文件变更后全量重扫一次"""
    env["manager"].run()
    env["processed"].clear()
    env["qb"].client.files_calls.clear()

    env["rules"].write_text("ext:.url\n", encoding="utf-8")  # 改内容 -> mtime 变化
    env["manager"].run()

    assert env["processed"] == ["aaa", "bbb"]
    assert sorted(env["qb"].client.files_calls) == ["aaa", "bbb"]


def test_failed_torrent_retried(env):
    """处理失败的种子不记账，下一轮自动重试"""
    env["fail_hashes"].add("bbb")
    env["manager"].run()

    state = json.loads(env["state_file"].read_text(encoding="utf-8"))
    assert set(state["torrents"]) == {"aaa"}  # bbb 失败，未记账

    env["fail_hashes"].clear()
    env["processed"].clear()
    env["manager"].run()
    assert env["processed"] == ["bbb"]  # 只重试失败的种子


def test_incomplete_rename_retried(env):
    """改名计划未全部成功（返回 False）也不记账，下一轮重试"""
    env["incomplete_hashes"].add("bbb")
    env["manager"].run()

    state = json.loads(env["state_file"].read_text(encoding="utf-8"))
    assert set(state["torrents"]) == {"aaa"}

    env["incomplete_hashes"].clear()
    env["processed"].clear()
    env["manager"].run()
    assert env["processed"] == ["bbb"]


def test_signature_ignores_name_and_state(env):
    """指纹只看 added_on/total_size：改名和状态变化不应触发重扫"""
    t = FakeRawTorrent("aaa")
    sig = qbmanager._torrent_signature(t)

    t.name = "改过的名字"
    t.state = "uploading"
    assert qbmanager._torrent_signature(t) == sig

    t.total_size = 2000  # 元数据到达 / 文件列表变化
    assert qbmanager._torrent_signature(t) != sig


def test_dry_run_does_not_write_state(env, monkeypatch):
    """DRY 运行不落盘，否则真实运行会被整体跳过"""
    monkeypatch.setitem(qbmanager.CONFIG, "dry_run", True)

    env["manager"].run()
    assert not env["state_file"].exists()


def test_update_trackers_only_new_since_last_run(monkeypatch):
    """Tracker 只加给上次运行之后新增的种子，不再按“最近 10 分钟”重复加"""
    now = 1_000_000.0
    monkeypatch.setattr(qbmanager.time, "time", lambda: now)
    monkeypatch.setattr(qbmanager, "get_external_trackers",
                        lambda qb: ["udp://t:80"])

    class TrackerQB(qbmanager.QBController):
        """只记录被加了 tracker 的种子"""

        def __init__(self):
            self.client = FakeClient([
                FakeRawTorrent("old", added_on=now - 3600),  # 很久以前添加
                FakeRawTorrent("new", added_on=now - 30),  # 上次运行后添加
            ])
            self.touched = []

        def connect(self):
            pass

        def add_trackers_to_torrent(self, torrent_hash, trackers):
            self.touched.append(torrent_hash)

    qb = TrackerQB()
    qbmanager.update_trackers(qb, since_ts=now - 60)

    assert qb.touched == ["new"]  # 只处理新增的那个
