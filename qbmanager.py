#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qBittorrent 自动管理器

功能：
1 规则过滤文件
2 自动重命名文件
3 自动种子重命名
4 自动顶层目录重命名
5 中文字符最多优先作为资源名称
6 规则热加载
7 添加tracker列表
"""

import traceback
import requests
import os
import time
import json
import qbittorrentapi
from loguru import logger

from qb_utils import get_top_folders, File, Torrent, Action, choose_best_name
from qb_utils import build_flatten_plan
from qb_utils import build_rename_plan, split_parent_leaf, unique_name
from qb_utils import join_path, _path_parts
from RuleEngine_utils import RuleEngine

# 配置缓存文件路径和过期时间（单位：秒，这里设置为 1 小时）
TRACKER_CACHE_FILE = "trackers_cache.json"
CACHE_EXPIRE_TIME = 1 * 3600
NEW_TORRENT_THRESHOLD = 10 * 60  # 多少秒内的种子视为“新添加”(此处为10分钟)

# 定义需要更新的下载状态
ACTIVE_STATES = [
    'downloading',  # 正在下载
    'stalledDL',  # 等待下载 (通常是因为没连接上tracker)
    'metaDL',  # 正在获取元数据
    'forcedDL',  # 强制下载
    'allocating',  # 正在分配磁盘空间
    'queuedDL'  # 排队下载
]


def get_external_trackers(
    qb_controller,
    url="https://ngosang.github.io/trackerslist/trackers_all.txt",
):
    """
    获取 Tracker 列表：合并外部 URL 列表 + qB 现有种子 Tracker，并处理缓存

    参数:
        qb_controller: QBController 实例
        url: 外部 Tracker 列表地址
        cache_file: 缓存文件名
        cache_duration: 缓存有效期（秒）
    """
    now = time.time()

    # 1. 尝试从缓存读取
    if os.path.exists(TRACKER_CACHE_FILE):
        cache_time = os.path.getmtime(TRACKER_CACHE_FILE)
        if now - cache_time < CACHE_EXPIRE_TIME:
            try:
                with open(TRACKER_CACHE_FILE, 'r', encoding='utf-8') as f:
                    trackers = [line.strip() for line in f if line.strip()]
                    if trackers:
                        logger.info(f"从缓存加载了 {len(trackers)} 个 Tracker")
                        return trackers
            except Exception as e:
                logger.error(f"读取缓存文件失败: {e}")

    # 2. 缓存失效，开始执行合并逻辑
    logger.info("缓存失效或不存在，开始同步最新 Tracker 列表...")
    all_trackers_set = set()

    # --- A. 获取外部网络 Tracker ---
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        ext_trackers = [
            line.strip() for line in response.text.splitlines()
            if line.strip()
        ]
        for t in ext_trackers:
            if t.startswith(
                ('http://', 'https://', 'udp://', 'ws://', 'wss://')):
                all_trackers_set.add(t)
        logger.info(f"从网络获取了 {len(ext_trackers)} 个 Tracker")
    except Exception as e:
        logger.error(f"从网络获取 Tracker 失败: {e}")

    # --- B. 获取 qBittorrent 现有种子的 Tracker ---
    try:
        qb_controller.connect()
        torrents = qb_controller.client.torrents_info()
        logger.info(f"正在从 {len(torrents)} 个种子中提取现有 Tracker...")

        for torrent in torrents:
            # 注意：get_torrent_trackers 是耗时操作，每个种子都会产生一次请求
            current_trackers = qb_controller.get_torrent_trackers(torrent.hash)
            for t in current_trackers:
                # 过滤掉一些私有种子或无效的 tracker
                if t.startswith(('http', 'udp')):
                    all_trackers_set.add(t)
    except Exception as e:
        logger.error(f"从 qB 种子提取 Tracker 出错: {e}")

    # 3. 结果去重并存入缓存
    final_list = sorted(list(all_trackers_set))

    if final_list:
        try:
            with open(TRACKER_CACHE_FILE, 'w', encoding='utf-8') as f:
                for tracker in final_list:
                    f.write(tracker + '\n')
            logger.info(f"已更新缓存，合并后共 {len(final_list)} 个 Tracker")
        except Exception as e:
            logger.error(f"写入缓存文件失败: {e}")
    else:
        # 如果获取失败且没缓存，尝试返回旧缓存（哪怕过期）
        logger.warning("未能获取到任何 Tracker，尝试使用旧缓存...")
        if os.path.exists(TRACKER_CACHE_FILE):
            with open(TRACKER_CACHE_FILE, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]

    return final_list


CONFIG = {
    "host": "192.168.10.200",
    "port": 8080,
    "username": "ranvane",
    "password": "fjgh1148028",
    "rule_file": "rules.txt",
    "scan_interval": 10,
    "dry_run": False,
    "log_file": "qbmanager.log",
}

# logger.remove()
# logger.add(CONFIG["log_file"], rotation="10 MB", retention=5)
# logger.add(lambda msg: print(msg, end=""))


class CancelDownload(Action):
    """
    取消下载操作类
    继承自Action基类，用于取消特定文件的下载
    """

    def __init__(self, torrent, file_ids):
        """
        初始化取消下载操作

        参数:
            torrent (Torrent): 关联的种子对象
            file_ids (list): 要取消下载的文件ID列表
        """
        self.hash = torrent.hash  # 种子哈希值
        self.ids = file_ids  # 要取消下载的文件ID列表
        self.torrent = torrent  # 关联的种子对象

    def execute(self, client):
        """
        执行取消下载操作
        通过将文件优先级设置为0来取消下载

        参数:
            client: qBittorrent客户端实例
        """
        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(f"[DRY] cancel download {self.ids}")  # 记录将要执行的操作
            return

        # 调用qBittorrent API，将指定文件的下载优先级设置为0（不下载）
        try:
            client.torrents_file_priority(torrent_hash=self.hash,
                                          file_ids=self.ids,
                                          priority=0)
            # 记录实际执行的操作
            logger.info(f"取消下载：{self.torrent.name} -> 共{len(self.ids)}文件，"
                        f"文件ID：{self.ids}")

        except Exception as e:
            logger.error(f"取消下载 {self.ids} 失败，{e}")


class RenameFile(Action):
    """
    重命名文件操作类
    继承自Action基类，用于重命名种子中的文件
    """

    def __init__(self, torrent, old, new):
        """
        初始化重命名文件操作

        参数:
            torrent (Torrent): 关联的种子对象
            old (str): 原始文件路径
            new (str): 新文件路径
        """
        self.torrent = torrent  # 关联的种子对象
        self.hash = torrent.hash  # 种子哈希值

        self.old = old  # 原始文件路径
        self.new = new  # 新文件路径

    def execute(self, client):
        """
        执行重命名文件操作

        参数:
            client: qBittorrent客户端实例
        """
        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(
                f"[DRY] rename file {self.old} -> {self.new}")  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子中的文件
        try:
            if self.old == self.new:
                return
            client.torrents_rename_file(torrent_hash=self.hash,
                                        old_path=self.old,
                                        new_path=self.new)

            # 记录实际执行的操作
            logger.info(
                f"重命名文件 {self.torrent.name} : {self.old} -> {self.new}")
        except Exception as e:
            # 此处必须记录日志：静默吞掉会让“改名没生效”无从排查
            logger.error(f"重命名文件 {self.old} -> {self.new} 失败，{e}")


class RenameTorrent(Action):
    """
    重命名种子操作类
    继承自Action基类，用于重命名整个种子
    """

    def __init__(self, torrent, new_name):
        """
        初始化重命名种子操作

        参数:
            torrent (Torrent): 关联的种子对象
            new_name (str): 新的种子名称
        """
        self.torrent = torrent  # 关联的种子对象
        self.hash = torrent.hash  # 种子哈希值
        self.new_name = new_name  # 新的种子名称

    def execute(self, client):
        """
        执行重命名种子操作

        参数:
            client: qBittorrent客户端实例
        """
        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(
                f"[DRY] rename torrent -> {self.new_name}")  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子
        try:
            client.torrents_rename(self.hash, self.new_name)
            logger.info(f"重命名种子 {self.torrent.name} -> {self.new_name}")
        except Exception as e:
            logger.error(
                f"重命名种子 {self.torrent.name} -> {self.new_name} 失败，{e}")


class RenameFolder(Action):
    """
    重命名文件夹操作类
    继承自Action基类，用于重命名种子中的文件夹
    """

    def __init__(self, torrent, old, new):
        """
        初始化重命名文件夹操作

        参数:
            torrent (Torrent): 关联的种子对象
            old (str): 原始文件夹路径
            new (str): 新文件夹路径
        """
        self.torrent = torrent  # 关联的种子对象
        self.hash = self.torrent.hash  # 种子哈希值
        self.old = old  # 原始文件夹路径
        self.new = new  # 新文件夹路径

    def execute(self, client):
        """
        执行重命名文件夹操作
        
        参数:
            client: qBittorrent客户端实例
        """
        # 检查新名称是否有效（非空）
        if not self.new or not self.new.strip():
            logger.warning(f"无法重命名文件夹 '{self.old}'，新名称为空或仅包含空白字符")
            return

        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(
                f"[DRY] rename folder {self.old} -> {self.new}")  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子中的文件夹
        try:
            client.torrents_rename_folder(torrent_hash=self.hash,
                                          old_path=self.old,
                                          new_path=self.new)
            # 记录实际执行的操作
            logger.info(
                f"重命名文件夹 {self.torrent.name} : {self.old} -> {self.new}")
        except Exception as e:
            logger.error(f"重命名文件夹 {self.old} -> {self.new} 失败，{e}")


class RenameDeepFolders(Action):
    """
    统一重命名操作类（文件 + 每一级目录，含顶级目录）

    为什么重构成“先算计划、再执行”：
        旧实现边算边改，父目录改名后子路径失效，只能靠 remap_path 级联补救；
        这既容易重复应用替换规则，也无法在改名前发现“清洗后重名”的冲突
        （qB 会返回 409，目录重名更会被合并，结构直接错乱）。

    当前执行顺序：
        1. 文件改名：此时目录仍是原名，路径一定有效，且无前缀映射问题；
        2. 目录改名：由深到浅，父目录改名时 qB 会递归带走子目录，
           因此每级的新路径都基于“原父目录”计算即可。
        qB 的 torrents_rename_folder 是递归的，所以“深到浅”比“浅到深”更安全：
        既只改末级名称，又不会在父目录改名后让后续路径失效。

    重名处理：
        计划阶段用 unique_name 生成 “名称_2” 形式避开同目录冲突（并保证后缀不会被规则再次删改）；
        执行阶段若仍收到 409（例如 qB 侧存在计划外条目），重新拉取同目录
        文件列表后再避让一次后重试。
    """

    def __init__(self, torrent, files, engine, top_fallback=None):
        """
        初始化统一重命名操作

        参数:
            torrent (Torrent): 关联的种子对象
            files (list): 该种子的文件对象列表（提供相对路径与优先级）
            engine (RuleEngine): 规则引擎实例
            top_fallback (str, optional): 顶级目录替换为空时的兜底名（通常是 best_name）
        """
        self.torrent = torrent  # 关联的种子对象
        self.hash = torrent.hash  # 种子哈希值
        self.files = files  # 文件对象列表
        self.engine = engine  # 规则引擎
        self.top_fallback = top_fallback  # 顶级目录兜底名

    def _occupied_names(self, client, parent):
        """
        读取某个目录下当前实际占用的名称（小写集合）

        用于 409 冲突后重新避让。⚠️ 必须同时包含**文件与目录**：
        qB 的 files 接口只返回文件，若只统计文件末尾段，
        目录与目录重名时占用集里根本没有该目录名，避让会算出同一个名字，
        重试依旧 409。因此这里把每个文件路径的每一级目录名也登记进来。

        参数:
            client: qBittorrent 客户端
            parent (str): 相对目录路径（顶级用 ""）

        返回:
            set: 该目录下已占用名称的小写集合（文件 + 目录）
        """
        try:
            raw_files = client.torrents_files(torrent_hash=self.hash)
        except Exception:
            return set()  # 读取失败时退回空集合，仍按原计划重试

        used = set()
        for raw in raw_files:
            parts = _path_parts(raw.name)
            # 登记该文件路径上的每一级目录名（i 为目录在 parts 中的下标）
            for i in range(len(parts) - 1):
                dir_parent = "/".join(parts[:i]) if i else ""
                if dir_parent == parent:
                    used.add(parts[i].lower())
            # 登记文件本身的末级名称
            if len(parts) >= 1:
                file_parent = "/".join(parts[:-1])
                if file_parent == parent:
                    used.add(parts[-1].lower())
        return used

    @staticmethod
    def _is_conflict(error):
        """
        判断异常是否为 qB 的重名冲突（HTTP 409）

        Conflict409Error 的文本是 "Conflict"，不含数字 409，
        而某些封装/代理可能只留下状态码，因此两者都匹配（不区分大小写）。

        参数:
            error (Exception): 捕获到的异常

        返回:
            bool: 是冲突类错误返回 True
        """
        text = f"{type(error).__name__} {error}".lower()
        return "409" in text or "conflict" in text

    def _do_rename(self, client, old_path, new_path, is_dir):
        """
        执行一次改名，遇到 409 冲突时重新避让后重试一次

        参数:
            client: qBittorrent 客户端
            old_path (str): 当前真实路径
            new_path (str): 计划的新路径
            is_dir (bool): 是否目录

        返回:
            bool: 改名成功（或因无需改名而跳过）返回 True，失败返回 False
        """
        try:
            if is_dir:
                client.torrents_rename_folder(torrent_hash=self.hash,
                                              old_path=old_path,
                                              new_path=new_path)
            else:
                client.torrents_rename_file(torrent_hash=self.hash,
                                            old_path=old_path,
                                            new_path=new_path)
            return True
        except Exception as e:
            # 仅冲突类错误值得重试；其他错误（路径不存在等）直接判定失败
            if not self._is_conflict(e):
                logger.error(f"重命名{'目录' if is_dir else '文件'} "
                             f"{old_path} -> {new_path} 失败，{e}")
                return False

        # 冲突重试：用 qB 的真实列表避让后改名
        parent, leaf = split_parent_leaf(new_path)
        used = self._occupied_names(client, parent)
        used.discard(split_parent_leaf(old_path)[1].lower())  # 自己不算冲突
        retry_leaf = unique_name(leaf, used, is_dir=is_dir, engine=self.engine)
        if retry_leaf is None:  # 无稳定可用名，放弃本次改名，避免振荡
            logger.warning(f"重命名 {old_path} -> {new_path} 冲突，且无可用避让名，跳过")
            return False
        retry_path = join_path(parent, retry_leaf)

        try:
            if is_dir:
                client.torrents_rename_folder(torrent_hash=self.hash,
                                              old_path=old_path,
                                              new_path=retry_path)
            else:
                client.torrents_rename_file(torrent_hash=self.hash,
                                            old_path=old_path,
                                            new_path=retry_path)
            logger.warning(f"目标重名，已避让：{new_path} -> {retry_path}")
            return True
        except Exception as e:
            logger.error(f"重命名{'目录' if is_dir else '文件'} "
                         f"{old_path} -> {retry_path} 失败，{e}")
            return False

    def execute(self, client):
        """
        执行统一重命名：先文件、后目录（由深到浅）

        参数:
            client (qBittorrent客户端实例)

        返回:
            dict: “旧路径 -> 实际新路径” 的成功改名映射，供日志/后续步骤参考
        """
        plan = build_rename_plan(self.files, self.engine,
                                 top_fallback=self.top_fallback)
        mapping = {}

        if CONFIG["dry_run"]:  # 模拟运行模式：只打印计划，不改动 qB
            for old_path, new_path in plan["files"]:
                logger.info(f"[DRY] rename file {old_path} -> {new_path}")
                mapping[old_path] = new_path
            for old_path, new_path in plan["dirs"]:
                logger.info(f"[DRY] rename dir {old_path} -> {new_path}")
                mapping[old_path] = new_path
            return mapping

        # 1. 文件改名：目录仍为原名，路径有效
        for old_path, new_path in plan["files"]:
            if self._do_rename(client, old_path, new_path, is_dir=False):
                mapping[old_path] = new_path
                logger.info(f"重命名文件 {self.torrent.name} : "
                            f"{old_path} -> {new_path}")

        # 2. 目录改名：由深到浅，父目录改名会递归带走已改好的子目录
        for old_path, new_path in plan["dirs"]:
            if self._do_rename(client, old_path, new_path, is_dir=True):
                mapping[old_path] = new_path
                logger.info(f"重命名目录 {self.torrent.name} : "
                            f"{old_path} -> {new_path}")

        return mapping


class MoveFolder(Action):
    """
    移动文件夹操作类
    继承自Action基类，用于将种子内的深层文件夹移动到顶级文件夹下（扁平化目录）
    """

    def __init__(self, torrent, old, top_folder, new_path=None):
        """
        初始化移动文件夹操作

        参数:
            torrent (Torrent): 关联的种子对象
            old (str): 原始深层目录完整路径（如 "顶级/子目录1/子目录2"）
            top_folder (str): 顶级文件夹名称（用于判断目录是否已在顶级）
            new_path (str, optional): 直接指定目标路径；为空时按“上移一级”计算，
                                      保留旧的单级上移行为以便外部调用
        """
        self.torrent = torrent  # 关联的种子对象
        self.hash = torrent.hash  # 种子哈希值
        self.old = old  # 原始深层目录路径
        self.top_folder = top_folder  # 顶级文件夹名称
        self.new_path = new_path  # 显式目标路径（扁平化计划使用）

    @staticmethod
    def get_moved_path(old):
        """
        计算目录上移一级后的新路径（静态工具方法）

        参数:
            old (str): 原始目录完整路径，如 "顶级/父/末级"

        返回:
            str: 上移一级后的路径 "顶级/末级"；若层级已足够浅（<=2级）则返回旧路径本身
        """
        parts = old.replace("\\", "/").split("/")  # 统一分隔符后切分为各层段

        if len(parts) <= 2:  # 层级不超过两级则无需上提
            return old

        return "/".join(parts[:-2] + [parts[-1]])  # 去掉倒数第二段，实现上移一级

    def execute(self, client):
        """
        执行移动文件夹操作
        将深层目录向上提升一级（让末级目录脱离其直接父目录，移到祖父目录下）
        多次运行（或循环调用）后，目录最终会扁平化到顶级文件夹正下方

        参数:
            client: qBittorrent客户端实例
        """
        # 防御性判断：目录本身就是顶级文件夹时无需移动
        if self.old == self.top_folder:
            logger.debug(f"文件夹 '{self.old}' 已是顶级文件夹，无需移动")
            return

        # 优先使用显式目标路径；否则计算上移一级后的新路径
        new = self.new_path if self.new_path else self.get_moved_path(self.old)

        # 路径未变化说明层级已足够浅（<=2级），无需移动
        if new == self.old:
            logger.debug(f"文件夹 '{self.old}' 层级已足够浅，无需移动")
            return

        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(f"[DRY] move folder {self.old} -> {new}")  # 记录将要执行的操作
            return

        # 调用qBittorrent API，将深层目录上移一级
        try:
            client.torrents_rename_folder(torrent_hash=self.hash,
                                          old_path=self.old,
                                          new_path=new)
            # 记录实际执行的操作
            logger.info(f"移动文件夹 {self.torrent.name} : {self.old} -> {new}")
        except Exception as e:
            logger.error(f"移动文件夹 {self.old} -> {new} 失败，{e}")


class QBController:
    """
    qBittorrent控制器类
    负责连接qBittorrent客户端并执行相关操作
    """

    def __init__(self):
        """
        初始化qBittorrent控制器
        """
        self.client = None  # qBittorrent客户端实例

    def connect(self):
        """
        连接到qBittorrent服务器
        已连接时跳过，避免重复创建Client对象
        """
        if self.client:  # 已连接则跳过，避免重复登录
            return

        # 创建qBittorrent客户端实例
        self.client = qbittorrentapi.Client(
            host=CONFIG["host"],
            port=CONFIG["port"],
            username=CONFIG["username"],
            password=CONFIG["password"],
        )
        logger.info("开始连接qBittorrent服务器....")
        try:
            self.client.auth_log_in()  # 登录到qBittorrent服务器
            logger.info("connected qbittorrent")  # 记录连接成功日志
        except Exception as e:
            logger.error(f"无法连接到qBittorrent服务器，请检查配置，{e}")
            return

    def scan(self):
        """
        扫描当前所有的种子及其文件
        生成器函数，逐个返回种子和其对应的文件列表

        ⚠️ 单个种子取文件失败（路径异常、种子刚被删除等）必须跳过并继续，
        否则生成器抛异常会中断整个 for 循环，导致后续种子全部不处理。
        """
        torrents = self.client.torrents_info()  # 获取所有种子信息

        for t in torrents:  # 遍历所有种子
            torrent = Torrent(t)  # 创建Torrent对象

            try:
                files = self.client.torrents_files(
                    torrent_hash=t.hash)  # 获取种子的所有文件
            except Exception as e:
                # 单个种子读取失败不影响其他种子
                logger.error(f"获取种子 {torrent.name} 文件列表失败，跳过：{e}")
                continue

            yield torrent, files  # 生成种子和文件的元组

    def get_torrent_trackers(self, torrent_hash):
        """
        获取指定种子的tracker列表

        参数:
            torrent_hash (str): 种子的哈希值

        返回:
            list: tracker URL 列表
        """
        try:
            trackers = self.client.torrents_trackers(torrent_hash=torrent_hash)
            tracker_urls = []
            for tracker in trackers:
                if tracker.url and tracker.url not in tracker_urls:
                    tracker_urls.append(tracker.url)
            return tracker_urls
        except Exception as e:
            logger.error(f"获取种子 {torrent_hash} 的tracker失败: {e}")
            return []

    def add_trackers_to_torrent(self, torrent_hash, trackers):
        """
        向指定种子添加tracker
        直接添加，qBittorrent API 会自动忽略已存在的 tracker

        参数:
            torrent_hash (str): 种子的哈希值
            trackers (list): 要添加的tracker URL 列表
        """
        if not trackers:
            return

        try:
            # 直接添加，跳过逐个查询（qB API 自动去重），减少 API 调用
            tracker_string = '\n'.join(trackers)
            self.client.torrents_add_trackers(torrent_hash=torrent_hash,
                                              urls=tracker_string)

            logger.info(f"为种子 {torrent_hash} 添加了 {len(trackers)} 个tracker")

        except Exception as e:
            logger.error(f"向种子 {torrent_hash} 添加tracker失败: {e}")

    def remove_all_trackers_from_torrent(self, torrent_hash):
        """
        从指定种子移除所有tracker

        参数:
            torrent_hash (str): 种子的哈希值
        """
        try:
            # 获取当前种子的tracker列表
            current_trackers = self.get_torrent_trackers(torrent_hash)

            if not current_trackers:
                logger.info(f"种子 {torrent_hash} 没有任何tracker，无需移除")
                return

            # 逐个移除tracker
            for tracker_url in current_trackers:
                try:
                    self.client.torrents_remove_trackers(
                        torrent_hash=torrent_hash, urls=tracker_url)
                except Exception as e:
                    logger.error(f"移除种子 {torrent_hash} 的tracker "
                                 f"{tracker_url} 时出错: {e}")

            logger.info(
                f"已移除种子 {torrent_hash} 的 {len(current_trackers)} 个tracker")

        except Exception as e:
            logger.error(f"获取种子 {torrent_hash} 的tracker列表时出错: {e}")


def update_trackers(qb_controller,
                    new_threshold_seconds=NEW_TORRENT_THRESHOLD):
    """
    只给“正在下载”或“最近new_threshold_seconds时间内添加”的种子更新 tracker

    参数:
        qb_controller (QBController): QBController实例
        new_threshold_seconds (int): 判定为“新添加”的时间范围（秒）
    """
    logger.info("开始增量更新种子 Tracker...")

    # 1. 获取外部 Tracker (直接利用你已有的带缓存函数)
    external_trackers = get_external_trackers(qb_controller)
    if not external_trackers:
        logger.warning("未能获取到任何 Tracker，任务结束")
        return

    # 2. 连接并获取所有种子信息
    qb_controller.connect()
    torrents = qb_controller.client.torrents_info()

    now = time.time()

    updated_count = 0

    # 3. 遍历种子进行逻辑判断
    for torrent in torrents:
        # 条件 A: 是否处于活跃下载状态
        is_active = torrent.state in ACTIVE_STATES

        # 条件 B: 是否为最近添加的种子
        # torrent.added_on 是 Unix 时间戳
        is_new = (now - torrent.added_on) < new_threshold_seconds

        # if is_active: # 只更新活跃下载状态的种子
        if is_new:  # 只更新最近添加的种子
            try:
                # 直接添加 external_trackers
                # qBittorrent API 会自动忽略种子中已存在的 tracker，所以不需要手动去重
                qb_controller.add_trackers_to_torrent(torrent.hash,
                                                      external_trackers)
                updated_count += 1
                logger.debug(
                    f"已更新种子: {torrent.name[:30]}... (状态: {torrent.state})")
            except Exception as e:
                logger.error(f"更新种子 {torrent.hash} 出错: {e}")

    logger.info(
        f"Tracker 更新任务完成：共检查 {len(torrents)} 个种子，实际更新了 {updated_count} 个符合条件的种子。"
    )


def clear_all_trackers(qb_controller):
    """
    清除所有种子的tracker

    参数:
        qb_controller (QBController): QBController实例
    """
    logger.info("开始清除所有种子的tracker....")
    qb_controller.connect()  # 连接到qBittorrent服务器

    # 获取所有种子
    torrents = qb_controller.client.torrents_info()

    # 从每个种子移除所有tracker
    for torrent in torrents:
        try:
            # 从种子移除所有tracker
            qb_controller.remove_all_trackers_from_torrent(torrent.hash)

        except Exception as e:
            logger.error(f"清除种子 {torrent.hash} 的tracker时出错: {e}")


# 在QBController类后面添加额外的空行


class Manager:
    """
    主管理器类
    协调规则引擎和qBittorrent控制器，实现自动化的种子管理功能
    """

    def __init__(self):
        """
        初始化主管理器
        """
        self.engine = RuleEngine(CONFIG["rule_file"])  # 创建规则引擎实例

        self.qb = QBController()  # 创建qBittorrent控制器实例

    def run(self):
        """
        启动管理器主循环
        持续监控和管理种子文件
        """
        self.qb.connect()  # 连接到qBittorrent服务器

        # while True:  # 主循环 # 注释掉主循环，改为手动触发
        #     time.sleep(CONFIG["scan_interval"])  # 等待指定的扫描间隔时间
        try:
            self.engine.load()  # 加载最新规则（热加载）
            logger.info("开始扫描所有种子....")
            for torrent, files in self.qb.scan():  # 扫描所有种子
                # 单个种子出错不能中断整轮扫描（AGENTS.md 设计约定第 5 条）：
                # 例如某个种子路径异常、API 偶发失败，其余种子仍应继续处理
                try:
                    self._process_torrent(torrent, files)
                except Exception:
                    logger.error(f"处理种子 {torrent.name} 失败：\n"
                                 f"{traceback.format_exc()}")
                    continue

        except Exception:  # 捕获所有异常
            logger.error(traceback.format_exc())  # 记录错误堆栈信息

    def _process_torrent(self, torrent, files):
        """
        处理单个种子：规则匹配 → 重命名 → 取消下载 → 扁平化

        参数:
            torrent (Torrent): 种子对象
            files (list): 该种子的文件对象列表（原始快照）
        """
        cancel_ids = []  # 存储需要取消下载的文件ID

        # --------------------规则匹配（只读，不改动任何状态）------------------------
        for f in files:  # 遍历种子中的所有文件
            # 跳过优先级为0的文件（不下载），无需创建 File 对象
            if f.priority == 0:
                continue

            file = File(torrent, f)  # 创建File对象

            matched_rule = self.engine.match(
                file)  # 匹配规则，返回 Rule 对象或 None
            if matched_rule:  # 如果文件匹配规则
                cancel_ids.append(file.id)  # 将文件ID添加到取消列表
                self.engine.debug_match(file,
                                        matched_rule)  # 传入已匹配结果避免二次扫描

        # --------------------计算最佳名称（在目录改名之前完成）------------------------
        # 必须在目录改名之前算，因为 choose_best_name 依赖的是尚未改动的原始路径
        best_name = choose_best_name(self.engine, torrent,
                                     files)  # 选择最佳种子名称

        # --------------------统一重命名（文件 + 目录）------------------------
        # 计划式重命名：先算完整计划（含冲突避让），再先改文件、后改目录（由深到浅）。
        # 不再需要 remap_path 前缀映射，避免重复应用替换规则和路径失效。
        # 顶级目录若被替换规则清空，则用 best_name 兜底（由 build_rename_plan 内部处理）
        RenameDeepFolders(
            torrent, files, self.engine,
            top_fallback=best_name).execute(self.qb.client)

        # --------------------种子重命名------------------------------
        if (best_name and best_name != torrent.name):  # 如果最佳名称
            # 与当前名称不同
            # 执行种子重命名操作
            RenameTorrent(torrent, best_name).execute(self.qb.client)

        # 说明：顶级目录的重命名已由上面的 RenameDeepFolders 统一处理
        # （所有层级都应用 replace 替换规则，顶级目录替换为空时才回退到 best_name），
        # 因此这里不再单独调用 RenameFolder，避免与逐层替换重复/冲突。
        # RenameFolder 类仍保留，便于外部单独调用或将来调整策略。

        # --------------------取消下载------------------------------
        if cancel_ids:  # 如果有需要取消下载的文件
            # 执行取消下载操作
            CancelDownload(torrent, cancel_ids).execute(self.qb.client)

        # --------------------移动深层目录到顶级（扁平化）------------------------------
        # 过滤掉不需要的文件后，把所需文件所在的深层目录直接移到顶级目录下
        # 注意：必须重新获取最新文件列表！前面的重命名/取消下载已经改变了真实路径与优先级，
        # 旧快照会导致路径漂移（404）或误判过滤文件
        try:
            # 重新获取该种子的最新文件列表（反映重命名与取消下载后的真实状态）
            latest_files = self.qb.client.torrents_files(
                torrent_hash=torrent.hash)
        except Exception as e:
            # 获取失败则回退到旧快照，仅影响本次扁平化，不影响其他种子
            logger.error(f"重新获取种子 {torrent.name} 文件列表失败: "
                         f"{str(e)}，扁平化将使用旧快照")
            latest_files = files

        # 单个种子可能包含多个顶级目录（多根种子），逐个处理
        for top_folder in get_top_folders(latest_files):
            # 由深到浅、一步到位的扁平化计划（含目标重名避让）
            # ⚠️ 必须把计划里的 new_dir 传给 MoveFolder：
            #    否则避让名被丢弃，实际仍按“上移一级”算目标，重名时又会撞 409
            for old_dir, new_dir in build_flatten_plan(latest_files,
                                                       top_folder,
                                                       engine=self.engine):
                MoveFolder(torrent, old_dir, top_folder,
                           new_path=new_dir).execute(self.qb.client)


def main():
    """
    主函数
    程序入口点，启动qBittorrent管理器
    """
    manager = Manager()
    manager.run()  # 创建管理器实例并运行主循环

    # 更新所有种子的tracker列表
    # clear_all_trackers(manager.qb) # 清除所有种子的tracker, 涉及到比较耗时，请谨慎使用
    update_trackers(manager.qb)


if __name__ == "__main__":  # 当脚本作为主程序运行时
    # 每分钟运行一次
    # * * * * * /usr/bin/python
    # /vol1/1000/my_programme/qBittorrent-utils/qbmanager.py
    main()  # 调用主函数
