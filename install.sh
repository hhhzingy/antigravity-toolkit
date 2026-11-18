#!/usr/bin/env bash
# Antigravity Toolkit - Ubuntu / Linux 一键交互式安装与管理向导
#
# 用法示例:
#   ./install.sh                       启动交互式数字菜单（推荐新手使用）
#   ./install.sh --all                 一键安装全部推荐增强模块
#   ./install.sh --module 1            按编号安装指定模块 (如 1, 2, 3 或 1,2)
#   ./install.sh --doctor              运行环境与安装状态健康自检
#   ./install.sh --uninstall           卸载全部已安装增强模块
#   ./install.sh --uninstall --module 2 单独卸载指定模块 (如 1, 2, 3)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ANSI color helpers (automatically disabled when stdout is not a terminal or NO_COLOR is set)
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET="\033[0m"
  C_BOLD="\033[1m"
  C_CYAN="\033[36m"
  C_GREEN="\033[32m"
  C_YELLOW="\033[33m"
  C_RED="\033[31m"
  C_DIM="\033[2m"
else
  C_RESET=""
  C_BOLD=""
  C_CYAN=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
  C_DIM=""
fi

show_usage() {
  echo ""
  echo -e "${C_BOLD}${C_CYAN}Antigravity Toolkit (Ubuntu / Linux) 使用说明${C_RESET}"
  echo -e "${C_DIM}------------------------------------------------------------${C_RESET}"
  echo "  ./install.sh                        启动可视化数字菜单（默认推荐）"
  echo "  ./install.sh --all                  一键安装全部推荐增强模块"
  echo "  ./install.sh --module 1             按编号安装指定模块 (如 1, 2, 3)"
  echo "  ./install.sh --module 2,3           同时安装多个指定模块"
  echo "  ./install.sh --doctor               运行环境与安装状态自检 (Doctor)"
  echo "  ./install.sh --uninstall            卸载全部已安装增强模块"
  echo "  ./install.sh --uninstall --module 2 单独卸载指定模块 (如 1, 2, 3)"
  echo "  ./install.sh --help                 显示本帮助说明"
  echo ""
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

run_shell_script() {
  local rel_path="$1"
  local title="$2"
  local full_path="${REPO_ROOT}/${rel_path}"

  if [[ ! -f "${full_path}" ]]; then
    echo -e "${C_RED}[错误] 未找到脚本: ${full_path}${C_RESET}"
    echo -e "${C_YELLOW}请确认您在完整的 antigravity-toolkit 仓库目录中运行此脚本。${C_RESET}"
    return 1
  fi

  echo ""
  echo -e "${C_CYAN}============================================================${C_RESET}"
  echo -e "${C_BOLD}${C_CYAN}>>> 正在执行: ${title}${C_RESET}"
  echo -e "${C_CYAN}============================================================${C_RESET}"

  if bash "${full_path}"; then
    echo ""
    echo -e "${C_GREEN}[完成] ${title} 已执行完毕！${C_RESET}"
    return 0
  else
    local rc=$?
    echo ""
    echo -e "${C_YELLOW}[提示] '${title}' 执行过程中返回了非零状态码 (${rc})。${C_RESET}"
    echo -e "${C_YELLOW}您可以运行 ./install.sh --doctor 查看详细环境诊断与修复建议。${C_RESET}"
    return "${rc}"
  fi
}

install_module() {
  local mod_id="${1,,}"
  mod_id="${mod_id//[[:space:]]/}"

  case "${mod_id}" in
    1|computer_use|computer-use)
      run_shell_script "computer_use/setup_linux.sh" "[模块 1] 桌面与浏览器极速操控 (Computer Use + Chrome 直连)"
      ;;
    2|close_guard|close-guard)
      run_shell_script "close_guard/install_close_guard.sh" "[模块 2] 防误关系统托盘驻留守护 (Close Guard)"
      ;;
    3|branch_conversation|branch-conversation|branch)
      run_shell_script "branch_conversation/install_branch_tool.sh" "[模块 3] 历史对话任意轮次分支工具 (Branch Conversation)"
      ;;
    *)
      echo -e "${C_RED}[错误] 未知的模块标识: '${1}'。可选值为 1、2、3。${C_RESET}"
      return 1
      ;;
  esac
}

uninstall_module() {
  local mod_id="${1,,}"
  mod_id="${mod_id//[[:space:]]/}"

  case "${mod_id}" in
    1|computer_use|computer-use)
      run_shell_script "computer_use/uninstall_computer_use.sh" "卸载 [模块 1] 桌面与浏览器极速操控 (Computer Use)"
      ;;
    2|close_guard|close-guard)
      run_shell_script "close_guard/uninstall_close_guard.sh" "卸载 [模块 2] 防误关系统托盘驻留守护 (Close Guard)"
      ;;
    3|branch_conversation|branch-conversation|branch)
      run_shell_script "branch_conversation/uninstall_branch_tool.sh" "卸载 [模块 3] 历史对话任意轮次分支工具 (Branch Conversation)"
      ;;
    all|a)
      uninstall_all
      ;;
    *)
      echo -e "${C_RED}[错误] 未知的卸载模块标识: '${1}'。可选值为 1、2、3 或 all。${C_RESET}"
      return 1
      ;;
  esac
}

install_all() {
  echo ""
  echo -e "${C_CYAN}即将依次为您安装全部 Antigravity 推荐增强模块...${C_RESET}"
  local ok=0
  install_module "1" || ok=1
  install_module "2" || ok=1
  install_module "3" || ok=1

  echo ""
  echo -e "${C_CYAN}============================================================${C_RESET}"
  if [[ "${ok}" -eq 0 ]]; then
    echo -e "${C_GREEN}全部推荐优化已安装完成！${C_RESET}"
    echo "温馨提示："
    echo "  1. 打开 Chrome 访问 chrome://inspect/#remote-debugging（Edge 访问 edge://inspect/#remote-debugging）并勾选 Enable remote debugging"
    echo "  2. 在 Antigravity 的 MCP Servers 面板点击 Refresh 即可开始使用"
  else
    echo -e "${C_YELLOW}部分模块未完全成功，请查看上方提示或运行 ./install.sh --doctor 进行环境自检。${C_RESET}"
  fi
  echo -e "${C_CYAN}============================================================${C_RESET}"
  return "${ok}"
}

uninstall_all() {
  echo ""
  echo -e "${C_YELLOW}即将依次清理并卸载全部 Antigravity Toolkit 增强模块...${C_RESET}"
  local ok=0
  uninstall_module "1" || ok=1
  uninstall_module "2" || ok=1
  uninstall_module "3" || ok=1
  return "${ok}"
}

run_doctor() {
  local doctor_path="${REPO_ROOT}/scripts/doctor.py"
  if [[ ! -f "${doctor_path}" ]]; then
    echo -e "${C_RED}[错误] 未找到自检脚本: ${doctor_path}${C_RESET}"
    return 1
  fi

  local py_bin
  if ! py_bin="$(find_python)"; then
    echo ""
    echo -e "${C_YELLOW}[提示] 当前系统尚未安装 Python 3，无法运行详细自检脚本。${C_RESET}"
    echo -e "请先在终端执行以下命令安装 Python 3："
    echo -e "  ${C_CYAN}sudo apt-get update && sudo apt-get install -y python3 python3-tk${C_RESET}"
    return 1
  fi

  PYTHONDONTWRITEBYTECODE=1 "${py_bin}" -B "${doctor_path}"
}

uninstall_menu() {
  echo ""
  echo -e "${C_DIM}----------------------------------------------------------------${C_RESET}"
  echo -e "  ${C_YELLOW}请选择要卸载的模块：${C_RESET}"
  echo "  [1] 卸载模块 1: 桌面与浏览器极速操控 (Computer Use)"
  echo "  [2] 卸载模块 2: 防误关系统托盘驻留守护 (Close Guard)"
  echo "  [3] 卸载模块 3: 历史对话任意轮次分支工具 (Branch Conversation)"
  echo "  [A] 卸载全部增强模块"
  echo "  [B] 返回主菜单"
  echo -e "${C_DIM}----------------------------------------------------------------${C_RESET}"

  local sub_raw=""
  if ! read -r -p "请输入卸载选项 [1/2/3/A/B]: " sub_raw; then
    return 0
  fi
  local sub_choice="${sub_raw^^}"
  sub_choice="${sub_choice//[[:space:]]/}"
  case "${sub_choice}" in
    1) uninstall_module "1" || true ;;
    2) uninstall_module "2" || true ;;
    3) uninstall_module "3" || true ;;
    A) uninstall_all || true ;;
    B|"") return 0 ;;
    *) echo -e "${C_DIM}[提示] 已取消卸载或未识别选项 '${sub_raw}'。${C_RESET}" ;;
  esac
}

interactive_menu() {
  while true; do
    echo ""
    echo -e "${C_BOLD}${C_CYAN}================================================================${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}      Antigravity Toolkit - 一键优化与安装向导 (Ubuntu/Linux)${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}================================================================${C_RESET}"
    echo "  请选择要执行的操作（输入方括号内的编号或字母后按回车）："
    echo ""
    echo -e "  ${C_GREEN}[1] 桌面与浏览器极速操控 (Computer Use + Chrome 直连)${C_RESET}"
    echo -e "      ${C_DIM}直连日常已登录浏览器、极速看屏、本地 OCR 兜底与晃动鼠标快速接管${C_RESET}"
    echo -e "  ${C_GREEN}[2] 防误关系统托盘驻留守护 (Close Guard)${C_RESET}"
    echo -e "      ${C_DIM}点击关闭按钮或按 Alt+F4 自动隐藏到系统托盘，保护后台 AI 任务${C_RESET}"
    echo -e "  ${C_GREEN}[3] 历史对话任意轮次分支工具 (Branch Conversation)${C_RESET}"
    echo -e "      ${C_DIM}按项目分组管理对话，支持从任意历史问答节点一键分叉探索新思路${C_RESET}"
    echo ""
    echo -e "  ${C_CYAN}[A] 一键安装全部推荐优化${C_RESET}"
    echo -e "  ${C_YELLOW}[D] 运行环境与状态自检 (Doctor)${C_RESET}"
    echo -e "  ${C_YELLOW}[U] 卸载已安装模块 (按模块选卸 / 全卸)${C_RESET}"
    echo "  [Q] 退出"
    echo -e "${C_DIM}----------------------------------------------------------------${C_RESET}"

    local raw_choice=""
    if ! read -r -p "请输入选项 [1/2/3/A/D/U/Q]: " raw_choice; then
      echo ""
      break
    fi

    local choice="${raw_choice^^}"
    choice="${choice//[[:space:]]/}"

    case "${choice}" in
      1) install_module "1" || true ;;
      2) install_module "2" || true ;;
      3) install_module "3" || true ;;
      A) install_all || true ;;
      D) run_doctor || true ;;
      U) uninstall_menu || true ;;
      Q)
        echo -e "${C_CYAN}已退出安装向导，祝您使用愉快！${C_RESET}"
        break
        ;;
      "")
        continue
        ;;
      *)
        echo -e "${C_YELLOW}[提示] 未识别的选项 '${raw_choice}'，请输入 1、2、3、A、D、U 或 Q。${C_RESET}"
        continue
        ;;
    esac

    if [[ ! -t 0 ]]; then
      continue
    fi
    echo ""
    local next_action=""
    if ! read -r -p "按回车键返回主菜单，或输入 Q 退出: " next_action; then
      echo ""
      break
    fi
    next_action="${next_action^^}"
    next_action="${next_action//[[:space:]]/}"
    if [[ "${next_action}" == "Q" ]]; then
      echo -e "${C_CYAN}已退出安装向导，祝您使用愉快！${C_RESET}"
      break
    fi
  done
}

# --- CLI Argument Parsing ---
DO_ALL=0
DO_DOCTOR=0
DO_UNINSTALL=0
MODULES=()

if [[ $# -eq 0 ]]; then
  interactive_menu
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all|-a|-All)
      DO_ALL=1
      shift
      ;;
    --module|-m|-Module)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo -e "${C_RED}[错误] $1 参数后需要指定模块编号（如 1、2、3）。${C_RESET}"
        show_usage
        exit 1
      fi
      MODULES+=("$2")
      shift 2
      ;;
    --module=*)
      MODULES+=("${1#*=}")
      shift
      ;;
    --doctor|-d|-Doctor)
      DO_DOCTOR=1
      shift
      ;;
    --uninstall|-u|-Uninstall)
      DO_UNINSTALL=1
      shift
      ;;
    --help|-h|-Help)
      show_usage
      exit 0
      ;;
    *)
      echo -e "${C_RED}[错误] 未知的命令行参数: $1${C_RESET}"
      show_usage
      exit 1
      ;;
  esac
done

EXIT_STATUS=0

if [[ "${DO_UNINSTALL}" -eq 1 ]]; then
  if [[ "${#MODULES[@]}" -gt 0 ]]; then
    for mod_entry in "${MODULES[@]}"; do
      IFS=',' read -r -a split_mods <<< "${mod_entry}"
      for single_mod in "${split_mods[@]}"; do
        if [[ -n "${single_mod}" ]]; then
          uninstall_module "${single_mod}" || EXIT_STATUS=1
        fi
      done
    done
  else
    uninstall_all || EXIT_STATUS=1
  fi
else
  if [[ "${DO_ALL}" -eq 1 ]]; then
    install_all || EXIT_STATUS=1
  fi

  if [[ "${#MODULES[@]}" -gt 0 ]]; then
    for mod_entry in "${MODULES[@]}"; do
      IFS=',' read -r -a split_mods <<< "${mod_entry}"
      for single_mod in "${split_mods[@]}"; do
        if [[ -n "${single_mod}" ]]; then
          install_module "${single_mod}" || EXIT_STATUS=1
        fi
      done
    done
  fi
fi

if [[ "${DO_DOCTOR}" -eq 1 ]]; then
  run_doctor || EXIT_STATUS=1
fi

exit "${EXIT_STATUS}"
