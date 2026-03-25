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

import qbittorrentapi
from loguru import logger

from qb_utils import get_top_folder, File, Torrent, Action, choose_best_name
from RuleEngine_utils import RuleEngine


def get_external_trackers(
    url="https://ngosang.github.io/trackerslist/trackers_best.txt", 
    cache_file=".trackers_cache", 
    cache_duration=3600
):
    """
    从URL获取tracker列表，并使用缓存机制避免频繁请求

    参数:
        url (str): 获取tracker列表的URL
        cache_file (str): 缓存文件路径
        cache_duration (int): 缓存持续时间（秒），默认1小时

    返回:
        list: tracker URL 列表
    """
    # 检查缓存文件是否存在及是否过期
    if os.path.exists(cache_file):
        cache_time = os.path.getmtime(cache_file)
        current_time = time.time()
        
        if current_time - cache_time < cache_duration:
            # 缓存未过期，从缓存文件读取
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    trackers = [line.strip() for line in f if line.strip()]
                    logger.info(f"从缓存加载了 {len(trackers)} 个tracker")
                    return trackers
            except Exception as e:
                logger.error(f"读取缓存文件失败: {e}")
    
    # 缓存不存在或已过期，从网络获取
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # 分割响应内容为行，并过滤空行
        lines = response.text.splitlines()
        trackers = [line.strip() for line in lines if line.strip()]
        
        # 过滤掉无效的tracker URL
        valid_trackers = []
        for tracker in trackers:
            tracker = tracker.strip()
            if tracker.startswith(
                ('http://', 'https://', 'udp://', 'ws://', 'wss://')
            ):
                valid_trackers.append(tracker)
        
        # 保存到缓存文件
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                for tracker in valid_trackers:
                    f.write(tracker + '\n')
            logger.info(f"已更新缓存文件，包含 {len(valid_trackers)} 个tracker")
        except Exception as e:
            logger.error(f"写入缓存文件失败: {e}")
        
        logger.info(f"从网络获取了 {len(valid_trackers)} 个tracker")
        return valid_trackers
    
    except Exception as e:
        logger.error(f"获取tracker列表失败: {e}")
        # 如果网络获取失败，尝试从缓存读取（即使已过期）
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    trackers = [line.strip() for line in f if line.strip()]
                    logger.info(
                        f"网络获取失败，从缓存加载了 {len(trackers)} 个tracker"
                    )
                    return trackers
            except Exception as e2:
                logger.error(f"从缓存读取也失败: {e2}")
        
        return []


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

        self.client.auth_log_in()  # 登录到qBittorrent服务器

        logger.info("connected qbittorrent")  # 记录连接成功日志

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


def update_trackers(qb_controller):
    """
    更新所有种子的tracker列表
    获取外部tracker列表，合并现有tracker，并去重添加到各种子

    参数:
        qb_controller (QBController): QBController实例
    """
    qb_controller.connect()  # 连接到qBittorrent服务器
    
    # 获取外部tracker列表（带缓存）
    external_trackers = get_external_trackers()
    if not external_trackers:
        logger.warning("未能获取到任何外部tracker")
        return

    # 获取所有种子
    torrents = qb_controller.client.torrents_info()
    
    # 获取所有现有tracker并去重
    all_existing_trackers = set()
    for torrent in torrents:
        current_trackers = qb_controller.get_torrent_trackers(torrent.hash)
        all_existing_trackers.update(current_trackers)
    
    # 合并现有tracker和外部tracker并去重
    final_trackers = list(set(list(all_existing_trackers) + external_trackers))
    logger.info(f"Tracker列表长度: {len(final_trackers)}")
    
    # 将合并后的tracker列表添加到每个种子
    for torrent in torrents:
        try:
            # 添加合并后的tracker到种子
            qb_controller.add_trackers_to_torrent(torrent.hash, final_trackers)
            
        except Exception as e:
            logger.error(f"更新种子 {torrent.hash} 的tracker时出错: {e}")


def clear_all_trackers(qb_controller):
    """
    清除所有种子的tracker

    参数:
        qb_controller (QBController): QBController实例
    """
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
    update_trackers(manager.qb)
    # clear_all_trackers(manager.qb)


if __name__ == "__main__":  # 当脚本作为主程序运行时
    # 每分钟运行一次
    # * * * * * /usr/bin/python
    # /vol1/1000/my_programme/qBittorrent-utils/qbmanager.py
    main()  # 调用主函数