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
"""

import traceback

import qbittorrentapi
from loguru import logger

from qb_utils import get_top_folder, File, Torrent, Action, choose_best_name
from RuleEngine_utils import RuleEngine

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
        client.torrents_file_priority(
            torrent_hash=self.hash, file_ids=self.ids, priority=0
        )
        # 记录实际执行的操作
        logger.info(f"{self.torrent.name} 取消下载 {self.ids}")


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
                f"[DRY] rename file {self.old} -> {self.new}"
            )  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子中的文件
        client.torrents_rename_file(
            torrent_hash=self.hash, old_path=self.old, new_path=self.new
        )
        # 记录实际执行的操作
        logger.info(f"重命名文件 {self.torrent.name} : {self.old} -> {self.new}")


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
                f"[DRY] rename torrent -> {self.new_name}"
            )  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子
        client.torrents_rename(self.hash, self.new_name)
        logger.info(f"重命名种子 {self.torrent.name} -> {self.new_name}")


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
        if CONFIG["dry_run"]:  # 如果是模拟运行模式
            logger.info(
                f"[DRY] rename folder {self.old} -> {self.new}"
            )  # 记录将要执行的操作
            return

        # 调用qBittorrent API，重命名种子中的文件夹
        client.torrents_rename_folder(
            torrent_hash=self.hash, old_path=self.old, new_path=self.new
        )
        # 记录实际执行的操作
        logger.info(f"重命名文件夹 {self.torrent.name} : {self.old} -> {self.new}")


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
                torrent_hash=t.hash
            )  # 获取种子的所有文件

            yield torrent, files  # 生成种子和文件的元组


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

                    if self.engine.match(file):  # 如果文件匹配规则
                        cancel_ids.append(file.id)  # 将文件ID添加到取消列表

                    new = self.engine.rename(file.name)  # 获取重命名后的文件名

                    if new != file.name:  # 如果重命名后名称发生变化
                        # 执行文件重命名操作
                        RenameFile(torrent, file.name, new).execute(self.qb.client)

                if cancel_ids:  # 如果有需要取消下载的文件
                    # 执行取消下载操作
                    CancelDownload(torrent, cancel_ids).execute(self.qb.client)

                best_name = choose_best_name(
                    self.engine, torrent, files
                )  # 选择最佳种子名称

                if (
                    best_name and best_name != torrent.name
                ):  # 如果最佳名称与当前名称不同
                    # 执行种子重命名操作
                    RenameTorrent(torrent, best_name).execute(self.qb.client)

                folder = get_top_folder(files)  # 获取顶级文件夹名称

                if folder and folder != best_name:  # 如果顶级文件夹存在且与最佳名称不同
                    # 执行文件夹重命名操作
                    RenameFolder(torrent, folder, best_name).execute(self.qb.client)

        except Exception:  # 捕获所有异常
            logger.error(traceback.format_exc())  # 记录错误堆栈信息


def main():
    """
    主函数
    程序入口点，启动qBittorrent管理器
    """
    logger.info("QB Manager started")  # 记录程序启动日志
    Manager().run()  # 创建管理器实例并运行主循环


if __name__ == "__main__":  # 当脚本作为主程序运行时
    # 每分钟运行一次
    # * * * * * /usr/bin/python  /vol1/1000/my_programme/qBittorrent-utils/qbmanager.py
    main()  # 调用主函数
