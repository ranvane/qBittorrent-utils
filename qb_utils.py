import os
import re
import fnmatch
import time
import traceback
import pathlib

import qbittorrentapi
from loguru import logger


def parse_size(size):
    """
    解析大小字符串并转换为字节数
    
    参数:
        size (str): 包含单位的大小字符串，例如 '10M', '5G', '2K'
        
    返回:
        int: 对应的字节数
    """
    size = size.upper()  # 转换为大写以便统一处理

    if size.endswith("K"):  # 如果单位是KB
        return int(size[:-1]) * 1024  # 移除单位字符并乘以1024得到字节数

    if size.endswith("M"):  # 如果单位是MB
        return int(size[:-1]) * 1024 * 1024  # 移除单位字符并乘以1024*1024得到字节数

    if size.endswith("G"):  # 如果单位是GB
        return int(
            size[:-1]) * 1024 * 1024 * 1024  # 移除单位字符并乘以1024*1024*1024得到字节数

    return int(size)  # 如果没有单位，则直接返回数字部分


def sanitize_name(name):
    """
    清理文件名，移除多余空格并进行标准化处理
    
    参数:
        name (str): 原始文件名
        
    返回:
        str: 清理后的文件名
    """
    name = re.sub(r"\s+", "", name)  # 将所有空白字符序列替换为空字符串（移除所有空格）
    name = name.strip()  # 移除首尾空白字符

    return name


def chinese_count(text):
    """
    统计文本中中文字符的数量
    
    参数:
        text (str): 要统计的文本
        
    返回:
        int: 文本中中文字符的数量
    """
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def extract_filename_noext(name):
    """
    从完整文件路径中提取不带扩展名的文件名
    
    参数:
        name (str): 完整的文件路径
        
    返回:
        str: 不包含扩展名的文件名
    """
    base = os.path.basename(name)  # 获取文件的基本名称（去除路径部分）
    return os.path.splitext(base)[0]  # 分离文件名和扩展名，返回文件名部分（索引0）


def get_top_folder(files):
    """
    从文件列表中获取顶级文件夹名称
    
    参数:
        files: 包含文件对象的列表，每个文件对象有name属性表示文件路径
        
    返回:
        str or None: 如果存在顶级文件夹则返回其名称，否则返回None
    """
    for f in files:
        # 将文件路径分割为各个部分
        parts = pathlib.Path(f.name).parts

        # 如果路径包含多于一个部分（意味着有文件夹结构）
        if len(parts) > 1:
            # 返回第一个部分，即顶级文件夹名称
            return parts[0]

    # 如果没有找到任何有层级结构的文件路径，则返回None
    return None


class File:

    def __init__(self, torrent, raw):
        """
        初始化File对象
        
        参数:
            torrent: 关联的Torrent对象
            raw: 来自qBittorrent API的原始文件数据对象
        """
        self.torrent = torrent  # 关联的种子对象

        self.id = raw.index  # 文件在种子中的索引号
        self.name = raw.name  # 文件名
        self.size = raw.size  # 文件大小（字节）
        self.priority = raw.priority  # 文件下载优先级

        self.ext = os.path.splitext(self.name)[1].lower()  # 文件扩展名（小写）


class Torrent:
    """
    表示一个种子对象
    """

    def __init__(self, raw):
        """
        初始化Torrent对象
        
        参数:
            raw: 来自qBittorrent API的原始种子数据对象
        """
        self.hash = raw.hash  # 种子的哈希值
        self.name = raw.name  # 种子名称


class Action:
    """
    操作基类
    定义了所有操作需要实现的接口
    """

    def execute(self, client):
        """
        执行操作的方法
        子类需要重写此方法来实现具体的操作逻辑
        
        参数:
            client: qBittorrent客户端实例
        """
        pass


def choose_best_name(engine, torrent, files):
    """
    从多种候选名称中选择最佳的种子名称
    优先选择包含最多中文字符的名称
    
    参数:
        engine (RuleEngine): 规则引擎实例
        torrent (Torrent): 种子对象
        files: 文件列表
        
    返回:
        str: 最佳的种子名称
    """
    candidates = []  # 存储候选名称的列表

    # 添加种子本身的名称作为候选
    candidates.append(engine.rename(torrent.name))

    # 获取顶级文件夹名称，如果存在则也作为候选
    folder = get_top_folder(files)
    if folder:
        candidates.append(engine.rename(folder))

    # # 找到最大的文件，并将其文件名（不含扩展名）作为候选
    # largest = max(files, key=lambda x: x.size)  # 找到尺寸最大的文件
    # name = extract_filename_noext(largest.name)  # 提取最大文件的文件名（不含扩展名）
    # candidates.append(engine.rename(name))
    # 找到最大的文件，并将其文件名（不含扩展名）作为候选
    if files:  # 检查文件列表是否非空
        largest = max(files, key=lambda x: x.size)  # 找到尺寸最大的文件
        name = extract_filename_noext(largest.name)  # 提取最大文件的文件名（不含扩展名）
        candidates.append(engine.rename(name))

    best = ""  # 最佳名称
    score = 0  # 最高中文字符数

    # 遍历所有候选名称，选择包含最多中文字符的名称
    for c in candidates:
        c = sanitize_name(c)  # 清理名称

        if not c:  # 如果名称为空则跳过
            continue

        s = chinese_count(c)  # 计算中文字符数

        if s > score:  # 如果当前名称的中文字符数更多
            best = c  # 更新最佳名称
            score = s  # 更新最高分数

    return best  # 返回包含最多中文字符的最佳名称
