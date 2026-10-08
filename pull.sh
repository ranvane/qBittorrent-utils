#!/bin/bash
# 拉取最新代码 
echo "设置 Git 用户信息"
git config --global user.name "ranvane"
git config --global user.email "ranvane@gmail.com"

echo "设置 Git 代理"
# 根据需要切换注释掉的代理类型
git config --global http.proxy "socks5://127.0.0.1:7890"
git config --global https.proxy "socks5://127.0.0.1:7890"

git fetch origin
git reset --hard origin/main
echo -e "代码已更新至：$(git log --oneline -1)"

echo "取消 Git 代理"
git config --global --unset http.proxy
git config --global --unset https.proxy