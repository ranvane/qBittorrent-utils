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


def _path_parts(name):
    """
    将种子内相对路径统一按 POSIX 规则拆分为层级列表

    参数:
        name (str): 种子内相对路径（可能使用反斜杠，来自不同平台/客户端）

    返回:
        tuple: 去掉空层级后的路径段元组
    """
    return tuple(part for part in pathlib.PurePosixPath(
        name.replace("\\", "/")).parts if part not in ("", "."))


def get_top_folders(files):
    """
    获取种子内所有顶级文件夹名称（去重、保持出现顺序）

    单个种子可能包含多个顶级目录（多根种子），也可能同时包含散落文件。
    只收集路径深度大于 1 的条目，散落文件没有顶级目录。

    参数:
        files: 包含文件对象的列表，每个文件对象有 name 属性表示文件路径

    返回:
        list: 顶级文件夹名称列表（可能为空）
    """
    names = []  # 按出现顺序保存顶级目录名
    for f in files:
        parts = _path_parts(f.name)
        if len(parts) > 1 and parts[0] not in names:
            names.append(parts[0])
    return names


def get_top_folder(files):
    """
    从文件列表中获取顶级文件夹名称

    参数:
        files: 包含文件对象的列表，每个文件对象有name属性表示文件路径

    返回:
        str or None: 如果存在顶级文件夹则返回其名称，否则返回None
    """
    folders = get_top_folders(files)
    return folders[0] if folders else None


def collect_dirs(files, min_depth=1):
    """
    收集文件列表中出现过的所有目录层级路径
    用于按“自顶向下、逐层”的顺序对目录应用替换规则

    参数:
        files: 包含文件对象的列表，每个文件对象有 name 属性（相对路径）
        min_depth (int): 最小层级深度，1 表示包含顶级目录

    返回:
        list: 目录路径列表，已去重，并按 (深度, 路径) 排序
              —— 排序保证父目录一定排在子目录之前，便于逐层重命名
    """
    dirs = set()  # 存储目录路径（去重）

    for f in files:  # 遍历所有文件
        # 路径包含多级目录时才需要收集（单文件的种子没有中间目录）
        parts = pathlib.PurePosixPath(f.name.replace("\\", "/")).parts

        # 末级是文件名不参与收集，因此只取第 1 层到第 len(parts)-1 层
        # 并用 min_depth 过滤掉不需要处理的浅层（如顶级目录可传 2 跳过）
        for i in range(min_depth, len(parts)):
            dirs.add("/".join(parts[:i]))  # 收集该层及以上的完整目录路径

    # 按 (深度, 路径) 排序：深度小（靠上）的目录在前，保证自顶向下处理
    # 这样父目录改名后，qB 会递归带动子目录，届时只需处理子目录自身的新名字
    return sorted(dirs, key=lambda p: (p.count("/") + 1, p))


def remap_path(path, mapping):
    """
    按“旧路径 → 新路径”映射重写给定路径
    用于父目录改名后，把后续待处理路径的父级前缀同步为新路径

    支持【级联】改写：多层目录自顶向下逐层改名时，前缀会连续变化，
    必须反复应用映射直到没有新映射可命中，否则第二层及之后的改名会丢失。
    例：mapping={"A":"B", "B/c":"B/d"} 时，"A/c/f.mp4" 需经两次改写得到 "B/d/f.mp4"

    参数:
        path (str): 待重写的路径，如 "顶级/深层1/深层2"
        mapping (dict): 旧路径到新路径的映射，如 {"顶级/深层1": "顶级/分区1"}

    返回:
        str: 重写后的路径；无匹配前缀时原样返回
    """
    result = path  # 当前重写结果

    # 迭代上限取 mapping 大小 + 1：每轮至少命中一个映射才继续，
    # 因此最多 len(mapping) 轮即可收敛；+1 留一次用于“确认无更多映射”的收尾判断
    # 该上限同时防止映射互相引用（如 A->B, B->A）导致死循环
    for _ in range(len(mapping) + 1):
        for old in sorted(mapping, key=len, reverse=True):  # 长前缀优先，匹配更精确
            if result == old:  # 完全相等，直接替换
                return mapping[old]

            if result.startswith(old + "/"):  # 是某个已改名目录的子路径
                result = mapping[old] + result[len(old):]  # 替换前缀，保留子路径部分
                break  # 应用一个映射后跳出，重新扫描（可能触发级联改写）
        else:
            # 内层循环未被 break，说明没有任何映射能命中当前路径，改写完成
            break

    return result  # 返回重写结果


def get_keep_dirs(files):
    """
    从文件列表中获取所有"所需文件"（优先级不为0）所在的深层目录路径
    用于将深层目录移动到顶级文件夹（扁平化目录结构）

    参数:
        files: 包含文件对象的列表，每个文件对象有 name/priority 属性

    返回:
        list: 需要提升到顶级的深层目录路径列表（去重，已按路径排序）
    """
    dirs = set()  # 存储需要提升的目录路径（去重）

    for f in files:
        # 跳过优先级为0的文件（被过滤掉、无需下载的文件）
        if f.priority == 0:
            continue

        # 统一按 POSIX 规则拆分路径，避免反斜杠路径被当成单层
        parts = _path_parts(f.name)

        # 路径包含多个部分说明文件在某个文件夹中
        if len(parts) > 1:
            # 文件的目录部分 = 除文件名外的所有路径段（即全路径去掉末级文件名）
            dir_path = "/".join(parts[:-1])
            # 收集该目录路径
            dirs.add(dir_path)

    # 按路径排序返回，保证执行顺序稳定（先处理浅层目录）
    return sorted(dirs)


def split_parent_leaf(path):
    """
    将路径拆分为“父目录 + 末级名称”

    参数:
        path (str): 统一后的相对路径，如 "顶级/深层/文件.mp4"

    返回:
        tuple: (父目录, 末级名称)，顶级条目的父目录为空字符串
    """
    parts = _path_parts(path)
    if not parts:  # 空路径保护
        return "", ""
    if len(parts) == 1:  # 顶级条目没有父目录
        return "", parts[0]
    return "/".join(parts[:-1]), parts[-1]


def _is_stable_name(engine, leaf, is_dir):
    """
    判断一个名称再次应用替换规则后是否保持不变（幂等）

    为什么需要：冲突避让会产生 “名称_2” 这类后缀，若用户规则恰好能删掉该后缀
    （例如 replace:(*) 会删掉括号内容），下一轮扫描会把两个条目再次清洗成同名，
    形成每分钟反复改名的振荡。这里要求避让候选名必须“规则再跑一遍也不变”。

    参数:
        engine (RuleEngine | None): 规则引擎，None 表示不做校验
        leaf (str): 单级名称
        is_dir (bool): 是否目录

    返回:
        bool: 稳定返回 True
    """
    if engine is None:  # 未提供引擎时跳过校验
        return True
    try:
        result = engine.explain(leaf, is_folder=is_dir).result
    except Exception:
        return True  # 校验异常不阻断改名，按稳定处理
    if not is_dir:  # 文件结果可能带路径，防御性只取末级
        result = result.replace("\\", "/").split("/")[-1]
    return result == leaf


def unique_name(name, used_lower, is_dir=False, engine=None):
    """
    在目标目录内生成不重名、且不会被规则再次改写的名称

    为什么需要：replace 规则会把带不同广告后缀的文件/目录清洗成同一个名字，
    直接提交给 qB 会返回 409 冲突；目录同名更会被合并，造成结构错乱。

    后缀使用 “_2/_3”（不用括号）：rules.txt 常含 replace:(*)、replace:【*】，
    括号类后缀会被下一轮扫描删掉，导致改名反复振荡。

    参数:
        name (str): 期望的新名称（末级名称，不含目录）
        used_lower (set): 同目录下已占用的名称（统一小写，兼容大小写不敏感文件系统）
        is_dir (bool): True 表示目录（不拆分扩展名），False 表示文件
        engine (RuleEngine, optional): 提供时校验候选名幂等（见 _is_stable_name）

    返回:
        str: 可用的唯一名称；输入为空时原样返回
    """
    if not name:  # 空名不做处理，交由调用方兜底
        return name

    if name.lower() not in used_lower:  # 本身不冲突，直接使用
        return name

    if is_dir:
        base, ext = name, ""  # 目录不拆分扩展名
    else:
        base, ext = os.path.splitext(name)  # 文件保留扩展名

    seq = 2  # 从 _2 开始递增，避免与常见 (1) 命名混淆
    for _ in range(20):  # 上限保护：极端规则下也不会死循环
        candidate = f"{base}_{seq}{ext}"
        # 既要不冲突，也要保证下一轮扫描不会把它改回原名
        if (candidate.lower() not in used_lower
                and _is_stable_name(engine, candidate, is_dir)):
            return candidate
        seq += 1

    # 找不到稳定候选（用户的 replace 规则能删掉所有后缀）时放弃改名：
    # 保持原名最多只是本轮跳过，绝不会形成“改名→被规则改回→再改名”的振荡
    return name


def is_safe_name(name):
    """
    判断名称能否作为单级文件/目录名提交给 qBittorrent

    拒绝空名、"."、".."、路径分隔符与控制字符：
    这些名称一旦提交，轻则该级改名失败（404/409），重则改变目录层级、写坏路径。

    参数:
        name (str): 待校验的单级名称

    返回:
        bool: 可作为单级名称时返回 True
    """
    if not name or name in (".", ".."):  # 空名与特殊目录名
        return False
    if "/" in name or "\\" in name:  # 路径分隔符会破坏层级
        return False
    if any(ord(ch) < 32 for ch in name):  # 控制字符
        return False
    return True


def join_path(parent, leaf):
    """
    拼接父目录与末级名称（父目录为空时直接返回末级名称）

    参数:
        parent (str): 父目录路径
        leaf (str): 末级名称

    返回:
        str: 拼接后的相对路径
    """
    return f"{parent}/{leaf}" if parent else leaf


def path_depth(path):
    """
    计算相对路径的层级深度（顶级目录为 1，顶级目录下的文件为 2）

    参数:
        path (str): 相对路径

    返回:
        int: 层级数量，空路径返回 0
    """
    return len(_path_parts(path))


def _proposed_dir_leaf(engine, leaf, parent, top_fallback):
    """
    计算某一级目录替换后的新名称，并做空名/非法名保护

    保护顺序：
        1) 顶级目录替换为空且提供了合法兜底名 -> 使用兜底名
        2) 其余情况保留原名（等价于该级不修改）
    ⚠️ 深层目录绝不能用兜底名，否则多个空目录会同名而被合并。

    参数:
        engine (RuleEngine): 规则引擎
        leaf (str): 该级目录原名
        parent (str): 父目录原路径（顶级目录为空字符串）
        top_fallback (str, optional): 顶级目录兜底名（通常是 best_name）

    返回:
        str: 替换后仍合法的新名称；不合法时返回原名
    """
    new_leaf = engine.explain(leaf, is_folder=True).result
    if is_safe_name(new_leaf):  # 替换结果合法，直接使用
        return new_leaf
    if not parent and top_fallback and is_safe_name(top_fallback):
        return top_fallback  # 顶级目录空名 -> best_name 兜底
    return leaf  # 深层目录/文件名 -> 保留原名


def _proposed_file_leaf(engine, leaf):
    """
    计算文件名替换后的新名称（保留扩展名），并做空名/非法名保护

    参数:
        engine (RuleEngine): 规则引擎
        leaf (str): 文件名原名（含扩展名）

    返回:
        str: 替换后仍合法的文件名；不合法时返回原名
    """
    new_leaf = engine.explain(leaf, is_folder=False).result
    # explain 返回的可能是路径，防御性只取末级
    new_leaf = new_leaf.replace("\\", "/").split("/")[-1] if new_leaf else new_leaf
    return new_leaf if is_safe_name(new_leaf) else leaf


def order_renames(pairs, is_dir=False):
    """
    对同目录内的改名排序，处理“目标名仍是别人旧名”的链式改名与互换改名

    示例：
        A -> B、B -> C 时，必须先 B -> C，再 A -> B，否则 A -> B 会撞上尚未改名的 B；
        A -> B、B -> A 这种互换无法直接完成，需要先改成临时名中转。

    参数:
        pairs (list): [(旧路径, 新路径), ...]，须同属一个父目录
        is_dir (bool): 是否为目录改名（影响临时名的扩展名处理）

    返回:
        list: 可直接按顺序执行的 [(旧路径, 新路径), ...]，含临时名中转步骤
    """
    if not pairs:
        return []

    pending = list(pairs)  # 待执行改名
    sources = {old for old, _ in pending}  # 尚未改走的旧路径（用于判断链式/互换）
    # 临时名只需避开同目录下的末级名称，因此这里收集的是 leaf 而不是完整路径
    occupied = {split_parent_leaf(old)[1] for old, _ in pending}
    result = []

    while pending:
        # 优先执行“目标名不再被待改名条目占用”的条目
        for index, (old, new) in enumerate(pending):
            if new not in sources or new == old:
                break
        else:
            # 全部互相占用（存在环）：把第一个改成临时名，打破死锁
            index = 0
            old, new = pending[index]
            parent, leaf = split_parent_leaf(old)
            # 临时名只存在一瞬间，不参与幂等校验（避免规则把临时后缀也删掉导致无解）
            if is_dir:
                temp_leaf = unique_name(f"{leaf}__tmp__", occupied, is_dir=True)
            else:
                base, ext = os.path.splitext(leaf)
                temp_leaf = unique_name(f"{base}__tmp__{ext}", occupied,
                                        is_dir=False)
            temp_path = join_path(parent, temp_leaf)
            result.append((old, temp_path))
            occupied.add(temp_leaf.lower())
            sources.discard(old)
            pending[index] = (temp_path, new)
            sources.add(temp_path)
            continue

        old, new = pending.pop(index)
        sources.discard(old)
        occupied.discard(split_parent_leaf(old)[1].lower())
        occupied.add(split_parent_leaf(new)[1].lower())
        result.append((old, new))

    return result


def build_rename_plan(files, engine, top_fallback=None):
    """
    统一生成整个种子的重命名计划（纯计算，不触碰 qB）

    设计要点（旧实现的问题都源于缺少统一计划）：
        1. 重名避让：不同文件/目录被 replace 清洗成同一名称时，按“名称_2”递增，
           避免 qB 返回 409 冲突，也避免目录同名被合并导致结构错乱。
        2. 两遍分配：同一父目录下先让“不改名”的条目占位，再分配改名条目，
           否则 A->B 可能撞上本身就叫 B 且不改名的条目。
        3. 文件先于目录执行、目录由深到浅执行：
           - 文件改名时父目录还是原名，路径一定有效；
           - 深层目录先改名，路径仍在其原名父目录下，随后父目录改名会递归带走它。
           这样完全不需要 remap_path 前缀映射，也不会重复应用替换规则。
        4. 空名/非法名一律回退原名，绝不提交空名、路径分隔符或控制字符。

    参数:
        files: 文件对象列表（需有 name 属性）
        engine (RuleEngine): 规则引擎
        top_fallback (str, optional): 顶级目录替换为空时的兜底名

    返回:
        dict: {
            "files": [(旧路径, 新路径), ...],   # 仅包含真正有变化的文件
            "dirs":  [(旧路径, 新路径), ...],   # 仅包含真正有变化的目录，已按深度倒序
        }
    """
    dirs = collect_dirs(files, min_depth=1)  # 已按 (深度, 路径) 升序

    used_by_dir = {}  # 已确定的父目录路径 -> 已占用名称（小写）

    def reserve(parent, leaf):
        """在指定目录的名称空间内登记一个已占用名称"""
        used_by_dir.setdefault(parent, set()).add(leaf.lower())

    def taken(parent):
        """获取指定目录已占用的名称集合（小写）"""
        return used_by_dir.setdefault(parent, set())

    # ---------- 第一阶段：目录（逐层两遍分配）----------
    # 同一父目录下的条目层级必然相同，因此按深度逐层处理即可：
    #   第 1 遍：先让“不改名”的目录占位；
    #   第 2 遍：再给改名的目录分配避让名。
    # 顺序不能颠倒，否则 A->B 可能撞上本身就叫 B 且不改名的目录。
    resolved_dir = {}  # 目录原路径 -> 最终完整路径（父目录部分已解析）

    by_depth = {}  # 深度 -> 该层目录列表（保持 collect_dirs 的顺序）
    for old_dir in dirs:
        by_depth.setdefault(path_depth(old_dir), []).append(old_dir)

    for depth in sorted(by_depth):  # 自顶向下
        level_dirs = by_depth[depth]
        planned = {}  # 目录原路径 -> 计划末级名

        for old_dir in level_dirs:  # 第 1 遍：登记计划名与不改名条目
            parent, leaf = split_parent_leaf(old_dir)
            parent_final = resolved_dir.get(parent, parent) if parent else ""
            proposed = _proposed_dir_leaf(engine, leaf, parent, top_fallback)
            planned[old_dir] = (parent_final, leaf, proposed)
            if proposed == leaf:  # 不改名的先占位
                reserve(parent_final, leaf)

        for old_dir in level_dirs:  # 第 2 遍：分配改名条目
            parent_final, leaf, proposed = planned[old_dir]
            if proposed == leaf:
                resolved_dir[old_dir] = join_path(parent_final, leaf)
                continue
            new_leaf = unique_name(proposed, taken(parent_final),
                                   is_dir=True, engine=engine)
            reserve(parent_final, new_leaf)
            resolved_dir[old_dir] = join_path(parent_final, new_leaf)

    # ---------- 第二阶段：文件（同样两遍分配）----------
    file_entries = []  # (原路径, 原父目录, 最终父目录, 原名, 替换名, 优先级)
    for f in files:
        parent, leaf = split_parent_leaf(f.name)
        parent_final = resolved_dir.get(parent, parent) if parent else ""
        proposed = _proposed_file_leaf(engine, leaf)
        file_entries.append((f.name, parent, parent_final, leaf, proposed,
                             getattr(f, "priority", 1)))

    for _, _, parent_final, leaf, proposed, priority in file_entries:
        # 不改名的文件、以及优先级为 0（不下载、不改名）的文件先占位
        if proposed == leaf or priority == 0:
            reserve(parent_final, leaf)

    file_plan = []
    for old_path, parent, parent_final, leaf, proposed, priority in file_entries:
        if priority == 0 or proposed == leaf:  # 无需改名
            continue

        new_leaf = unique_name(proposed, taken(parent_final),
                               is_dir=False, engine=engine)
        reserve(parent_final, new_leaf)

        # 文件改名在目录改名之前执行，因此这里必须使用原父目录（当前真实路径）
        file_plan.append((old_path, join_path(parent, new_leaf)))

    # 同目录内可能存在 A->B 且 B->C 的链式改名，统一排序后再执行，避免撞名
    file_plan = _order_plan_by_parent(file_plan)

    # 目录计划：由深到浅执行；新路径同样使用原父目录（父目录尚未改名）
    dir_plan = []
    for old_dir in sorted(dirs, key=path_depth, reverse=True):
        parent, leaf = split_parent_leaf(old_dir)
        new_leaf = split_parent_leaf(resolved_dir[old_dir])[1]
        if new_leaf == leaf:
            continue
        dir_plan.append((old_dir, join_path(parent, new_leaf)))

    # 目录同样需要处理链式改名；按父目录分组排序不改变“由深到浅”的层级要求，
    # 因为同一父目录下的目录层级必然相同
    dir_plan = _order_plan_by_parent(dir_plan, is_dir=True)

    return {"files": file_plan, "dirs": dir_plan}


def _order_plan_by_parent(pairs, is_dir=False):
    """
    按父目录分组，对每组内的改名做链式避让排序后合并

    参数:
        pairs (list): [(旧路径, 新路径), ...]
              约定调用方已保证同父目录的条目在排序后仍满足层级顺序
        is_dir (bool): 是否为目录改名

    返回:
        list: 可直接执行的有序改名列表
    """
    groups = {}  # 父目录 -> 该目录下的改名条目
    order = []  # 保持父目录首次出现顺序，避免结果抖动
    for old_path, new_path in pairs:
        parent, _ = split_parent_leaf(old_path)
        if parent not in groups:
            groups[parent] = []
            order.append(parent)
        groups[parent].append((old_path, new_path))

    ordered = []
    for parent in order:
        ordered.extend(order_renames(groups[parent], is_dir=is_dir))
    return ordered


def build_flatten_plan(files, top_folder, engine=None):
    """
    生成“深层目录扁平化”计划：把所需文件所在的深层目录直接移到顶级目录下

    相比旧实现（每次只上移一级、浅层先处理）：
        1. 由深到浅处理：子目录先搬走，父目录路径始终有效；
        2. 一步到位：qB 的 rename_folder 允许更换父目录，无需循环上移；
        3. 重名避让：目标目录已存在同名时改用 “名称_2”，避免目录被合并。

    参数:
        files: 文件对象列表（需有 name / priority）
        top_folder (str): 顶级目录名
        engine (RuleEngine, optional): 用于校验避让名不会被规则再次改写

    返回:
        list: [(旧目录路径, 新目录路径), ...]，已按深度倒序
    """
    if not top_folder:
        return []

    # 顶级目录下已占用的名称（文件与目录共用名称空间）
    reserved = set()
    for f in files:
        parts = _path_parts(f.name)
        if len(parts) >= 2 and parts[0] == top_folder:
            reserved.add(parts[1].lower())

    candidates = []  # 需要扁平化的深层目录
    for deep_dir in get_keep_dirs(files):
        parts = _path_parts(deep_dir)
        # 只处理顶级目录之下、且层级 >=3 的目录（2 级目录已经在顶级正下方）
        if len(parts) >= 3 and parts[0] == top_folder:
            candidates.append(deep_dir)

    # 由深到浅处理，保证搬走子目录时父目录路径仍然有效
    candidates.sort(key=lambda p: (-path_depth(p), p))

    plan = []
    for deep_dir in candidates:
        leaf = _path_parts(deep_dir)[-1]  # 末级目录名才是要保留的名称
        new_leaf = unique_name(leaf, reserved, is_dir=True, engine=engine)  # 规避顶级目录下的重名
        reserved.add(new_leaf.lower())
        plan.append((deep_dir, join_path(top_folder, new_leaf)))

    return plan





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
    # 种子名可能被写成 "资源名/子目录" 这类伪路径，只取末级作为候选，
    # 否则后续会被当成分隔符而产生非法种子名
    torrent_leaf = torrent.name.replace("\\", "/").split("/")[-1]
    candidates.append(engine.rename(torrent_leaf, is_folder=True))

    # 获取顶级文件夹名称，如果存在则也作为候选
    # 多根种子可能有多个顶级目录，全部纳入候选
    for folder in get_top_folders(files):
        # 文件夹名是整串名称，按文件夹模式替换（不拆扩展名）
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
