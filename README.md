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

`RuleEngine_utils.py` 既是被 `qbmanager.py` 调用的规则引擎，也是一个**独立的规则试算命令行工具**。
它**只读取 `rules.txt`，绝不会连接或修改 qBittorrent**，可以放心随便试。

### 1. 测试重命名替换规则（传入字符串即可）

```bash
python3 RuleEngine_utils.py "大神，【Amber】，小红书"
```

输出会明确告诉你**处理后的字符串**和**是哪条规则起的作用**：

```text
============================================================
【替换规则试算】
------------------------------------------------------------
原始字符串 : 大神，【Amber】，小红书
------------------------------------------------------------
命中 1 条替换规则：
  第1/16条  【*】  :  '大神，【Amber】，小红书' -> '大神，，小红书'
------------------------------------------------------------
最终结果   : 大神，，小红书
是否变化   : 是
============================================================
```

### 2. 测试文件路径（自动提示“目录不参与替换”）

```bash
python3 RuleEngine_utils.py "【下课后】信息/【下课后】信息.mp4"
```

```text
原始字符串 : 【下课后】信息/【下课后】信息.mp4
目录部分   : 【下课后】信息  <-- 目录不参与替换规则
文件名     : 【下课后】信息/信息.mp4
命中 1 条替换规则：
  第1/16条  【*】  :  '【下课后】信息' -> '信息'
最终结果   : 【下课后】信息/信息.mp4
```

> 💡 上面的模式**只替换文件名**（等价于生产环境 `rename()` 的行为）。
> 想看“每一级目录都被替换”的效果，请用下面的 `--deep` 模式。

### 2.1 逐级替换（每一级目录都替换）⭐

```bash
python3 RuleEngine_utils.py "【AI增强】顶级/【分区1】/[合集]深层2/489155.com@【AI增强】EDMosaic-567.mp4" --deep
```

```text
命中 5 条替换规则：
  [层级] 【AI增强】顶级
    第1/14条  【*】  :  '【AI增强】顶级' -> '顶级'
  [层级] 【AI增强】顶级/【分区1】
    第1/14条  【*】  :  '【分区1】' -> ''          <-- 替换后为空 -> 保留原名
  [层级] 【AI增强】顶级/【分区1】/[合集]深层2
    第8/14条  [*]  :  '[合集]深层2' -> '深层2'
  [层级] .../489155.com@【AI增强】EDMosaic-567.mp4
    第1/14条  【*】  :  '489155.com@【AI增强】EDMosaic-567' -> '489155.com@EDMosaic-567'
    第3/14条  *com@  :  '489155.com@EDMosaic-567' -> 'EDMosaic-567'
最终结果   : 顶级/【分区1】/深层2/EDMosaic-567.mp4
```

| 参数 | 作用 |
|------|------|
| `--deep` | 逐级替换：路径中**每一级目录 + 文件名**都应用替换规则 |
| `--best "名称"` | 顶级目录被替换为空时的兜底名（生产环境自动取 `best_name`） |

> 🛡️ **空名保护**：某一级被替换成空字符串时（如目录名恰好是 `【分区1】`），
> **顶级目录**用兜底名，**深层目录/文件名保留原名**。
> 这样可避免路径出现 `//`，也避免多个空目录被兜底成同名而合并。

### 3. 测试取消下载规则

```bash
python3 RuleEngine_utils.py -c "某文件.mp4"          # 大小默认 10M
python3 RuleEngine_utils.py -c "某文件.mp4" 500K     # 指定大小
```

输出形如：

```text
最终结果   : 取消下载（不下载此文件）
命中 3 条取消下载规则：
  第12/345条  ext:.url;ext:.txt;...  :  '某文件.mp4' -> '取消下载'
```

### 4. 交互模式（连续粘贴测试，推荐）

```bash
python3 RuleEngine_utils.py -i
```

| 前缀 | 作用 |
|------|------|
| 直接输入 | 按**文件夹名**测试替换规则 |
| `:f ` | 按**文件路径**测试替换规则（显示目录不参与替换的提示） |
| `:c ` | 测试**取消下载**规则 |
| `:q` | 退出 |

### 5. 在代码中调用

```python
from RuleEngine_utils import RuleEngine

engine = RuleEngine("rules.txt")
engine.load()

# 只想知道结果 -> 和生产完全一致
new_name = engine.rename("大神，【Amber】，小红书", is_folder=True)

# 想知道"哪个规则干的" -> 返回结构化对象
r = engine.explain("大神，【Amber】，小红书", is_folder=True)
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
| **目录逐级替换的自顶向下顺序** | qB 的 `torrents_rename_folder` 是**递归**的，改父目录会连带子目录，所以必须父目录先改，并用 `remap_path` 级联维护路径映射。 |
| **空目录名保护** | 某级被替换为空时，顶级目录用 `best_name` 兜底，深层目录/文件名保留原名。深层目录**不**用 `best_name`，否则多个空目录会同名导致目录被合并。 |
| **`replace:` 区分大小写** | 因为替换作用于**原始文本**。`filename:` / `ext:` 则不区分大小写。 |
| **`*` 是非贪婪匹配** | `replace:【*】` 删除最短的 `【` 到 `】` 片段。`replace:*com@` 删除最短的前缀到 `com@`。 |
| **规则自动去重** | 每次 `load()` 按“单条件”去重，重复项只加载一次并在日志中报告去重条数。判定结果不受影响（规则间是 OR 关系）。 |
| **文件夹名不再用 best_name** | 顶级目录改为“替换后的原名”；`best_name`（中文最多优先）现在只用于**种子名**与顶级目录兜底。 |


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
