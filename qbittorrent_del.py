#!/usr/bin/env python3
import qbittorrentapi
import os
import time
import re
from pathlib import Path
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
    return "".join(chinese_chars)


def generate_random_string(length=3):
    # 定义包含所有数字和字母的字符集
    characters = string.ascii_letters + string.digits
    # 使用random.choices生成随机字符列表，然后将其连接成字符串
    random_string = "".join(random.choices(characters, k=length))
    return random_string


# 重命名包含指定字符串的文件夹
def replace_folders_name(client, replace_str_list):
    """
    重命名包含指定字符串的文件夹，对于bt来说，只替换最顶层的文件夹

    参数：
    client（qbittorrentapi.Client）：与qBittorrent客户端的连接对象，用于获取种子信息和执行操作。
    replace_str_list（list of str）：包含要替换的字符串的列表，或者是用于匹配文件夹名称的正则表达式字符串列表。

    """
    logger.info("重命名包含指定字符串的文件夹...")
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
                new_folder_path = new_folder_path.strip()

                try:
                    if new_folder_path != p.parts[0] and len(new_folder_path) > 0:

                        client.torrents_rename_folder(
                            torrent_hash=torrent.hash,
                            old_path=p.parts[0],
                            new_path=new_folder_path,
                        )
                        time.sleep(0.5)
                except Exception as e:
                    logger.error(
                        f"种子《{torrent.name}》重命名文件夹失败：  \n`{p.parts[0]}` -> `{new_folder_path}` \n{e}"
                    )
                    break


# 重命名包含指定字符串的文件
def rename_files(client, replace_str_list):
    """
    重命名包含指定字符串的文件

    这个函数会遍历给定的qBittorrent客户端中的所有种子文件，并检查每个种子文件中的文件。
    对于每个文件，如果文件名包含在replace_str_list中的任何字符串，函数将会替换这些字符串。
    使用正则表达式来匹配字符串，并且忽略大小写。

    参数:
    client: qBittorrent客户端对象，用于获取种子信息和执行操作。
    replace_str_list: 一个正则表达式字符串列表，用于匹配文件名中的字符串。

    返回值:
    无

    异常:
    如果在重命名文件过程中发生错误，它将会被捕获并作为异常抛出。
    """
    logger.info("重命名包含指定字符串的文件...")
    # 组合新的文件名和父文件夹路径
    separator = "/"  # 指定的连接字符串
    # 使用列表推导式批量编译这些正则表达式
    regex_list = [re.compile(regex, re.IGNORECASE) for regex in replace_str_list]
    for torrent in client.torrents.info():
        for file in torrent.files:

            p = Path(file.name)

            if (
                file.priority > 0 and len(p.suffix) > 0
            ):  # 只替换优先级大于0的文件和有后缀名的文件
                for regex in regex_list:
                    file_path = file.name.split(r"/")
                    filename = file_path[-1]
                    # logger.info(
                    #     f"《{torrent.name}》\n文件路径：{file_path},\n文件名：{filename},\n后缀名：{p.suffix}"
                    # )
                    if re.search(regex, filename):

                        new_name = re.sub(regex, "", filename).strip()
                        # 检查新文件名是否为空
                        if new_name == "":
                            continue
                        # 检查新文件名中是否没有点号,如果没有点号，生成一个随机字符串,
                        # 将文件路径的前部分与随机字符串和新文件名连接起来
                        if "." not in new_name:

                            new_name = (
                                separator.join(file_path[:-1])
                                + generate_random_string()
                                + "."
                                + new_name
                            )

                        new_path = separator.join(file_path[:-1]) + separator + new_name

                        try:

                            if new_name != filename:

                                client.torrents_rename_file(
                                    torrent_hash=torrent.hash,
                                    old_path=file.name,
                                    new_path=new_path,
                                )
                                logger.info(
                                    f"重命名种子：《{torrent.name}》的文件：\n{file.name} -> \n{new_path}"
                                )
                                time.sleep(0.2)
                        except Exception as e:
                            logger.error(
                                f"重命名种子：《{torrent.name}》的文件 :\n 使用正则表达式：{regex.pattern}\n{file.name} -> {new_path}\n失败：\n{e}"
                            )
                            return


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
    logger.info("重命名种子名...")
    replace_regex_list = [re.compile(regex, re.IGNORECASE) for regex in replace_list]
    for torrent in client.torrents.info():
        tmp_name = ""
        torrent_name = torrent.name

        for file in torrent.files:
            if file.priority > 0:  # 优先级大于0的文件
                p = Path(file.name)
                tmp_name = p.parts[0].replace("/", "")

        # 1、使用正则表达式处理种子名字符,去除特定的字符
        for regex in replace_regex_list:
            torrent_name = re.sub(regex, "", torrent_name)
        if torrent_name != torrent.name:
            logger.info(f"重命名种子：《{torrent.name}》 -> {torrent_name}")
            try:
                client.torrents_rename(torrent.hash, new_torrent_name=torrent_name)
            except Exception as e:
                logger.error(
                    f"重命名种子失败：{e} \n《{torrent.name}》 -> {torrent_name}"
                )

        # 2、使用正则表达式处理种子根文件夹名字符,去除特定的字符
        for regex in replace_regex_list:
            tmp_name = re.sub(regex, "", tmp_name)
        # 3、比对根文件夹和种子名中文字符数，那个长度大，则替换对方
        if torrent_name != tmp_name:
            tmp_name_chinese_characters = extract_chinese_characters(tmp_name)
            torrent_name_chinese_characters = extract_chinese_characters(torrent_name)

            if (
                len(torrent_name_chinese_characters) == 0
                and len(tmp_name_chinese_characters) > 0
            ):
                try:
                    logger.info(f"重命名种子：《{torrent.name}》 -> {tmp_name}")
                    # 将种子名替换为根文件夹的中文字符串

                    client.torrents_rename(torrent.hash, new_torrent_name=tmp_name)
                    logger.info(
                        f"重命名种子:\n\t《{torrent.name}》 -> {tmp_name} \n\t{e}"
                    )
                    time.sleep(0.5)
                    return
                except Exception as e:
                    logger.error(
                        f"重命名种子失败:\n\t《{torrent.name}》 -> {tmp_name} \n\t{e}"
                    )
            if (
                len(torrent_name_chinese_characters) > 0
                and len(tmp_name_chinese_characters) == 0
            ):
                try:
                    client.torrents_rename_folder(
                        torrent_hash=torrent.hash,
                        old_path=torrent.name,
                        new_path=tmp_name,
                    )
                    logger.info(
                        f"重命名种子文件夹:\n\t《{torrent.name}》 -> {torrent_name} "
                    )
                    time.sleep(0.5)
                    return
                except Exception as e:

                    logger.error(
                        f"种子{torrent_name}文件夹重命名失败:\n\t《{torrent.name}》 -> {tmp_name}\n\t{e}"
                    )

            # 如果 根文件夹的中文字符数大于种子名中文字符数，则替换种子名
            if (
                len(tmp_name_chinese_characters) >= len(torrent_name_chinese_characters)
                and len(tmp_name_chinese_characters) > 0
            ):

                try:
                    logger.info(f"重命名种子：《{torrent.name}》 -> {tmp_name}")
                    # 将种子名替换为根文件夹的中文字符串

                    client.torrents_rename(torrent.hash, new_torrent_name=tmp_name)
                    logger.info(f"重命名种子:\n\t《{torrent.name}》 -> {tmp_name} \n")
                    time.sleep(0.5)
                    return
                except Exception as e:
                    logger.error(
                        f"重命名种子失败:\n\t《{torrent.name}》 -> {tmp_name} \n\t{e}"
                    )

            if (
                len(tmp_name_chinese_characters) < len(torrent_name_chinese_characters)
                and len(torrent_name_chinese_characters) > 0
            ):
                # 如果 根文件夹的中文字符数小于种子名中文字符数，
                # 使用种子名替换根文件名
                try:
                    client.torrents_rename_folder(
                        torrent_hash=torrent.hash,
                        old_path=tmp_name,
                        new_path=torrent.name,
                    )
                    logger.info(f"重命名种子:\n\t {tmp_name} ->  《{torrent.name}》 ")
                    time.sleep(0.5)
                    return
                except Exception as e:

                    logger.error(
                        f"种子:{torrent_name}重命名失败:\n\t{tmp_name} ->  《{torrent.name}》\n\t{e}"
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


def main():

    client = connect_to_qbittorrent()
    if client:
        try:

            cancel_downloading_files_with_extension(client, file_extensions)
            # cancel_downloading_matching_regex(client, cancel_download_list)
            replace_folders_name(client, replace_list)
            rename_torrent_name(client, replace_list)
            rename_files(client, replace_list)
            set_excluded_file_names()
            gen_del_bash()

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
