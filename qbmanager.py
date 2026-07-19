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

from qb_utils import get_top_folder, File, Torrent, Action, choose_best_name
from RuleEngine_utils import RuleEngine



# 配置缓存文件路径和过期时间（单位：秒，这里设置为 1 小时）
TRACKER_CACHE_FILE = "trackers_cache.json"
CACHE_EXPIRE_TIME = 1 * 3600 
NEW_TORRENT_THRESHOLD = 10 * 60  # 多少秒内的种子视为“新添加”(此处为10分钟)

# 定义需要更新的下载状态
ACTIVE_STATES = [
    'downloading',   # 正在下载
    'stalledDL',     # 等待下载 (通常是因为没连接上tracker)
    'metaDL',        # 正在获取元数据
    'forcedDL',      # 强制下载
    'allocating',    # 正在分配磁盘空间
    'queuedDL'       # 排队下载
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
        ext_trackers = [line.strip() for line in response.text.splitlines() if line.strip()]
        for t in ext_trackers:
            if t.startswith(('http://', 'https://', 'udp://', 'ws://', 'wss://')):
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
            logger.info(
                f"取消下载：{self.torrent.name} -> 共{len(self.ids)}文件，"
                f"文件ID：{self.ids}"
            )

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
            client.torrents_rename_file(torrent_hash=self.hash,
                                        old_path=self.old,
                                        new_path=self.new)

            # 记录实际执行的操作
            logger.info(
                f"重命名文件 {self.torrent.name} : {self.old} -> {self.new}")
        except Exception as e:
            logger.error(f"重命名文件 {self.old} -> {self.new} 失败，{e}")
            return


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
        """
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
        """
        torrents = self.client.torrents_info()  # 获取所有种子信息

        for t in torrents:  # 遍历所有种子
            torrent = Torrent(t)  # 创建Torrent对象

            files = self.client.torrents_files(
                torrent_hash=t.hash)  # 获取种子的所有文件

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

        参数:
            torrent_hash (str): 种子的哈希值
            trackers (list): 要添加的tracker URL 列表
        """
        if not trackers:
            return

        try:
            # 获取当前种子的tracker列表
            current_trackers = self.get_torrent_trackers(torrent_hash)
            
            # 过滤掉已经存在的tracker
            new_trackers = [t for t in trackers if t not in current_trackers]
            
            if not new_trackers:
                logger.info(f"种子 {torrent_hash} 已经拥有所有tracker，无需添加")
                return
            
            # 添加新tracker
            tracker_string = '\n'.join(new_trackers)
            self.client.torrents_add_trackers(
                torrent_hash=torrent_hash,
                urls=tracker_string
            )
            
            logger.info(
                 f"为种子 {torrent_hash} 添加了 {len(new_trackers)} 个新tracker"
             )
            
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
                        torrent_hash=torrent_hash,
                        urls=tracker_url
                    )
                except Exception as e:
                    logger.error(
                        f"移除种子 {torrent_hash} 的tracker "
                        f"{tracker_url} 时出错: {e}"
                    )
            
            logger.info(
                f"已移除种子 {torrent_hash} 的 {len(current_trackers)} 个tracker"
            )
            
        except Exception as e:
            logger.error(f"获取种子 {torrent_hash} 的tracker列表时出错: {e}")



def update_trackers(qb_controller, new_threshold_seconds=NEW_TORRENT_THRESHOLD):
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
        if is_new: # 只更新最近添加的种子
            try:
                # 直接添加 external_trackers
                # qBittorrent API 会自动忽略种子中已存在的 tracker，所以不需要手动去重
                qb_controller.add_trackers_to_torrent(torrent.hash, external_trackers)
                updated_count += 1
                logger.debug(f"已更新种子: {torrent.name[:30]}... (状态: {torrent.state})")
            except Exception as e:
                logger.error(f"更新种子 {torrent.hash} 出错: {e}")

    logger.info(f"Tracker 更新任务完成：共检查 {len(torrents)} 个种子，实际更新了 {updated_count} 个符合条件的种子。")


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
                cancel_ids = []  # 存储需要取消下载的文件ID

                for f in files:  # 遍历种子中的所有文件
                    file = File(torrent, f)  # 创建File对象

                    if file.priority == 0:  # 如果文件优先级为0（不下载）
                        continue  # 跳过
                    # --------------------文件重命名操作------------------------------
                    new = self.engine.rename(file.name)  # 获取重命名后的文件名
                    if new != file.name:  # 如果重命名后名称发生变化
                        # 执行文件重命名操作
                        RenameFile(torrent, file.name,
                                   new).execute(self.qb.client)

                    if self.engine.match(file):  # 如果文件匹配规则
                        cancel_ids.append(file.id)  # 将文件ID添加到取消列表

                # --------------------种子重命名------------------------------
                best_name = choose_best_name(self.engine, torrent,
                                             files)  # 选择最佳种子名称

                if (best_name and best_name != torrent.name):  # 如果最佳名称
                    # 与当前名称不同
                    # 执行种子重命名操作
                    RenameTorrent(torrent, best_name).execute(self.qb.client)

                # --------------------重命名文件夹------------------------------
                folder = get_top_folder(files)  # 获取顶级文件夹名称
                if folder:  # 先检查顶级文件夹是否存在（基础前提）
                    # 检查最佳名称是否有效（非空、非空白字符）
                    if not best_name or best_name.strip() == "":
                        pass
                    elif folder == best_name:
                        pass
                    else:
                        # 所有条件满足，执行重命名
                        try:
                            RenameFolder(torrent, folder,
                                         best_name).execute(self.qb.client)
                            logger.info(
                                f"[RenameFolder]文件夹重命名成功："
                                f"{folder} -> {best_name}"
                            )
                        except Exception as e:
                            # 捕获重命名执行过程中的异常，增强容错性
                            logger.error(
                                f"[RenameFolder]文件夹重命名执行失败："
                                f"{folder} -> {best_name}，错误：{str(e)}"
                            )
                else:
                    logger.info(
                        f"[RenameFolder]文件夹重命名失败：未找到顶级文件夹"
                        f"（最佳名称：{best_name or '空'}）"
                    )
                # --------------------取消下载------------------------------
                if cancel_ids:  # 如果有需要取消下载的文件
                    # 执行取消下载操作
                    CancelDownload(torrent, cancel_ids).execute(self.qb.client)

        except Exception:  # 捕获所有异常
            logger.error(traceback.format_exc())  # 记录错误堆栈信息


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