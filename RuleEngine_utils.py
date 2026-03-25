import os
import re
import fnmatch
import traceback

from loguru import logger

from qb_utils import parse_size, sanitize_name, remove_by_match


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
                    if fnmatch.fnmatch(file.name.lower(),
                                       p):  # 先将文件名转换为小写，再使用shell风格通配符匹配文件名
                        logger.debug(f"匹配文件名规则: {file.name}")
                        return True

            if self.ext:  # 如果设置了扩展名匹配条件
                for e in self.ext:  # 遍历所有扩展名
                    if file.ext == e:  # 检查文件扩展名是否匹配
                        logger.debug(f"匹配扩展名规则: {file.name}")
                        return True

            if (self.min_size
                    and file.size < self.min_size):  # 如果设置了最小大小限制且文件小于限制
                logger.debug(f"匹配 min_size 规则: {self.min_size}")
                return True

            if (self.max_size
                    and file.size > self.max_size):  # 如果设置了最大大小限制且文件大于限制
                logger.debug(f"匹配 max_size 规则: {self.max_size}")
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

    def __init__(self, cond, raw=None):
        """
        初始化规则对象

        参数:
            cond (dict): 条件配置字典
            raw (str, optional): 原始规则文本（用于调试），默认值为None
        """
        self.cond = Condition(cond)
        self.raw = raw  # 原始规则文本（用于调试）

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

        with open(self.file, encoding="utf8") as f:  # 以UTF-8编码打开规则文件
            for line in f:  # 逐行读取文件
                line = line.strip()  # 去除首尾空白字符

                if not line or line.startswith("#"):  # 如果是空行或注释行
                    continue  # 跳过

                cond = {}  # 创建条件字典

                parts = line.split(";")  # 以分号分割规则行

                for p in parts:  # 处理每个部分
                    if ":" not in p:  # 如果不包含冒号
                        continue  # 跳过

                    k, v = p.lower().split(":", 1)  # 先将键值对转换为小写，再以冒号分割键值对

                    k = k.strip()  # 去除键的首尾空白字符
                    v = v.strip()  # 去除值的首尾空白字符

                    if k == "replace":  # 如果是替换规则字段
                        self.replaces.append(v)  # 添加到替换规则列表
                        continue

                    if k in ("min_size", "max_size"):  # 如果是大小相关字段
                        v = parse_size(v)  # 解析大小字符串

                    if k == "ext":  # 如果是扩展名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    if k == "filename":  # 如果是文件名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    cond[k] = v  # 添加到条件字典
                    # logger.debug(f"rule: {cond}加入规则列表 ")

                    # 创建规则对象并添加到规则列表，加入原始规则文本
                    # self.rules.append(Rule(cond))
                    self.rules.append(Rule(cond, raw=line))

        logger.info(
            f"共加载 {len(self.rules)} 条取消下载的规则，和 {len(self.replaces)} 条重命名规则"
        )  # 记录已加载的规则数量

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

    def rename(self, file_path: str, is_folder=False) -> str:
        """
        根据通配符替换规则重命名 BT 种子文件路径中的文件名
        只修改文件名，保留目录结构

        参数:
            file_path (str): BT 文件完整路径（可能包含多级目录）
            is_folder (bool, optional): 是否是文件夹名，默认为False
        返回:
            str: 重命名后的完整路径
        """
        if is_folder:  # 如果是文件夹名
            new_name = file_path

        else:  #如果是文件路径
            dir_path, filename = os.path.split(file_path)  # 分离目录和文件名
            name, ext = os.path.splitext(filename)  # 分离文件名和扩展名
            new_name = name

        for pattern in self.replaces:
            new_name = remove_by_match(new_name, pattern)  # 根据通配符模式删除匹配内容

        if is_folder:  # 如果是文件夹名
            new_name = sanitize_name(new_name)
            return new_name  # 直接返回文件夹名

        else:  # 如果是文件路径
            new_name = sanitize_name(new_name) + ext  # 拼回扩展名并清理
            return os.path.join(dir_path, new_name)  # 拼回原目录

    def debug_match(self, file):
        """
        调试规则匹配
        打印匹配到的规则
        
        参数:
            file (File): 要测试匹配的文件对象
        """
        matched = False  # 标记是否有规则匹配

        # 遍历所有规则，检查是否匹配给定文件
        for i, r in enumerate(self.rules, 1):  # 使用enumerate为规则编号（从1开始）
            if r.match(file):  # 检查当前规则是否匹配文件
                logger.info(f"匹配第{i}行的规则（除去注释）: {r.raw}")  # 记录匹配成功的规则编号和原始规则内容
                matched = True  # 设置匹配标记为True

        if not matched:  # 如果没有任何规则匹配
            logger.info("没有任何规则匹配")  # 记录未匹配任何规则的信息


# 创建一个模拟的raw对象，具有File类期望的属性
class MockRaw:

    def __init__(self, name, size):
        self.index = 0  # 假设索引为0
        self.name = name
        self.size = size
        self.priority = 1  # 假设优先级为1（正常下载）


# 创建一个模拟的torrent对象
class MockTorrent:

    def __init__(self):
        self.hash = "mock_hash"
        self.name = "mock_torrent"


if __name__ == "__main__":

    # 创建规则引擎对象
    engine = RuleEngine("rules.txt")
    engine.load()
    #测试文件名替换规则

    new_name = engine.rename(
        "【ai增强】edmosaicedea-567肉欲色女孩喜欢吃大gg跟精液，插入后爽到翻白眼！5p无码性爱影片mia4k60帧增强版/489155.com@【AI增强】EDMosaicEDEA-567肉欲色女孩喜欢吃大GG跟精液，插入后爽到翻白眼！5P无码性爱影片Mia4K60帧增强版.mp4"
    )
    print(new_name)

    # #测试取消下载规则
    # #  创建模拟对象
    # from qb_utils import File
    # raw_obj = MockRaw("Movie.2024.CC.mp4", parse_size("100MB"))
    # torrent_obj = MockTorrent()

    # f = File(torrent_obj, raw_obj)

    # engine.debug_match(f)
