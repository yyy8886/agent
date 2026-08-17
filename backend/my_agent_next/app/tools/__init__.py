# app/tools/__init__.py — 工具注册表
# =============================================================================
# 所有工具在此注册，chat_service 从此导入 ALL_TOOLS 绑定到模型。
# 添加新工具：在此文件 import 并加入 ALL_TOOLS 列表即可。

from .file_read import read_file
from .file_write import write_file
from .file_edit import edit_file
from .file_glob import glob
from .file_grep import grep
from .bash import run_bash
from .web_fetch import web_fetch
from .web_search import web_search
from .ask_user import ask_user_question
from .skill_discovery import discover_skills, load_skill

ALL_TOOLS = [
    read_file, write_file, edit_file, glob, grep, run_bash,
    web_fetch, web_search, ask_user_question, discover_skills, load_skill,
]

# 工具名 → 工具的映射，用于执行时查找
TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}
