import os
import re
import fnmatch
import traceback
from loguru import logger

from qb_utils import parse_size, sanitize_name, remove_by_match, File

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

        # 预编译文件名通配符模式为正则表达式，避免每次匹配时重复编译
        self._compiled_filename = []
        self.last_match = None  # 最近一次 match 命中的具体条件描述（如 filename:*xx*）
        if self.filename:
            for p in self.filename:
                try:
                    # fnmatch.translate 将 shell 通配符转为正则（如 *.mp4 → (?s:.*\.mp4)\Z）
                    self._compiled_filename.append(re.compile(fnmatch.translate(p)))
                except re.error:
                    # 极少数非法模式降级为原始字符串匹配
                    self._compiled_filename.append(None)

    def match(self, file):
        """
        检查文件是否满足当前条件

        参数:
            file (File): 要检查的文件对象

        返回:
            bool: 如果文件满足任一条件则返回True，否则返回False
        """
        try:
            if self._compiled_filename:  # 使用预编译的正则进行文件名匹配
                fname_lower = file.name.lower()
                for compiled, pat in zip(self._compiled_filename, self.filename):
                    if compiled and compiled.match(fname_lower):
                        self.last_match = f"filename:{pat}"  # 记录命中的文件名模式
                        return True

            if self.ext:  # 如果设置了扩展名匹配条件
                for e in self.ext:  # 遍历所有扩展名
                    if file.ext == e:  # 检查文件扩展名是否匹配
                        self.last_match = f"ext:{e}"  # 记录命中的扩展名
                        return True

            if (self.min_size
                    and file.size < self.min_size):  # 如果设置了最小大小限制且文件小于限制
                self.last_match = f"min_size:{self.min_size}"  # 记录命中的最小大小条件
                return True

            if (self.max_size
                    and file.size > self.max_size):  # 如果设置了最大大小限制且文件大于限制
                self.last_match = f"max_size:{self.max_size}"  # 记录命中的最大大小条件
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

    def __init__(self, cond, raw=None, text=None, line_no=0):
        """
        初始化规则对象

        参数:
            cond (dict): 条件配置字典
            raw (str, optional): 原始规则整行文本（用于调试），默认值为None
            text (str, optional): 该条件在规则行中的原始片段（如 "filename:*萝莉岛*"）
            line_no (int, optional): 该规则在 rules.txt 中的行号（从 1 开始）
        """
        self.cond = Condition(cond)
        self.raw = raw  # 原始规则整行文本（用于调试）
        self.text = text  # 该条件的原始片段（用于报告具体命中的规则名称）
        self.line_no = line_no  # 所在行号
        self.last_match = None  # 最近一次 match 命中的具体条件描述

    def match(self, file):
        """
        检查文件是否匹配当前规则

        参数:
            file (File): 要检查的文件对象

        返回:
            Rule or None: 匹配成功返回自身，否则返回None
        """
        if self.cond.match(file):  # 调用条件对象的match方法
            self.last_match = self.cond.last_match  # 透传命中的具体条件描述
            return self  # 匹配成功返回自身（含 raw 等信息）
        return None


class RenameStep:
    """
    单条替换规则的命中记录
    用于向使用者解释“这一步是哪个规则把字符串改成了什么样”
    """

    def __init__(self, index, total, pattern, before, after, level=None):
        """
        初始化命中记录

        参数:
            index (int): 该规则在 replaces 列表中的序号（从 1 开始）
            total (int): 替换规则总数
            pattern (str): 命中的通配符规则原文
            before (str): 应用该规则之前的字符串
            after (str): 应用该规则之后的字符串
            level (str, optional): 该步骤所属的路径层级（逐级模式用），单级模式为 None
        """
        self.index = index  # 规则序号
        self.total = total  # 规则总数
        self.pattern = pattern  # 命中的规则原文
        self.before = before  # 替换前的字符串
        self.after = after  # 替换后的字符串
        self.level = level  # 所属层级路径（逐级模式用）

    def to_dict(self):
        """
        转为普通字典，方便打印或序列化

        返回:
            dict: 包含序号、规则、替换前后字符串的字典
        """
        return {
            "index": self.index,
            "total": self.total,
            "pattern": self.pattern,
            "before": self.before,
            "after": self.after,
            "level": self.level,
        }

    def __str__(self):
        """
        格式化为单行可读文本

        返回:
            str: 形如 “第1/16条 replace:【*】 : 旧 -> 新” 的文本
        """
        return (f"第{self.index}/{self.total}条  {self.pattern}  :  "
                f"{self.before!r} -> {self.after!r}")


class RenameResult:
    """
    重命名解释结果
    记录原始字符串、最终字符串，以及过程中每一条被命中的替换规则
    """

    def __init__(self, original, result, steps, is_folder=False, dir_part="", mode="rename"):
        """
        初始化解释结果

        参数:
            original (str): 用户传入的原始字符串
            result (str): 处理完成后的最终字符串
            steps (list[ReplaceStep]): 命中的规则列表（未命中任何规则时为空列表）
            is_folder (bool): 是否按“文件夹名”模式处理
            dir_part (str): 文件路径模式下未被处理的目录部分
            mode (str): 报告模式，"rename" 为重命名试算，"cancel" 为取消下载试算
        """
        self.original = original  # 原始字符串
        self.result = result  # 最终字符串
        self.steps = steps  # 命中的规则列表
        self.is_folder = is_folder  # 是否为文件夹模式
        self.dir_part = dir_part  # 未参与替换的目录部分
        self.mode = mode  # 报告模式

    @property
    def changed(self):
        """
        本次处理是否真的产生了变化

        返回:
            bool: 原始字符串与最终字符串不同则返回 True
        """
        return self.original != self.result

    def to_dict(self):
        """
        转为普通字典，方便打印或 JSON 序列化

        返回:
            dict: 完整解释结果的字典
        """
        return {
            "original": self.original,
            "result": self.result,
            "changed": self.changed,
            "mode": self.mode,
            "is_folder": self.is_folder,
            "dir_part": self.dir_part,
            "steps": [s.to_dict() for s in self.steps],
        }

    def __str__(self):
        """
        格式化为多行可读报告

        返回:
            str: 包含原始值、逐步命中规则、最终结果的报告文本
        """
        lines = []  # 报告行集合
        lines.append(f"原始字符串 : {self.original}")  # 展示原始字符串

        # 文件路径模式下，额外提示“目录部分不参与替换”这一关键事实
        # 这是最容易让人误以为 replace 规则失效的原因
        if not self.is_folder and self.dir_part:
            lines.append(f"目录部分   : {self.dir_part}  <-- 目录不参与替换规则")
            lines.append(f"文件名     : {self.result}")

        if self.steps:  # 有规则被命中
            lines.append("-" * 60)  # 分隔线
            # 取消下载模式下命中的不是“替换规则”，改用“取消下载规则”措辞
            label = "取消下载规则" if self.mode == "cancel" else "替换规则"
            lines.append(f"命中 {len(self.steps)} 条{label}：")  # 命中数量

            if self.mode == "deep":  # 逐级模式：按层级分组展示，直观看出哪一级目录被改
                last_level = object()  # 哨兵对象，保证首个 level 一定触发分组
                for s in self.steps:  # 逐条输出
                    if s.level != last_level:  # 进入新层级
                        last_level = s.level  # 记录当前层级
                        lines.append(f"  [层级] {s.level}")  # 输出层级标题
                    lines.append(f"    第{s.index}/{s.total}条  {s.pattern}  :  "
                                 f"{s.before!r} -> {s.after!r}")  # 缩进显示规则明细
            else:  # 单级模式：平铺显示
                for s in self.steps:  # 逐条输出命中详情
                    lines.append(f"  {s}")  # 缩进显示每条规则

        lines.append("-" * 60)  # 分隔线
        lines.append(f"最终结果   : {self.result}")  # 最终字符串

        if self.mode == "cancel":  # 取消下载模式：用“判定”措辞，避免出现“是否变化”这种无意义表述
            lines.append(f"命中条数   : {len(self.steps)}")  # 命中的规则条数
        else:  # 重命名模式：提示字符串是否发生变化
            lines.append(f"是否变化   : {'是' if self.changed else '否（无规则命中）'}")  # 变化标记

        return "\n".join(lines)  # 拼接为完整报告


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
        self.file = os.path.join(BASE_DIR, rule_file)  # 规则文件路径

        self.rules = []  # 规则列表

        self.replaces = []  # 替换规则列表
        self.replace_lines = {}  # 替换规则值 -> 其在 rules.txt 中的行号

        self.last_mtime = 0  # 上次修改时间戳

    def load(self):
        """
        加载规则文件
        如果文件不存在则创建默认文件，如果文件被修改则重新加载
        """
        logger.info(f"加载规则文件: {os.path.abspath(self.file)}")
        if not os.path.exists(self.file):  # 如果规则文件不存在
            with open(self.file, "w", encoding="utf8") as f:  # 创建并写入默认内容
                f.write('''#******************规则说明***************************
# 匹配以下条件的文件将被取消下载（不下载）
# 
# max_size:X  - 取消下载大小大于X的文件（如max_size:10M表示取消下载大于10MB的文件）
# min_size:X  - 取消下载大小小于X的文件（如min_size:10M表示取消下载小于10MB的文件）
# filename:X  - 取消下载文件名匹配模式X的文件（支持通配符，如filename:*.txt）
# ext:X       - 取消下载指定扩展名的文件（如ext:.mp4表示取消下载MP4文件）
# replace:X   - 删除文件夹和文件名中的字符串
# 
# 多个条件可以用分号分隔，如：ext:.mkv;min_size:500M，取消下载只要满足其中任意一个条件
# 表示取消下载扩展名为.mkv且大小小于500MB的文件
#***************************************************
''')

        mtime = os.path.getmtime(self.file)  # 获取文件最后修改时间

        if mtime == self.last_mtime:  # 如果文件未被修改
            return  # 直接返回，无需重新加载

        self.last_mtime = mtime  # 更新最后修改时间

        self.rules.clear()  # 清空现有规则列表

        # 【BUG修复】replaces 列表此前从未被清空，热加载时会与旧规则无限累积
        # （表现为日志里的"重命名规则"数量只增不减，且每次改规则文件都会翻倍）
        self.replaces.clear()  # 清空现有替换规则列表
        self.replace_lines.clear()  # 同步清空行号映射

        # 去重用的集合：记录已出现过的条件/替换规则，避免同一规则被重复加载
        # （rules.txt 是长期手工维护的文件，复制粘贴很容易产生重复项）
        seen_conditions = set()  # 取消下载条件的去重键集合
        seen_replaces = set()  # 替换规则的去重键集合
        dup_conditions = 0  # 被去重丢弃的重复条件计数
        dup_replaces = 0  # 被去重丢弃的重复替换规则计数

        with open(self.file, encoding="utf8") as f:  # 以UTF-8编码打开规则文件
            for line_no, line in enumerate(f, 1):  # 逐行读取文件并记录行号
                line = line.strip()  # 去除首尾空白字符

                if not line or line.startswith("#"):  # 如果是空行或注释行
                    continue  # 跳过

                # 将全角分号替换为半角分号，避免规则被错误合并
                line = line.replace("；", ";")

                parts = line.split(";")  # 以分号分割规则行

                for p in parts:  # 处理每个部分
                    if ":" not in p:  # 如果不包含冒号
                        continue  # 跳过

                    # 【BUG修复】此前写作 p.lower().split(":", 1)，把“值”也跟着转成了小写。
                    # 但 replace 规则是作用在【原始文本】上的（区分大小写），
                    # 导致 replace:ReducingMosaic / replace:【S级泄密】 这类含大写字母的规则
                    # 永远匹配不到、静默失效。现改为：只对“键”转小写，值保持原样。
                    k, v = p.split(":", 1)  # 以冒号分割键值对，值保留原始大小写

                    k = k.strip().lower()  # 键统一转小写（保证 replace/filename 等键名可识别）

                    v = v.strip()  # 去除值的首尾空白字符

                    if k == "replace":  # 如果是替换规则字段
                        # replace 作用于原始文本，保持原始大小写
                        # 同一替换规则重复出现时结果完全一致，直接丢弃后来的重复项
                        if v in seen_replaces:  # 已出现过同一条替换规则
                            dup_replaces += 1  # 累加重复计数
                            continue  # 跳过，不重复加入

                        seen_replaces.add(v)  # 登记该替换规则
                        self.replaces.append(v)  # 添加到替换规则列表
                        self.replace_lines[v] = line_no  # 记录该替换规则所在行号
                        continue

                    v = v.lower()  # 其余匹配条件作用于小写化的文件名（见 Condition.match），保持原有行为

                    if k in ("min_size", "max_size"):  # 如果是大小相关字段
                        v = parse_size(v)  # 解析大小字符串

                    if k == "ext":  # 如果是扩展名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    if k == "filename":  # 如果是文件名字段
                        v = [x.strip() for x in v.split(",")]  # 以逗号分割并去除空白字符

                    # 以“键 + 值”构造去重键：列表值转成元组（可哈希），标量值直接使用
                    # 判定结果不受影响（规则之间是 OR 关系，重复条件命中多次也等价于命中一次），
                    # 去重只是省去冗余匹配，并让日志/统计更准确
                    dedup_key = (k, tuple(v) if isinstance(v, list) else v)  # 构造可哈希的去重键

                    if dedup_key in seen_conditions:  # 已出现过同一条件
                        dup_conditions += 1  # 累加重复计数
                        continue  # 跳过，不重复加入

                    seen_conditions.add(dedup_key)  # 登记该条件

                    # 【BUG修复】此前 cond 字典在条件循环【外】创建并被反复复用，
                    # 导致同一行的第 2 个及之后的 Rule 携带了前面所有条件的累积副本
                    # （条件本应彼此独立、OR 关系，累积会让后面的 Rule 意外变宽）。
                    # 现改为每个条件使用独立字典，去重键也才能准确对应单个条件。
                    self.rules.append(Rule({k: v}, raw=line, text=p.strip(), line_no=line_no))  # 创建独立条件对象并加入规则列表

        # 加载统计信息：若有重复项被丢弃，在日志中明确说明，避免"规则莫名不生效"的误判
        dedup_note = ""
        if dup_conditions or dup_replaces:  # 仅在确实发生去重时才提示
            dedup_note = f"（已去重：取消下载条件 {dup_conditions} 条、替换规则 {dup_replaces} 条）"

        logger.info(
            f"共加载 {len(self.rules)} 条取消下载的规则，"
            f"和 {len(self.replaces)} 条重命名规则{dedup_note}"
        )  # 记录已加载的规则数量

    def match(self, file):
        """
        检查文件是否匹配任何规则

        参数:
            file (File): 要检查的文件对象

        返回:
            Rule or None: 首个匹配的规则对象，无匹配返回None
        """
        for r in self.rules:  # 遍历所有规则
            if r.match(file):  # 检查文件是否匹配当前规则
                return r  # 匹配成功返回该规则对象
        return None  # 所有规则都不匹配则返回None

    def explain_deep(self, file_path: str, is_dir_like=False, top_fallback=None) -> RenameResult:
        """
        逐级替换：把路径拆成多级，对**每一级目录名和末级文件名**分别应用全部替换规则
        与 rename() 的区别在于 rename() 只处理末级文件名，中间目录会被原样保留

        空名保护：若某一级替换后变成空字符串（例如目录名恰好是“【分区1】”，被 replace:【*】 全删），
        会导致路径出现连续分隔符或空文件名。此处按优先级回退：
            1) 顶级目录优先使用 top_fallback（通常传入 best_name，即“中文最多”的最佳名）
            2) 其余情况（深层目录、文件名）保留该级**原名**，即等价于该级不修改

        参数:
            file_path (str): 待处理路径，如 "顶级/深层1/深层2/视频.mp4"
            is_dir_like (bool, optional): 路径本身是否就是目录（不以文件名结尾）
            top_fallback (str, optional): 顶级目录替换为空时的兜底名称

        返回:
            RenameResult: mode 为 "deep" 的解释结果，result 为逐级替换后的完整路径，
                           steps 中每条记录都带 level 字段标明所属层级
        """
        # 统一分隔符并拆分为层级列表
        parts = [p for p in file_path.replace("\\", "/").split("/") if p]

        if not parts:  # 空路径直接返回，避免后续索引越界
            return RenameResult(file_path, file_path, [], mode="deep")

        # 末级是否按“文件名”处理：不是目录路径时，末级要拆扩展名并保留它
        last_is_file = not is_dir_like and not file_path.endswith(("/", "\\"))

        new_parts = []  # 逐级替换后的层级列表
        steps = []  # 命中规则记录（跨层级累积）
        total = len(self.replaces)  # 替换规则总数

        for idx, part in enumerate(parts):  # 逐级处理
            is_last = (idx == len(parts) - 1)  # 是否为末级

            if is_last and last_is_file:  # 末级是文件名：分离扩展名，只替换主干
                base, ext = os.path.splitext(part)  # 拆分文件名主干与扩展名
                current = base  # 当前待替换文本为文件名主干
            else:  # 目录级：整段名称都参与替换
                current = part  # 当前待替换文本为整段目录名
                ext = ""  # 目录无扩展名

            start = len(steps)  # 记录本级新产生记录的起始下标，便于事后统一标注层级

            for i, pattern in enumerate(self.replaces, 1):  # 逐条应用替换规则
                after = remove_by_match(current, pattern)  # 计算替换结果
                if after != current:  # 有变化才算命中
                    # 报告中展示该替换规则所在行号与规则名称，便于定位 rules.txt
                    pattern_desc = f"规则位于 rules.txt 第{self.replace_lines.get(pattern, '?')}行，规则名称：replace:{pattern}"
                    steps.append(RenameStep(i, total, pattern_desc, current, after))  # 追加命中记录
                    current = after  # 更新当前文本，继续下一条规则

            # 【空名保护】替换后该级变为空时不能提交给 qB（会产生 "//" 或无扩展名的空文件名）
            # 按优先级回退：顶级目录用 best_name 兜底，其余情况保留原名（即该级不修改）
            if not sanitize_name(current):  # 清理空白后为空，说明该级被替换没了
                if idx == 0 and top_fallback and sanitize_name(top_fallback):
                    # 顶级目录且提供了有效兜底名 -> 使用兜底名
                    current = top_fallback  # 回退到 best_name
                else:
                    # 深层目录 / 文件名，或兜底名同样无效 -> 保留原名，该级不做修改
                    current = part  # 回退到本级原名

            # 统一标注本级产生的所有记录，标明它们属于哪一层路径（便于报告定位）
            # level 使用“本级及以上的原路径”，与 qBittorrent 的 old_path 语义一致
            level_path = "/".join(parts[:idx] + [part])  # 本级的原路径前缀
            for s in steps[start:]:  # 遍历本级新增的记录
                s.level = level_path  # 打上层级标注

            new_parts.append(sanitize_name(current) + ext)  # 清理空白、拼回扩展名并加入结果

        result = "/".join(new_parts)  # 拼回完整路径

        return RenameResult(
            original=file_path,  # 原始路径
            result=result,  # 逐级替换后的路径
            steps=steps,  # 命中规则列表
            is_folder=not last_is_file,  # 整体按目录处理
            dir_part="",  # 逐级模式无需单独区分目录部分
            mode="deep",  # 标记为逐级替换模式
        )

    def explain(self, file_path: str, is_folder=False) -> RenameResult:
        """
        试算重命名结果，并完整记录“哪条规则在第几步起了作用”
        与 rename() 共用同一套处理逻辑，保证解释结果与真实行为 100% 一致

        参数:
            file_path (str): 待处理字符串。文件模式下可含多级目录
            is_folder (bool, optional): True 表示按文件夹名处理，False 按文件路径处理

        返回:
            RenameResult: 含原始值、最终值、命中规则列表的解释结果对象
        """
        if is_folder:  # 文件夹模式：整串就是名称，不做扩展名拆分
            dir_part = ""  # 无目录部分
            name = file_path  # 名称即整串
            ext = ""  # 无扩展名
        else:  # 文件路径模式：只对最后一级“文件名”应用替换规则
            dir_part, filename = os.path.split(file_path)  # 分离目录与文件名
            name, ext = os.path.splitext(filename)  # 分离文件名主干与扩展名

        current = name  # 当前待处理文本
        steps = []  # 命中规则记录列表
        total = len(self.replaces)  # 替换规则总数

        for i, pattern in enumerate(self.replaces, 1):  # 按顺序逐条应用替换规则
            after = remove_by_match(current, pattern)  # 计算应用该规则后的文本
            if after != current:  # 只有文本发生变化才算“命中”
                # 报告中展示该替换规则所在行号与规则名称，便于定位 rules.txt
                pattern_desc = f"规则位于 rules.txt 第{self.replace_lines.get(pattern, '?')}行，规则名称：replace:{pattern}"
                steps.append(RenameStep(i, total, pattern_desc, current, after))  # 记录这一步
                current = after  # 更新当前文本，继续下一条规则

        if is_folder:  # 文件夹模式：仅做空白清理
            result = sanitize_name(current)  # 清理首尾与中间空白
        else:  # 文件模式：清理空白后拼回扩展名与原目录
            result = os.path.join(dir_part, sanitize_name(current) + ext)  # 还原完整路径

        return RenameResult(
            original=file_path,  # 原始字符串
            result=result,  # 最终字符串
            steps=steps,  # 命中规则列表
            is_folder=is_folder,  # 是否文件夹模式
            dir_part=dir_part,  # 未参与替换的目录部分
        )

    def explain_rename(self, file_path: str, is_folder=False) -> RenameResult:
        """
        试算“重命名替换规则”，返回命中的规则列表
        是 explain() 的便捷别名，语义与 explain_cancel 对称，便于直接测试

        参数:
            file_path (str): 待处理字符串（文件夹名或文件路径）
            is_folder (bool, optional): True 表示按文件夹名处理

        返回:
            RenameResult: 含原始值、最终值、命中规则列表的解释结果对象
        """
        return self.explain(file_path, is_folder=is_folder)

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
        # 直接复用 explain 的处理逻辑，仅取最终结果，避免两套代码行为漂移
        return self.explain(file_path, is_folder=is_folder).result

    def explain_cancel(self, name: str, size=0) -> RenameResult:
        """
        试算“取消下载”规则，报告哪些规则命中、为什么命中
        仅用于调试，不改动任何状态

        参数:
            name (str): 文件名或相对路径（用于 ext / filename 匹配）
            size (int, optional): 文件大小（字节），用于 min_size / max_size 匹配

        返回:
            RenameResult: result 为“将被取消下载”或“保留下载”，steps 为命中规则原文
        """
        # 构造模拟文件对象，复用与生产完全一致的匹配链路
        file = File(MockTorrent(), MockRaw(name, size))  # 生成一个仅用于匹配的临时对象

        steps = []  # 命中规则列表
        for i, r in enumerate(self.rules, 1):  # 遍历全部取消下载规则
            if r.match(file):  # 该规则命中当前文件
                # 报告里展示：所在行号、规则名称（条件片段）、实际命中的条件描述
                pattern = f"规则位于 rules.txt 第{r.line_no}行，规则名称：{r.text}（命中：{r.last_match}）"
                steps.append(RenameStep(i, len(self.rules), pattern, name, "取消下载"))  # 记录命中规则

        # 汇总结果：命中任意一条即判定为“取消下载”，与 match() 的首个命中语义一致
        final = "取消下载（不下载此文件）" if steps else "保留下载"
        return RenameResult(
            original=name,  # 原始文件名
            result=final,  # 判定结果
            steps=steps,  # 命中的规则列表
            is_folder=True,  # 视为无需目录拆分的整体
            dir_part="",  # 无目录部分
            mode="cancel",  # 标记为取消下载试算模式
        )

    def debug_match(self, file, matched_rule=None):
        """
        调试规则匹配
        若已传入 matched_rule 则直接记录，否则重新扫描

        参数:
            file (File): 要测试匹配的文件对象
            matched_rule (Rule, optional): 已匹配的规则对象
        """
        # 注意：rules 已按“单条件”去重，索引不再等于 rules.txt 的行号，
        # 因此日志只报“第几条规则”并附上规则原文（原文比行号更有排查价值）
        if matched_rule:  # 已有匹配结果，直接记录，避免二次扫描
            rule_idx = self.rules.index(matched_rule) + 1  # 该规则在去重后列表中的序号
            logger.info(
                f"命中第{rule_idx}/{len(self.rules)}条规则: {matched_rule.raw}"
            )
            return

        # 无传入结果时降级为全量扫描（兼容外部直接调用）
        matched = False
        for i, r in enumerate(self.rules, 1):
            if r.match(file):
                logger.info(f"命中第{i}/{len(self.rules)}条规则: {r.raw}")
                matched = True

        if not matched:
            logger.info("没有任何规则匹配")


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


def _print_report(title, report):
    """
    打印一份测试报告（统一输出格式）

    参数:
        title (str): 报告标题，如“替换规则试算”
        report (RenameResult): explain / explain_cancel 返回的解释结果对象
    """
    bar = "=" * 60  # 报告外框分隔线
    print(bar)  # 输出上边框
    print(f"【{title}】")  # 输出标题
    print("-" * 60)  # 输出内部分隔线
    print(report)  # 输出报告正文
    print(bar)  # 输出下边框



def organize_rules(rule_file="rules.txt", max_parts=8):
    """
    整理规则文件：去重、拆长行、保留注释与分类结构，整理完成后覆盖原文件

    处理规则：
    1. 重复的规则片段（如 replace:【*】、filename:*xx*）全局只保留一个
    2. 一行中规则过多导致过长时，拆分为多行（每行最多 max_parts 条）
    3. 开头的 #******************规则说明*************************** 块原样保留
    4. 每个分类开头的说明注释原样保留（以 # 开头的行都视为注释保留）
    5. 规则按原有分类块归位，块与块之间保留一个空行

    参数:
        rule_file (str): 规则文件名（相对 BASE_DIR）
        max_parts (int): 每行最多容纳的规则条数

    返回:
        tuple: (整理前行数, 整理后行数, 去重丢弃的条数)
    """
    path = os.path.join(BASE_DIR, rule_file)  # 规则文件完整路径
    with open(path, encoding="utf8") as f:  # 读取当前规则文件
        lines = f.read().splitlines()  # 按行拆分

    out = []  # 输出行集合
    seen = set()  # 已出现过的"键:值"规则片段，用于全局去重
    seen_comments = set()  # 已出现过的注释行，避免重复注释块
    buffer_parts = []  # 当前规则块累积的规则片段
    dup_count = 0  # 去重丢弃的条数

    def flush():
        """把当前块累积的规则片段按每行 max_parts 条拆行写入 out"""
        for i in range(0, len(buffer_parts), max_parts):  # 分块切片
            out.append(";".join(buffer_parts[i:i + max_parts]))  # 拼成一行
        buffer_parts.clear()  # 清空缓冲区

    for raw_line in lines:  # 逐行处理
        line = raw_line.strip()  # 去首尾空白

        if line.startswith("#"):  # 注释行：先结算当前规则块，再原样保留注释
            flush()
            out.append(line)  # 注释行原样保留（包括分类说明与规则说明块，一个不删）
            continue

        if not line:  # 空行：先结算当前规则块，再写一个空行分隔
            flush()
            if out and out[-1] != "":  # 避免连续空行
                out.append("")
            continue

        line = line.replace("；", ";")  # 全角分号转半角
        for part in line.split(";"):  # 拆成单个规则片段
            part = part.strip()  # 去空白
            if not part or ":" not in part:  # 空片段或不含冒号的片段跳过
                continue
            if part in seen:  # 重复规则片段，丢弃
                dup_count += 1  # 累计去重条数
                continue
            seen.add(part)  # 登记新规则片段
            buffer_parts.append(part)  # 加入当前块缓冲

    flush()  # 结算最后一块

    # 去掉首尾多余空行，保证以单一换行结尾
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    text = "\n".join(out) + "\n"  # 拼接为最终文本
    with open(path, "w", encoding="utf8") as f:  # 覆盖写回 rules.txt
        f.write(text)

    return len(lines), len(out), dup_count  # 返回统计信息


if __name__ == "__main__":
    """
    直接测试各类规则：每种规则都有自己的试算函数，改字符串即可

    用法:
        python3 RuleEngine_utils.py

    规则试算函数一览:
        engine.explain_rename("字符串")   # 重命名替换规则（只换末级文件名）
        engine.explain_deep("目录/文件")    # 逐级替换规则（每一级目录都替换）
        engine.explain_cancel("文件名")     # 取消下载规则

    其他工具函数:
        organize_rules()                  # 整理 rules.txt：去重、拆长行、保留注释与分类
    """
    engine = RuleEngine("rules.txt")  # 创建规则引擎并加载规则（只读，不连接 qB）
    engine.load()

    # 直接测试：修改下面的测试字符串即可
    # _print_report("重命名替换规则试算", engine.explain_rename("测试字符串"))
    # _print_report("逐级替换规则试算", engine.explain_deep("测试字符串"))
    _print_report("取消下载规则试算", engine.explain_cancel("《震撼精品核弹》身材超级棒的推特网红女神室外极限露出全裸旅游真-实感受世界的美好"))
