import os
import re
import fnmatch
import time
import traceback
import pathlib

import qbittorrentapi
from loguru import logger

from qb_utils import chinese_count, extract_filename_noext, get_top_folder, parse_size, sanitize_name, File, Torrent, Action, choose_best_name


class Condition:
    """
    条件类
    用于定义匹配文件的各种条件，如文件名、扩展名、大小等
    """

    def __init__(self, data):
        """
        初始化条件对象
        
        参数:
            data (dict): 包含条件配置的数据字典
        """
        self.filename = data.get("filename")  # 文件名匹配模式列表
        self.ext = data.get("ext")  # 扩展名匹配列表

        self.min_size = data.get("min_size")  # 最小文件大小限制
        self.max_size = data.get("max_size")  # 最大文件大小限制

    def match(self, file):
        """
        检查文件是否满足当前条件
        
        参数:
            file (File): 要检查的文件对象
            
        返回:
            bool: 如果文件满足任一条件则返回True，否则返回False
        """
        try:
            if self.filename:  # 如果设置了文件名匹配条件
                for p in self.filename:  # 遍历所有文件名匹配模式
                    if fnmatch.fnmatch(file.name, p):  # 使用shell风格通配符匹配文件名
                        return True

            if self.ext:  # 如果设置了扩展名匹配条件
                for e in self.ext:  # 遍历所有扩展名
                    if file.ext == e:  # 检查文件扩展名是否匹配
                        return True

            if self.min_size and file.size < self.min_size:  # 如果设置了最小大小限制且文件小于限制
                return True

            if self.max_size and file.size > self.max_size:  # 如果设置了最大大小限制且文件大于限制
                return True

            return False  # 文件不满足任何条件

        except Exception:  # 捕获所有异常
            logger.error(traceback.format_exc())  # 记录错误堆栈信息
            return False  # 发生异常时返回False


class Rule:
    """
    规则类
    包含一个条件对象，定义了如何匹配文件的规则
    """

    def __init__(self, cond):
        """
        初始化规则对象
        
        参数:
            cond (dict): 条件配置字典
        """
        self.cond = Condition(cond)  # 创建条件对象

    def match(self, file):
        """
        检查文件是否匹配当前规则
        
        参数:
            file (File): 要检查的文件对象
            
        返回:
            bool: 如果文件匹配规则则返回True，否则返回False
        """
        return self.cond.match(file)  # 调用条件对象的match方法


class RuleEngine:
    """
    规则引擎类
    负责加载和管理规则文件，以及执行文件匹配和重命名操作
    支持规则热加载功能
    """

    def __init__(self, rule_file):
        """
        初始化规则引擎
        
        参数:
            rule_file (str): 规则文件路径
        """
        self.file = rule_file  # 规则文件路径

        self.rules = []  # 规则列表

        self.replaces = []  # 替换规则列表

        self.last_mtime = 0  # 上次修改时间戳

    def load(self):
        """
        加载规则文件
        如果文件不存在则创建默认文件，如果文件被修改则重新加载
        """
        if not os.path.exists(self.file):  # 如果规则文件不存在
            with open(self.file, "w", encoding="utf8") as f:  # 创建并写入默认内容
                f.write("# rules\n")

        mtime = os.path.getmtime(self.file)  # 获取文件最后修改时间

        if mtime == self.last_mtime:  # 如果文件未被修改
            return  # 直接返回，无需重新加载

        self.last_mtime = mtime  # 更新最后修改时间

        self.rules.clear()  # 清空现有规则列表
        self.replaces.clear()  # 清空现有替换规则列表

        with open(self.file, encoding="utf8") as f:  # 以UTF-8编码打开规则文件
            for line in f:  # 逐行读取文件
                line = line.strip()  # 去除首尾空白字符

                if not line or line.startswith("#"):  # 如果是空行或注释行
                    continue  # 跳过

                if line.startswith("replace:"):  # 如果是替换规则行
                    self.replaces.append(line.split(":", 1)[1])  # 提取替换模式并添加到列表
                    continue

                cond = {}  # 创建条件字典

                parts = line.split(";")  # 以分号分割规则行

                for p in parts:  # 处理每个部分
                    if ":" not in p:  # 如果不包含冒号
                        continue  # 跳过

                    k, v = p.split(":", 1)  # 以冒号分割键值对

                    k = k.strip()  # 去除键的首尾空白字符
                    v = v.strip()  # 去除值的首尾空白字符

                    if k in ("min_size", "max_size"):  # 如果是大小相关字段
                        v = parse_size(v)  # 解析大小字符串

                    if k == "ext":  # 如果是扩展名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    if k == "filename":  # 如果是文件名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    cond[k] = v  # 添加到条件字典

                self.rules.append(Rule(cond))  # 创建规则对象并添加到规则列表

        logger.info(f"rules loaded: {len(self.rules)}")  # 记录已加载的规则数量

    def match(self, file):
        """
        检查文件是否匹配任何规则
        
        参数:
            file (File): 要检查的文件对象
            
        返回:
            bool: 如果文件匹配任一规则则返回True，否则返回False
        """
        for r in self.rules:  # 遍历所有规则
            if r.match(file):  # 检查文件是否匹配当前规则
                return True  # 如果匹配则立即返回True

        return False  # 所有规则都不匹配则返回False

    def rename(self, name):
        """
        根据替换规则重命名文件名
        
        参数:
            name (str): 原始文件名
            
        返回:
            str: 重命名后的文件名
        """
        new = name  # 初始新名称等于原名称

        for r in self.replaces:  # 遍历所有替换规则
            new = re.sub(r, "", new, flags=re.I)  # 使用正则表达式替换匹配的部分为空字符串（不区分大小写）

        return sanitize_name(new)  # 清理并返回新名称
