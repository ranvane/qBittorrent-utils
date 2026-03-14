import os
import re
import pathlib


def parse_size(size):
    """
    将带单位的大小字符串解析为字节数（bytes）

    支持格式示例：
        100        -> 100 bytes
        10K / 10KB -> 10 * 1024
        5M / 5MB   -> 5 * 1024^2
        2G / 2GB   -> 2 * 1024^3
        1.5G       -> 1.5 * 1024^3

    参数:
        size (str | int | float)
            文件大小字符串或数字。
            可以包含单位 K/M/G/T，也可以不带单位。

    返回:
        int
            对应的字节数

    异常:
        ValueError
            当输入格式非法时抛出
    """

    # 如果已经是数字（例如程序内部直接传入字节数）
    # 直接转换为 int 返回
    if isinstance(size, (int, float)):
        return int(size)

    # 去除字符串前后空白字符并统一为大写
    # 这样可以兼容 "10m", "10MB", " 5g "
    size = size.strip().upper()

    # 使用正则表达式解析：
    # (\d+(?:\.\d+)?)   匹配整数或小数，例如 10 或 1.5
    # ([KMGT]?B?)       匹配单位，例如 K / KB / M / MB
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGT]?B?)", size)

    # 如果正则匹配失败，说明字符串格式非法
    if not match:
        raise ValueError(f"Invalid size format: {size}")

    # 提取数值部分
    number = float(match.group(1))

    # 提取单位部分
    unit = match.group(2)

    # 定义单位对应的字节倍数
    # 使用 1024 体系（文件系统标准）
    unit_table = {
        "": 1,  # 无单位 -> bytes
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
    }

    # 计算字节数
    bytes_size = number * unit_table[unit]

    # 返回整数形式
    return int(bytes_size)


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
    return len(re.findall(r"[\u4e00-\u9fff]", text))


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
        self.name = raw.name.strip()  # 文件名
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
    torrent_name = engine.rename(torrent.name, is_folder=True)
    candidates.append(engine.rename(torrent_name))

    # 获取顶级文件夹名称，如果存在则也作为候选
    folder = get_top_folder(files)

    if folder:
        candidates.append(engine.rename(folder, is_folder=True))

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


def remove_by_match(text: str, pattern: str) -> str:
    """
    根据通配符模式删除文本中的匹配内容
    通配符规则：
        * 表示任意字符（可贪婪匹配）
    
    参数:
        text (str): 原文本
        pattern (str): 通配符模式，例如 "@*", "*@", "【*】"
    
    返回:
        str: 删除匹配后的文本
    """
    # 将通配符 * 转成正则表达式 .*，其他字符转义
    # print(f"使用通配符: {pattern}")
    regex_pattern = ''
    i = 0
    while i < len(pattern):
        if pattern[i] == '*':
            # regex_pattern += '.*'   # 贪婪匹配
            regex_pattern += '.*?'  # 非贪婪匹配
            i += 1
        else:
            regex_pattern += re.escape(pattern[i])
            i += 1

    # 使用 re.sub 删除匹配内容
    return re.sub(regex_pattern, '', text, flags=re.DOTALL)
