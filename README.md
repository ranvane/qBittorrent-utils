# 🚀 qBittorrent Auto Manager (qBittorrent 自动管理器)

[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![qBittorrent API](https://img.shields.io/badge/qBittorrent-WebAPI-orange.svg)](https://github.com/rmartin16/qbittorrent-api)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

一个基于 Python 编写的 **qBittorrent 自动化辅助脚本**。通过调用 qBittorrent WebAPI，配合强大的自定义规则引擎，实现种子下载全生命周期的自动化管理。告别杂乱的文件命名和广告文件，让你的下载目录井井有条，同时自动优化 Tracker 提升下载速度。

## ✨ 核心功能

- 🗑️ **智能垃圾过滤**：基于正则/关键字规则，自动将广告文件、快捷方式(`.url`)或无用文本(`.txt`)的下载优先级设为 `0`，节省磁盘与带宽。
- 🏷️ **多层级智能重命名**：
  - **目录逐级替换**：对种子内**每一级目录**（含顶级目录）应用 `replace` 规则，深层目录不再残留 `【广告】` 前缀。
  - **文件重命名**：自动剔除文件名中的广告前缀/后缀。
  - **种子重命名**：智能提取最佳名称（优先匹配中文字符作为资源名）。
- 🔀 **深层目录扁平化**：把所需文件的深层目录逐层上移到顶级文件夹正下方，目录结构更整洁。
- ⚡ **自动 Tracker 优化**：定时从[ngosang/trackerslist](https://ngosang.github.io/trackerslist/trackers_best.txt) 拉取最新优质 Tracker，并自动去重追加到所有种子中，大幅提升死种/慢种的下载速度（内置 1 小时缓存防封机制）。
- 🔥 **规则热加载 + 自动去重**：修改 `rules.txt` 后无需重启，下一次扫描自动应用；重复规则只加载一次。
- 🧪 **内置规则试算工具**：不连 qB 也能验证规则，精确告诉你“处理后的字符串 + 哪条规则起作用了”。
- 🛡️ **安全测试模式 (Dry Run)**：内置 Dry Run 模式，开启后仅在日志中输出将会执行的操作，避免误伤现有文件。

## 🛠️ 环境依赖

运行本脚本需要 Python 3.6+ 环境，并安装以下依赖库：

```bash
pip install qbittorrent-api requests loguru
```

**⚠️ 注意**：本脚本依赖于同目录下的另外两个核心组件（请确保它们存在于您的仓库中）：
- `qb_utils.py`：提供 qBittorrent 相关的实体类（`Torrent`, `File`, `Action`）和工具函数（`choose_best_name`, `get_top_folder`）。
- `RuleEngine_utils.py`：提供 `RuleEngine` 规则引擎类，用于解析和匹配过滤/重命名规则。

## ⚙️ 配置说明

在主脚本（如 `qbmanager.py`）中，您可以找到 `CONFIG` 字典进行核心配置修改：

```python
CONFIG = {
    "host": "192.168.10.200",     # qBittorrent 监听的 IP/域名
    "port": 8080,                 # qBittorrent WebUI 端口
    "username": "name",        # WebUI 用户名
    "password": "your_password",  # WebUI 密码
    "rule_file": "rules.txt",     # 规则配置文件路径
    "scan_interval": 10,          # 扫描间隔（当前已改为计划任务驱动）
    "dry_run": False,             # 是否开启模拟运行模式 (建议初次使用设为 True)
    "log_file": "qbmanager.log",  # 日志文件输出路径
}
```

### 规则文件 (`rules.txt`)
您需要在此文件中定义过滤和重命名的具体规则，引擎会在运行时动态加载它。

> ⚠️ **注意**：`replace:` 替换规则**区分大小写**。`replace:ReducingMosaic` 只会删除大小写完全一致的 `ReducingMosaic`。
> 而 `filename:` / `ext:` 过滤规则**不区分大小写**（内部自动转小写比对）。

---

## 🧪 规则试算工具（推荐用法）

`RuleEngine_utils.py` 既是被 `qbmanager.py` 调用的规则引擎，也是一个**独立的规则试算脚本**（每类规则都有自己的试算函数）。
它**只读取 `rules.txt`，绝不会连接或修改 qBittorrent**，可以放心随便试。

### 1. 直接运行脚本试算（推荐）

修改 `RuleEngine_utils.py` 末尾 `if __name__ == "__main__":` 中的测试字符串，然后：

```bash
python3 RuleEngine_utils.py
```

脚本会直接对各类规则分别试算并打印命中报告：

```python
engine.explain_rename("测试字符串")   # 重命名替换规则（只换末级文件名）
engine.explain_deep("目录/测试.mp4")   # 逐级替换规则（每一级目录都替换）
engine.explain_cancel("测试字符串")    # 取消下载规则
```

### 5. 在代码中调用

```python
from RuleEngine_utils import RuleEngine

engine = RuleEngine("rules.txt")
engine.load()

# 只想知道结果 -> 和生产完全一致
new_name = engine.rename("大神，【Amber】，小红书", is_folder=True)

# 想知道"哪个规则干的" -> 返回结构化对象
r = engine.explain_rename("大神，【Amber】，小红书", is_folder=True)
print(r.result)                 # '大神，，小红书'
for step in r.steps:            # 每条命中的规则
    print(step.index, step.pattern, step.before, step.after)
print(r.to_dict())              # 完整字典，可直接 json.dumps

# 取消下载规则同理
c = engine.explain_cancel("广告.txt", parse_size("10M"))
print(c.result, len(c.steps))
```

---

## 🐛 已知问题与设计约束

| 项 | 说明 |
|----|------|
| **`rename()` 不改目录** | `rename(path)` 只替换最后一级文件名；**每一级目录**由 `qbmanager.py` 的 `RenameDeepFolders` 负责（用 `--deep` 试算可查看逐级效果）。 |
| **计划式重命名** | 先由 `build_rename_plan()` 一次算出「文件 + 每一级目录」的完整计划，再执行：**先改文件，后改目录（由深到浅）**。不再使用 `remap_path` 前缀映射，避免重复应用替换规则。 |
| **重名自动避让** | 不同条目被 `replace` 清洗成同名时，自动加 `_2`、`_3` 后缀（如 `A.mp4`、`A_2.mp4`），避免 qB 409 冲突与**目录被合并**。文件和目录共用同一名称空间，跨类型同名也会避让。 |
| **后缀不会振荡** | 避让后用 `_2` 而非 `(2)`：`rules.txt` 的 `replace:(*)` / `replace:【*】` 会删掉括号内容，用括号会导致每分钟反复改名。避让名还会校验“再跑一遍规则不变”；若确实找不到稳定名则保留原名、放弃改名。 |
| **容错** | 单种子读取/处理失败只跳过该种子，不影响本轮其余种子；`rules.txt` 中写法错误的大小规则只跳过该条，不会让整份规则失效。 |
| **空目录名保护** | 某级被替换为空时，顶级目录用 `best_name` 兜底，深层目录/文件名保留原名。深层目录**不**用 `best_name`，否则多个空目录会同名导致目录被合并。 |
| **空文件名保护** | 文件名主干被完全删掉时保留原名，不会出现只剩 `.mp4` 的文件。 |
| **`replace:` 区分大小写** | 因为替换作用于**原始文本**。`filename:` / `ext:` 则不区分大小写。 |
| **`*` 是非贪婪匹配** | `replace:【*】` 删除最短的 `【` 到 `】` 片段。`replace:*com@` 删除最短的前缀到 `com@`。 |
| **规则自动去重** | 每次 `load()` 按“单条件”去重，重复项只加载一次并在日志中报告去重条数。判定结果不受影响（规则间是 OR 关系）。 |
| **文件夹名不再用 best_name** | 顶级目录改为“替换后的原名”；`best_name`（中文最多优先）现在只用于**种子名**与顶级目录兜底。 |
| **扁平化一步到位** | 深层目录直接移到顶级目录下（由深到浅），目标重名自动避让；多远种子（多个顶级目录）逐个处理。 |


## 🚀 使用指南

### 方式一：单次运行测试
直接在终端执行脚本，它将扫描当前所有的种子并执行过滤、重命名和 Tracker 更新操作：

```bash
python3 qbmanager.py
```

### 方式二：配合 Cronjob 定时运行（推荐）
本脚本被设计为无状态的单次运行模式，非常适合使用 Linux 系统的 `crontab` 进行定时调度。

打开终端输入 `crontab -e`，添加以下内容（每分钟执行一次）：

```cron
* * * * * /usr/bin/python3 /path/to/your/project/qbmanager.py
```
*(请将 `/usr/bin/python3` 和 `/path/to/your/project/` 替换为您实际的 Python 路径和项目路径)*

## 📂 项目结构

```text
├── qbmanager.py           # 主入口脚本，包含控制器与调度逻辑
├── qb_utils.py            # qB 实体类及通用工具函数封装
├── RuleEngine_utils.py    # 规则解析引擎 + 独立试算命令行工具
├── rules.txt              # 用户自定义的过滤与重命名规则（需自行创建）
├── .trackers_cache        # Tracker 缓存文件（脚本自动生成）
└── qbmanager.log          # 运行日志（由 loguru 自动生成，支持自动轮转）
```

## 📝 贡献与反馈

欢迎提交 Issue 报告 Bug 或分享您实用的 `rules.txt` 规则！也欢迎提交 Pull Request 完善本项目。

## 📄 许可证

本项目基于[MIT License](LICENSE) 协议开源，请自由使用、修改和分发。

## 📋 更新日志

### 2026-11-08 — 逻辑审查：修复 8 处缺陷

**真实 bug**

- **409 冲突重试永不触发**：`Conflict409Error` 的文本只有 `"Conflict"`，不含数字 `409`，
  原判断 `"409" not in str(e)` 恒为真，重试逻辑形同虚设。改为类名/文本双匹配（`_is_conflict`）。
- **扁平化避让名被丢弃**：`build_flatten_plan` 算出了 `new_dir`，但调用 `MoveFolder` 时没传
  `new_path`，实际仍按“上移一级”算目标，重名时照样 409。已把计划目标传入。
- **目录改名撞同层同名文件**：原实现“先分配全部目录、再分配全部文件”，
  `目录【广告】A -> A` 不会发现同层已有文件 `A`。改为**按深度逐层、文件与目录一起两遍分配**。
- **409 避让时漏掉目录名**：`_occupied_names` 只统计文件末级名，目录重名冲突时占用集里没有该目录名，
  重试算出同一个名字。已同时登记每一级目录名。
- **`unique_name` 无解时返回原名**：返回原名可能正是冲突名（409）或会被规则改回（振荡）。
  改为返回 `None`，由调用方保留原名、放弃改名。
- **单种子故障中断整轮扫描**：生成器 `scan()` 内抛异常会终止 for 循环。
  `scan()` 增加单种子 try/continue，`Manager.run()` 拆出 `_process_torrent` 并逐种子捕获。
- **非法大小规则拖垮整份加载**：`min_size:10GBx` 会让 `parse_size` 抛 `ValueError`，
  导致全部过滤/重命名规则失效。改为只跳过该条并告警。
- **`collect_dirs` 路径解析不一致**：用 `PurePosixPath` 而其他函数用 `_path_parts`，
  `a//b`、`a/./b` 等路径会算出对不上的层级。已统一走 `_path_parts`。

**其他**

- `RenameFile` 失败分支原先静默 `return`，改为记录 `logger.error`，便于排查。
- `MoveFolder.get_moved_path` 统一处理反斜杠路径。
- 同步更新 AGENTS.md / README.md。

### 2026-11-08 — 重命名逻辑改为“计划式”并修复重名相关问题

**问题（旧实现的真实缺陷）**

- **重名冲突**：`replace` 常把带不同广告后缀的文件清洗成同名，qB 返回 409，改名静默失败；
  目录清洗成同名时会被 qB **合并**，目录结构直接错乱。
- **重复应用规则**：旧流程先目录改名、再用 `remap_path` 回写文件路径，路径前缀会被反复套用替换规则。
- **空文件名**：文件名主干被规则删空时，结果只剩 `.mp4`。
- **扁平化顺序错误**：旧实现由浅到深逐级上移，子目录先被搬走后父目录路径失效；
  且失败后仍继续移动，导致残留半成品目录。
- **多根种子**：只处理第一个顶级目录，其余目录的深层结构不扁平化。

**修复方式**

- 新增 `qb_utils.build_rename_plan()`：一次算出「文件 + 每一级目录（含顶级）」的完整计划。
  - 两遍分配：先让“不改名”的条目占位，再给改名条目分配避让名，杜绝“改成别人原名”。
  - 执行顺序：**先改文件、后改目录（由深到浅）**，不需要 `remap_path` 前缀映射。
  - 空名/非法名保护：`is_safe_name()` 拒绝空名、`..`、路径分隔符、控制字符。
- 新增 `unique_name()`：同目录重名生成 `名称_2` 后缀，并校验**幂等**（下一轮规则不会再改它）。
- 新增 `order_renames()`：处理 `A→B、B→C` 链式改名，互换改名时用临时名中转。
- 新增 `_do_rename()` 冲突重试：执行阶段命中 409 时重新拉取真实列表、避让后再试一次。
- 新增 `build_flatten_plan()`：扁平化改为由深到浅、一步移到顶级，并做目标重名避让；支持多根种子。
- `RuleEngine.explain()` 增加文件名空名保护（不再返回 `.mp4`）。
- `choose_best_name()` 支持多顶级目录，并去掉种子名中的伪路径部分。

**测试**：用模拟 qB（支持递归改名与 409 冲突）回归 17 个场景，全部通过：
基本逐级替换、文件/目录同名冲突、链式改名、空名保护、文件名清空、多根目录、
扁平化及其重名避让、优先级 0 跳过、反斜杠路径、dry-run、409 重试、括号规则下避让稳定。

### 2026-10-08 — 新增 rules.txt 规则整理函数

- `RuleEngine_utils.organize_rules(rule_file="rules.txt", max_parts=8)`：
  全局去重（重复规则只保留一个）、长行拆分（每行最多 8 条且不超过 120 字符）、保留开头规则说明块与各分类注释、按原分类归位，整理完成后覆盖原文件。
- 已对 `rules.txt` 执行整理：347 条规则零丢失零新增，引擎加载结果不变（332 条取消下载 + 15 条重命名）。

### 2026-10-08 — explain_rename / explain_deep 报告同步显示行号与规则名称

- `load()` 新增 `replace_lines` 映射（replace 值 -> rules.txt 行号），热加载时同步清空。
- `explain()` / `explain_deep()` 命中记录改为：`规则位于 rules.txt 第x行，规则名称：replace:XXX`，与 `explain_cancel()` 格式一致。

### 2026-10-08 — explain_cancel 报告显示具体命中条件与行号

- `Condition.match()` 记录具体命中的条件；`Rule` 新增 `text`（条件片段）、`line_no`（rules.txt 行号）、`last_match`。
- `explain_cancel()` 报告中的规则改为输出：`规则位于 rules.txt 第x行，规则名称：filename:*萝莉岛*（命中：filename:*萝莉岛*）`，
  不再把整行多条条件挤成一行。

### 2026-10-08 — 试算方式改为直接调用（去除命令行）

- `if __name__ == "__main__":` 不再解析命令行参数，改为直接调用各类规则试算函数：
  `engine.explain_rename(...)` / `engine.explain_deep(...)` / `engine.explain_cancel(...)`，
  返回各自命中的规则，并用 `_print_report` 打印报告。
- 新增 `RuleEngine.explain_rename()`：`explain()` 的便捷别名，与 `explain_cancel()` 语义对称。
- 移除 argparse 命令行参数解析与交互模式 `_interactive()`（死代码），试算更简单直接。
- README / AGENTS.md 同步更新试算用法说明。

### 2026-09-27 — 规则引擎试算工具 + 两个 replace BUG 修复

**新增**

- `RuleEngine_utils.py` 新增 `RenameStep` / `RenameResult` 两个结果类，以及
  `RuleEngine.explain()`（替换规则试算）、`RuleEngine.explain_cancel()`（取消下载规则试算）。
  `rename()` 已重构为复用 `explain()`，**保证试算结果与生产行为 100% 一致**。
- `__main__` 重写为命令行试算工具：支持传字符串直接出结果、`--folder`、`--deep`、`--best`、
  `-c/--cancel` 测取消下载规则、`-i/--interactive` 交互模式。
- **目录逐级替换**：`RuleEngine.explain_deep()` + `qbmanager.RenameDeepFolders`。
  对种子内**每一级目录**（含顶级）应用 `replace` 规则，自顶向下逐层改名 + `remap_path` 级联维护路径映射。
  `Manager.run()` 顺序调整为 `best_name` → `RenameDeepFolders` → `RenameFile` → `RenameTorrent`。
- **规则自动去重**：`load()` 按“单条件”去重（`replace` 按值去重），日志报告去重条数。
- `qb_utils` 新增 `collect_dirs()`（收集所有目录层级，父目录先于子目录）与 `remap_path()`（级联改写路径）。

**修复**

- **replace 规则值被误转小写**：`k, v = p.lower().split(":", 1)` 把值也转成了小写，
  导致 `replace:ReducingMosaic`、`replace:【S级泄密】` 等含大写字母的规则**永远匹配不到、静默失效**。
  现改为只对**键**转小写，`replace` 值保持原始大小写；`filename:` / `ext:` 仍维持不区分大小写的原有行为。
- **热加载时 replaces 无限累积**：`load()` 只 `self.rules.clear()` 却从不清 `self.replaces`，
  导致每改一次 `rules.txt` 替换规则就翻倍。已补上 `self.replaces.clear()`。
- **交互模式前缀解析错误**：`:f` / `:c` 因只取了 `line[0]` 而永远匹配不上；
  无前缀时又会吞掉首字。已重写为三段式解析（带冒号 / 无冒号简写 / 无前缀）。
- **条件字典复用导致规则变宽**：`cond` 在条件循环外复用，第 2 个及之后的 `Rule` 携带了前面所有条件的累积副本。
  已改为每个条件使用独立字典（判定结果不变，仅修正日志与去重）。
- **路径映射未级联**：`remap_path` 原本只应用一次映射，多层目录改名时第二层及之后会失效，
  导致文件重命名使用失效的旧路径而**静默失败**。已改为迭代级联 + 死循环防护。

**清理**

- `rules.txt` 第 51-58 行残留了**已提交的 git 冲突标记**（`<<<<<<< HEAD` / `=======` / `>>>>>>>`），
  冲突两侧规则同时被加载。已合并两侧并清掉 `*cc.mp4`、`*抖音Max*`、`*漫画*`、`*男娘日记*`、
  `*資源啓動*`、`*顶级黑客*` 等重复条件项。
  校验结果：**清理前后规则种类均为 346 种，零丢失、零新增，完全等价。**

**文档**

- README 新增「🧪 规则试算工具」「🐛 已知问题与设计约束」「📋 更新日志」章节。
- AGENTS.md 同步更新核心功能、模块职责与设计约定。

### 2026-09-27 — 目录参与替换规则 + 规则去重

**新增功能**

- **目录逐级替换规则**（需求：让目录也参与替换）
  - 核心算法：**自顶向下 + 路径映射级联**。
    - qB 的 `torrents_rename_folder` 是**递归**的，改父目录会连带子目录，所以必须父目录先改；
    - 父目录改名后子目录的 `old_path` 已失效，用 `remap_path` 级联改写前缀（可连续应用多次映射）；
    - 每级只调用一次 qB 接口，API 调用次数最少。
  - `explain_deep(..., top_fallback=)` 带**空名保护**：某级替换为空时，顶级目录用 `best_name` 兜底，
    深层目录/文件名保留原名。避免路径出现 `//`。
  - ⚠️ 深层目录**刻意不**用 `best_name` 兜底：多个空目录会得到同名，导致目录被合并、结构错乱。

**规则去重**

- 每次 `load()` 自动去重：取消下载条件按 `(键, 值)` 去重、`replace` 按值去重。
- 判定结果不受影响（规则间为 OR 关系），仅省去冗余匹配并让日志/统计更准确。
- 去重条数在加载日志中报告。

**行为变更（需知悉）**

- 顶级文件夹名不再固定使用 `best_name`，改为「替换后的原名」；
  `best_name`（中文最多优先）现在仅用于**种子名**与顶级目录的空名兜底。
- `Manager.run()` 中不再调用 `RenameFolder`（`RenameFolder` 类保留）。

**文档**

- README 新增 `--deep` / `--best` 试算用法、目录逐级替换原理与已知约束。
- AGENTS.md 新增约定第 11 条（去重）、第 12 条（目录逐级替换）。

---
