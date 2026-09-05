# AGENTS.md — qBittorrent-utils 项目协作规范

> 本文件用于指导 AI 智能体与本项目协作。**每次有功能修改、较大的修改或新的需求时，必须同步更新本文件。**

---

## 1. 项目概述

**qBittorrent Auto Manager** 是一个基于 Python 编写的 qBittorrent 自动化辅助脚本。它通过调用 qBittorrent WebAPI，结合自定义规则引擎，实现种子下载全生命周期的自动化管理，包括垃圾文件过滤、多层级智能重命名以及 Tracker 自动优化。

**运行方式**：无状态单次运行模式，配合 Linux `crontab` 定时调度（每分钟执行一次）。

---

## 2. 核心功能

1. **规则过滤文件**：基于正则/关键字规则，将广告文件、快捷方式（`.url`）、无用文本（`.txt`）等下载优先级设为 `0`（不下载）。
2. **自动文件重命名**：剔除文件名中的广告前缀/后缀。
3. **自动种子重命名**：智能提取最佳名称（优先中文字符作为资源名）。
4. **自动顶层目录重命名**：将顶级文件夹重命名为最佳名称。
5. **中文字符最多优先作为资源名称**。
6. **规则热加载**：修改 `rules.txt` 后无需重启，下一次扫描自动应用。
7. **添加 Tracker 列表**：从外部源拉取并合并 Tracker，内置 1 小时缓存。

---

## 3. 项目结构

```text
├── qbmanager.py           # 主入口脚本（控制器 + 操作类 + 主管理器 + Tracker 逻辑）
├── qb_utils.py            # 实体类（File/Torrent/Action） + 通用工具函数
├── RuleEngine_utils.py    # 规则引擎（Condition/Rule/RuleEngine + Mock 测试类）
├── rules.txt              # 用户自定义过滤与重命名规则
├── requirements.txt       # 依赖清单
├── trackers_cache.json    # Tracker 缓存文件（脚本自动生成，1 小时过期）
├── commit.sh              # 一键提交推送脚本（含代理配置）
└── AGENTS.md              # 本文件（AI 协作规范）
```

---

## 4. 模块职责说明

### 4.1 `qbmanager.py` — 主入口

| 组件 | 职责 |
|------|------|
| `CONFIG` 字典 | 核心配置（host/port/username/password/rule_file/scan_interval/dry_run/log_file） |
| `get_external_trackers()` | 合并外部 URL Tracker + qB 现有种子 Tracker，带缓存 |
| `CancelDownload` | 取消指定文件下载（优先级设为 0） |
| `RenameFile` | 重命名种子内单个文件 |
| `RenameTorrent` | 重命名整个种子 |
| `RenameFolder` | 重命名种子内顶级文件夹 |
| `QBController` | 连接 qB、扫描种子、Tracker 增删查 |
| `update_trackers()` | 增量更新 Tracker（只更新最近添加/活跃下载的种子） |
| `clear_all_trackers()` | 清除所有种子的 Tracker（谨慎使用，耗时） |
| `Manager` | 主管理器：加载规则 → 扫描 → 过滤/重命名/目录重命名 → 取消下载 |
| `main()` | 程序入口：运行 Manager，然后更新 Tracker |

**关键常量**：
- `NEW_TORRENT_THRESHOLD = 10 * 60`：10 分钟内添加的种子视为"新添加"
- `ACTIVE_STATES`：活跃下载状态列表（downloading/stalledDL/metaDL 等）

### 4.2 `qb_utils.py` — 实体与工具

| 组件 | 职责 |
|------|------|
| `parse_size()` | 将 `10M/2G/5KB` 解析为字节数 |
| `sanitize_name()` | 清理文件名（移除所有空白字符） |
| `chinese_count()` | 统计中文字符数量 |
| `extract_filename_noext()` | 提取不含扩展名的文件名 |
| `get_top_folder()` | 获取文件列表的顶级文件夹名称 |
| `File` 类 | 文件对象（id/name/size/priority/ext） |
| `Torrent` 类 | 种子对象（hash/name） |
| `Action` 类 | 操作基类（定义 `execute()` 接口） |
| `choose_best_name()` | 从候选名称中选中文最多者作为最佳种子名 |
| `remove_by_match()` | 根据通配符模式删除文本匹配内容 |

### 4.3 `RuleEngine_utils.py` — 规则引擎

| 组件 | 职责 |
|------|------|
| `Condition` | 匹配条件（filename/ext/min_size/max_size），条件间为 **OR** 关系 |
| `Rule` | 规则对象（含 Condition + 原始文本） |
| `RuleEngine` | 规则引擎：加载/热加载、匹配、重命名、调试匹配 |
| `MockRaw` / `MockTorrent` | 测试用模拟对象（`__main__` 中用于调试） |

**规则文件格式**（`rules.txt`）：
- 每行用 `;` 分隔多个条件，命中任一条件即匹配（OR）
- `filename:*xx*`：shell 通配符匹配文件名（转小写）
- `ext:.mp4`：扩展名匹配（可逗号分隔多个）
- `min_size:X` / `max_size:X`：大小限制（支持 K/M/G/T 单位）
- `replace:X`：删除文件夹/文件名中的字符串（通配符 `*` 非贪婪匹配）

---

## 5. 技术栈与环境

- **语言**：Python 3.6+
- **依赖**（`requirements.txt`）：`qbittorrent_api`、`Requests`、`loguru`
- **日志**：`loguru`，默认写法 `logger.info/debug/warning/error`
- **网络**：外部 Tracker 拉取走 `requests.get`，超时 10 秒；`commit.sh` 中 Git 代理端口为 `7890`

---

## 6. 关键设计约定（修改时必须遵循）

1. **操作类继承 `Action` 基类**：所有操作（取消/重命名等）必须继承 `Action` 并实现 `execute(client)` 方法。
2. **Dry Run 模式**：所有会改动 qB 的操作类中，`execute()` 开头必须检查 `CONFIG["dry_run"]`，为 True 时仅打 `[DRY]` 日志并 `return`。
3. **规则热加载**：`RuleEngine.load()` 通过比对 `mtime` 判断是否需要重载；新增配置/规则时必须保持此机制。
4. **实体使用 `raw` 数据源**：`File`/`Torrent` 通过 qBittorrent API 的原始 `raw` 对象初始化。
5. **任何修改 qB 状态的动作都需 try/except 容错**，并打 `logger.error` 日志，避免单种子异常中断整个扫描流程。
6. **代码注释**：所有函数/类必须有中文 Docstring，关键逻辑加逐行中文注释（沿用现有风格）。
7. **主循环已取消**：当前为"单次运行 + cron 调度"模式，`Manager.run()` 中的 `while True` 与 `time.sleep` 已注释。
8. **稳定代码优先原则（重要）**：当前代码是**经过长期实际使用和测试、被证明稳定可靠**的。任何修改都必须在保持既有行为稳定的前提下进行：
   - **禁止为追求"更优雅"而随意重构**稳定代码。
   - 修改前先充分理解现有逻辑，最小化改动范围，不要改动无关部分。
   - 保持向后兼容，不破坏已验证的功能行为。
9. **修改后必须完整测试（重要）**：每次功能修改完成后，都必须**完整测试所有功能**，确保改动没有破坏既有行为：
   - 测试重点：规则过滤、文件/种子/文件夹重命名、中文名称选择、规则热加载、Tracker 更新、Dry Run 模式。
   - 可运行 `python3 RuleEngine_utils.py` 进行规则引擎的 Mock 自测。
   - 必要时在真实环境（或将 `CONFIG["dry_run"]` 置 `True` 的模拟环境）全流程运行 `python3 qbmanager.py` 验证。
   - **测试未通过不得提交。**
10. **提交规范（重要）**：测试全部通过后，**参考 `commit.sh` 中的代码提交到 git**：
    - 提交前先设置 Git 用户与代理（代理端口 `7890`），参考 `commit.sh` 中的 `git config` 与 `git add -A`、`git commit`、`git push origin` 流程。
    - 提交信息应清晰描述本次改动内容（避免沿用 `commit.sh` 里占位的 `"...."`，应写有意义的 message）。
    - 推送完成后按 `commit.sh` 中方式取消代理。

---

## 7. 维护规则（重要）

> ⚠️ **每次有功能修改、较大的修改或新需求时，必须同步更新本文件。**

当你对项目做出以下任一改动，务必同步更新 `AGENTS.md` 的对应章节：

- **新增/删除/重命名模块或文件** → 更新「项目结构」和「模块职责说明」
- **新增/修改/删除功能点** → 更新「核心功能」和「模块职责说明」
- **新增/修改操作类（Action 子类）** → 更新 `qbmanager.py` 表格
- **新增/修改规则语法** → 更新「RuleEngine 规则文件格式」及 RuleEngine 表格
- **修改技术栈/依赖** → 更新「技术栈与环境」和 `requirements.txt`
- **新增/修改设计约定**（如新的模式、构造约定）→ 更新「关键设计约定」
- **修改运行方式/调度** → 更新「项目概述」和「关键设计约定」

### 强制流程（每次改动必须走完）

1. **理解稳定代码**：修改前先读懂现有逻辑，明确改动边界，最小化改动范围。
2. **完成功能代码修改**：遵循「关键设计约定」，保持向后兼容。
3. **同步更新 `AGENTS.md`**：审视本次改动影响的章节，编辑相应内容。
4. **完整测试**：按「关键设计约定」第 9 条完整测试所有功能，确认未破坏既有行为。
5. **提交推送**：测试通过后，按「关键设计约定」第 10 条参考 `commit.sh` 提交并推送 git。

> ⚠️ **测试未通过不得提交；`AGENTS.md` 未同步、未与本文件描述一致不得提交。**

