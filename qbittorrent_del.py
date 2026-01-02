#!/usr/bin/env python3
import qbittorrentapi
import os
import time
import re
from pathlib import Path
from pathlib import PurePosixPath
from loguru import logger
import random
import string


from regex_pattern import (
    cancel_download_list,
    replace_list,
    file_extensions,
    domain_suffix_pattern,
    image_suffix_pattern,
)


BASE_DIR = os.path.dirname(__file__)
completed_dir = "/vol1/1000/download/complete/"

replace_regex_list = [re.compile(regex, re.IGNORECASE) for regex in replace_list]


# 连接到 qBittorrent 客户端
def connect_to_qbittorrent():
    client = qbittorrentapi.Client(
        host="192.168.10.200", port=8080, username="ranvane", password="fjgh1148028"
    )
    try:
        client.auth_log_in()
        logger.info("成功连接到 qBittorrent 客户端")
        return client
    except qbittorrentapi.LoginFailed as e:
        logger.info(f"连接到 qBittorrent 客户端失败：{e}")
        return None


def disconnect_from_qbittorrent(client):
    try:
        client.auth_log_out()
        logger.info("已断开与 qBittorrent 客户端的连接")
    except Exception as e:
        logger.error(f"断开与 qBittorrent 客户端的连接失败：{e}")


def extract_chinese_characters(text):
    """
    提取字符串中的所有中文字符。

    :param text: 输入的字符串
    :return: 包含所有中文字符的列表
    """
    pattern = re.compile(r"[\u4e00-\u9fa5]")
    chinese_chars = pattern.findall(text)
    chinese_chars = "".join(chinese_chars)
    if len(chinese_chars) > 0:
        return chinese_chars
    else:
        return ""


def get_top_folder_name(torrent):
    """
    获取种子最顶级的文件夹
    """
    top_folder = ""
    for file in torrent.files:
        if file.priority > 0:  # 优先级大于0的文件
            p = Path(file.name)
            # tmp_name = p.parts[0].replace("/", "")
            top_folder = p.parts[0]

    return top_folder


def generate_random_string(length=3):
    """生成指定长度的随机字符串，默认长度为3"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


# 重命名包含指定字符串的文件夹
def replace_folders_name(client, replace_str_list):
    """
    重命名包含指定字符串的文件夹，对于bt来说，只替换最顶层的文件夹

    参数：
    client（qbittorrentapi.Client）：与qBittorrent客户端的连接对象，用于获取种子信息和执行操作。
    replace_str_list（list of str）：包含要替换的字符串的列表，或者是用于匹配文件夹名称的正则表达式字符串列表。

    """
    logger.info("重命名包含指定字符串的文件夹（replace_folders_name）...")
    # 使用列表推导式批量编译这些正则表达式
    regex_list = [re.compile(regex) for regex in replace_str_list]
    for torrent in client.torrents.info():
        for file in torrent.files:
            # 创建Path实例
            p = Path(file.name)

            # 提取文件名的最顶层文件夹部分
            top_folder = p.parts[0]

            for regex in regex_list:

                new_folder_path = re.sub(regex, "", top_folder)
                if new_folder_path == top_folder:
                    continue

                new_folder_path = new_folder_path.replace(" ", "")
                try:
                    if new_folder_path != top_folder and len(new_folder_path) > 0:

                        client.torrents_rename_folder(
                            torrent_hash=torrent.hash,
                            old_path=top_folder,
                            new_path=new_folder_path,
                        )
                        time.sleep(0.5)
                except Exception as e:
                    logger.error(
                        f"种子《{torrent.name}》重命名文件夹失败：  \n使用正则表达式：{regex.pattern}\n`{top_folder}` -> `{new_folder_path}` \n{e}"
                    )
                    break


# 重命名包含指定字符串的文件
def rename_files(client, replace_patterns, delay=0.2):
    """
    重命名包含指定字符串的文件。

    遍历 qBittorrent 客户端中的所有种子文件，并对文件名进行替换操作。
    使用正则表达式匹配文件名中的字符串（忽略大小写）。

    参数:
        client: qBittorrent 客户端对象，用于获取种子信息和执行操作。
        replace_patterns: 正则表达式字符串列表，用于匹配文件名中需要替换的部分。
        delay: 两次操作之间的延迟（默认 0.2 秒）。

    返回值:
        无
    """
    # 如果没有提供任何正则表达式，则跳过文件重命名操作
    if not replace_patterns:
        logger.info("未提供任何正则表达式，跳过文件重命名操作。")
        return

    logger.info("开始重命名包含指定字符串的文件...")
    # 编译正则表达式列表，忽略大小写
    replace_patterns = [
        re.compile(pattern, re.IGNORECASE) for pattern in replace_patterns
    ]

    # 遍历所有种子
    for torrent in client.torrents.info():
        # 遍历种子中的所有文件并且文件是否有优先级且有文件扩展名
        for file in torrent.files:
            # 获取文件路径
            file_path = Path(file.name)

            if file.priority > 0 and file_path.suffix:
                # 获取原始文件名
                original_file_name = file_path.name
                # 获取父目录路径
                parent_directory = str(file_path.parent) if file_path.parent else "."
                new_file_name = original_file_name
                # 遍历正则表达式列表
                for regex in replace_patterns:
                    # 使用正则表达式替换文件名中的指定字符串
                    new_file_name = re.sub(regex, "", new_file_name).replace(" ", "")

                # 如果文件名替换后为空，则跳过该文件
                if not new_file_name:
                    logger.warning(f"文件名为空，跳过文件：{file.name}")
                    continue

                # 如果文件名替换后没有扩展名，则添加随机字符串和原文件扩展名
                if "." not in new_file_name:
                    new_file_name += generate_random_string() + file_path.suffix

                # 使用 PurePosixPath 构造新路径
                new_file_path = str(PurePosixPath(parent_directory) / new_file_name)

                try:
                    # 如果新文件名与原始文件名不同，则重命名文件
                    if new_file_name != original_file_name:
                        client.torrents_rename_file(
                            torrent_hash=torrent.hash,
                            old_path=file.name,
                            new_path=new_file_path,
                        )
                        logger.info(
                            f"种子：《{torrent.name}》文件重命名：\n"
                            f"{file.name} -> {new_file_path}"
                        )
                        # 延迟一段时间，避免频繁操作
                        time.sleep(delay)
                except Exception as e:
                    # 如果重命名失败，记录错误信息并继续
                    logger.error(
                        f"重命名种子：《{torrent.name}》的文件失败：\n"
                        f"文件路径：{file.name} -> {new_file_path}\n"
                        f"正则表达式：{regex.pattern}\n错误：{e}"
                    )
                continue


def cancel_downloading_files_with_extension(client, file_extensions):
    """

    这个函数用于取消下载指定后缀名的文件，其作用是遍历qBittorrent客户端中的所有种子文件，并检查每个文件的后缀名是否在给定的文件扩展名列表中。如果找到匹配的文件，并且文件的优先级大于0，函数将使用qBittorrent客户端提供的API调用来取消该文件的下载，设置其优先级为0。

    参数：
    client（qbittorrentapi.Client）：与qBittorrent客户端的连接对象，用于获取种子信息和执行操作。
    file_extensions（list of str）：包含要取消下载的文件扩展名的列表。例如，[".mp4", ".mkv"]将取消下载所有.mp4和.mkv文件。
    """
    logger.info("取消下载指定后缀名的文件...")
    for torrent in client.torrents.info():
        for file in torrent.files:

            # 创建Path实例
            p = Path(file.name)

            # 使用os.path.splitext()提取后缀
            file_extension = p.suffix

            if file.priority > 0:  # 只替换优先级大于0的文件

                if file_extension in file_extensions:
                    # logger.info(f"取消下载：{file.name} {file.priority}")
                    try:
                        client.torrents_file_priority(torrent.hash, file.index, 0)
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"取消下载：{file.name} 失败！{e} ")


def cancel_downloading_matching_regex(client, cancel_download_list):
    """
    取消下载符合正则表达式的文件和文件夹

    参数:
    client: qBittorrent客户端对象，用于获取种子信息和执行操作。
    cancel_download_list: 正则表达式字符串列表，用于匹配要取消下载的文件或文件夹名称。

    返回值:
    无

    异常:
    如果在取消下载过程中发生错误，将抛出异常。
    """
    logger.info("取消下载符合正则表达式的文件和文件夹...")
    # 使用列表推导式批量编译这些正则表达式
    regex_list = [re.compile(regex, re.IGNORECASE) for regex in cancel_download_list]
    for torrent in client.torrents.info():
        for file in torrent.files:
            _name = file.name.replace(" ", "")
            # logger.info(f"{file.name}")
            if file.priority > 0:  # 只取消优先级大于0的文件
                for regex in regex_list:
                    if regex.search(_name):
                        logger.info(
                            f"取消下载：{file.name} {file.priority} {regex.pattern}"
                        )
                        client.torrents_file_priority(torrent.hash, file.index, 0)
                        time.sleep(0.1)


def rename_torrent_name(client, replace_list):
    """
    重命名种子名
    此函数的目的是遍历qbittorrent客户端中的所有种子，找到每个种子中优先级大于0的文件，
    并以该文件的文件名（不包括扩展名）作为新的种子名。如果新种子名与原种子名不同，则进行重命名操作。
    """
    logger.info("重命名种子名(rename_torrent_name)...")

    # 1、首先处理种子名字
    for torrent in client.torrents.info():
        torrent_name = torrent.name
        _torrents_rename(client, torrent, torrent_name)

    # 2、处理种子根文件夹名和种子名中文字符数，那个长度大，则替换对方
    for torrent in client.torrents.info():
        top_folder_name = get_top_folder_name(torrent)  # 根文件夹名
        torrent_name = torrent.name  # 种子名

        if torrent_name != top_folder_name:
            top_folder_chinese_characters = extract_chinese_characters(top_folder_name)
            torrent_name_chinese_characters = extract_chinese_characters(torrent_name)

            # 根文件夹的中文字符数大于种子名中文字符数，则替换种子名
            if len(torrent_name_chinese_characters) < len(
                top_folder_chinese_characters
            ):

                _torrents_rename(client, torrent, top_folder_name)
            elif len(torrent_name_chinese_characters) > len(
                top_folder_chinese_characters
            ):  # 根文件夹的中文字符数小于种子名中文字符数，则替换根文件夹名字为种子名
                _rename_torrent_folder(client, torrent, top_folder_name, torrent_name)


def _torrents_rename(client, torrent, torrent_name):
    """
    将种子名替换为根文件夹的中文字符串
    """
    try:

        # 将种子名替换为根文件夹的中文字符串
        for regex in replace_regex_list:
            torrent_name = re.sub(regex, "", torrent_name).replace(" ", "")
        # 判断是否为空、是否和原种子名相同
        if len(torrent_name) < 1 or torrent_name == torrent.name:
            return

        client.torrents_rename(torrent.hash, new_torrent_name=torrent_name)
        logger.info(f"重命名种子:\n\t《{torrent.name}》 -> {torrent_name} \n")
        time.sleep(0.5)
        return
    except Exception as e:
        logger.error(f"重命名种子失败:\n\t《{torrent.name}》 -> {torrent_name} \n\t{e}")


def _rename_torrent_folder(client, torrent, old_torrent_folder, new_torrent_folder):
    """
    将根文件夹串替换为种子名字
    """
    try:

        for regex in replace_regex_list:

            new_torrent_folder = re.sub(regex, "", new_torrent_folder).replace(" ", "")

        # 判断是否为空、是否和原种子名相同
        if (
            len(new_torrent_folder) < 1
            or len(new_torrent_folder) < 1
            or old_torrent_folder == new_torrent_folder
        ):
            return

        client.torrents_rename_folder(
            torrent_hash=torrent.hash,
            old_path=old_torrent_folder,
            new_path=new_torrent_folder,
        )
        logger.info(
            f"将根文件夹串替换为种子名字:{torrent.name}\n\t {old_torrent_folder} ->  {new_torrent_folder} "
        )
        time.sleep(0.5)
        return
    except Exception as e:

        logger.error(
            f"种子:{torrent.name}重命名失败:\n\t{old_torrent_folder} ->  {new_torrent_folder}\n\t{e}"
        )


def set_excluded_file_names():
    """
    连接到 qBittorrent 客户端，获取排除文件名列表，并将其与本地文件中的排除文件名合并。
    合并后的列表将被设置为 qBittorrent 的新排除文件名列表，并保存到本地文件中。

    异常处理：
    - 如果连接到 qBittorrent 客户端失败，记录错误信息并返回。
    - 如果获取或设置排除文件名列表时发生异常，记录错误信息并返回。

    返回：
    - 成功时记录成功信息，失败时记录错误信息。
    """
    client = connect_to_qbittorrent()
    if client:
        try:
            # 所有配置写入文件中
            # app_preferences = client.app_preferences()

            # excluded_file_path = os.path.join(BASE_DIR, "配置文件.txt")
            # with open(excluded_file_path, "w", encoding="utf-8") as file:
            #     for key, value in app_preferences.items():
            #         file.write(f"{key}: {value}\n")

            qb_excluded_file_names = client.app_preferences()["excluded_file_names"]
            if not qb_excluded_file_names:
                qb_excluded_file_names = []
            else:
                qb_excluded_file_names = [
                    name.strip() for name in qb_excluded_file_names.split("\n")
                ]
            excluded_file_path = os.path.join(BASE_DIR, "排除的文件名.txt")
            with open(excluded_file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()
                # 去除每行末尾的换行符并生成列表
                file_excluded_file_names = [line.strip() for line in lines]

            new_excluded_file_names = []
            for item in qb_excluded_file_names + file_excluded_file_names:
                if item not in new_excluded_file_names:
                    new_excluded_file_names.append(item)
            new_excluded_file_names = "\n".join(new_excluded_file_names)

            client.app_set_preferences({"excluded_file_names": new_excluded_file_names})

            with open(excluded_file_path, "w", encoding="utf-8") as file:
                file.writelines(new_excluded_file_names)

            logger.info("成功设置排除的文件名功能")

        except Exception as e:
            logger.error(f"设置排除的文件名功能失败：{e}")
        finally:
            disconnect_from_qbittorrent(client)


def cancel_downloading_files_with_name_and_size(client):
    """

    这个函数用于取消下载文件名中包含指定字符串同时大小小于一定的文件，其作用是遍历qBittorrent客户端中的所有种子文件，并检查每个文件的后缀名是否在给定的文件扩展名列表中。如果找到匹配的文件，并且文件的优先级大于0，函数将使用qBittorrent客户端提供的API调用来取消该文件的下载，设置其优先级为0。

    参数：
    client（qbittorrentapi.Client）：与qBittorrent客户端的连接对象，用于获取种子信息和执行操作。

    """
    logger.info("取消下载文件名中包含指定字符串同时大小小于 size 的文件...")
    # 1024 * 1024 = 1 MB
    size = 5 * 1024 * 1024  # 5 MB
    excluded__names = [
        "！.mp4",
    ]
    for torrent in client.torrents.info():
        for file in torrent.files:

            if file.priority > 0:  # 只替换优先级大于0的文件
                for name in excluded__names:
                    if name in file.name and file.size > size:
                        # logger.info(f"取消下载：{file.name} {file.priority}")
                        try:
                            client.torrents_file_priority(torrent.hash, file.index, 0)
                            time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"取消下载：{file.name} 失败！{e} ")


def main():

    client = connect_to_qbittorrent()
    if client:
        try:

            cancel_downloading_files_with_extension(client, file_extensions)
            # # cancel_downloading_matching_regex(client, cancel_download_list)
            replace_folders_name(client, replace_list)
            rename_torrent_name(client, replace_list)
            rename_files(client, replace_list)
            cancel_downloading_files_with_name_and_size(client)
            set_excluded_file_names()
            # gen_del_bash()

        finally:
            disconnect_from_qbittorrent(client)


def gen_del_bash():
    bash_list = []
    excluded_file_path = os.path.join(BASE_DIR, "排除的文件名.txt")

    with open(excluded_file_path, "r", encoding="utf-8") as file:

        lines = file.readlines()
        # 去除每行末尾的换行符并生成列表
        file_excluded_file_names = [line.strip() for line in lines]
    for str in file_excluded_file_names:

        _str = f"find {completed_dir} -type f -name '{str}'"
        _str = _str.replace(".*", "*")
        bash_list.append(_str + r" -exec rm -rf {} \;")

        _str = f"find {completed_dir} -type d -name '{str}'"
        _str = _str.replace(".*", "*")
        bash_list.append(_str + r" -exec rm -rf {} \;")

    with open("qb_del.sh", "w", errors="ignore") as file:

        file.write("#!/bin/bash" + "\n\n")
        for item in bash_list:
            try:
                file.write(item + "\n")
            except Exception as e:
                logger.error(f"{e}:{item}")


if __name__ == "__main__":
    # * 0-23 * * * /usr/local/bin/python3.9  /opt/qbittorrentee/qbittorrent_del.py
    # 0 */1 * * * bash /opt/qbittorrentee/qb_del.sh
    # 0 */1 * * * bash /opt/qbittorrentee/rename.sh

    main()
