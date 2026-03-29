# 🚀 qBittorrent Auto Manager (qBittorrent 自动管理器)

[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![qBittorrent API](https://img.shields.io/badge/qBittorrent-WebAPI-orange.svg)](https://github.com/rmartin16/qbittorrent-api)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

一个基于 Python 编写的 **qBittorrent 自动化辅助脚本**。通过调用 qBittorrent WebAPI，配合强大的自定义规则引擎，实现种子下载全生命周期的自动化管理。告别杂乱的文件命名和广告文件，让你的下载目录井井有条，同时自动优化 Tracker 提升下载速度。

## ✨ 核心功能

- 🗑️ **智能垃圾过滤**：基于正则/关键字规则，自动将广告文件、快捷方式(`.url`)或无用文本(`.txt`)的下载优先级设为 `0`，节省磁盘与带宽。
- 🏷️ **多层级智能重命名**：
  - **文件重命名**：自动剔除文件名中的广告前缀/后缀。
  - **种子与目录重命名**：智能提取最佳名称（优先匹配中文字符作为资源名），并自动重命名 qB 客户端内的种子名称及本地顶级文件夹。
- ⚡ **自动 Tracker 优化**：定时从[ngosang/trackerslist](https://ngosang.github.io/trackerslist/trackers_best.txt) 拉取最新优质 Tracker，并自动去重追加到所有种子中，大幅提升死种/慢种的下载速度（内置 1 小时缓存防封机制）。
- 🔥 **规则热加载**：修改 `rules.txt` 后无需重启程序，下一次扫描自动应用最新规则。
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
├── RuleEngine_utils.py    # 规则解析引擎，处理字符串与正则匹配
├── rules.txt              # 用户自定义的过滤与重命名规则（需自行创建）
├── .trackers_cache        # Tracker 缓存文件（脚本自动生成）
└── qbmanager.log          # 运行日志（由 loguru 自动生成，支持自动轮转）
```

## 📝 贡献与反馈

欢迎提交 Issue 报告 Bug 或分享您实用的 `rules.txt` 规则！也欢迎提交 Pull Request 完善本项目。

## 📄 许可证

本项目基于[MIT License](LICENSE) 协议开源，请自由使用、修改和分发。

---
