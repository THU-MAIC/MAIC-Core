from enum import StrEnum
# import StrEnum

"""
Substitutions of DictionaryEnum in MAIC-Backend.
The original implementation is an enum of dict of {value: comment},
where value and comment are enumerated as below.
"""


class MAICChatActionDict(StrEnum):
    SHOWFILE = 'showFile'           # 展示文件
    ALLOWINPUT = 'allowInput'       # 允许用户输入
    SPEAK = 'speak'                 # 发言中
    QUESTION = 'question'           # 提问
    ANSWER = 'answer'               # 提供答案
    USER_ANSWER = 'user_answer'     # 用户答案
    CONTROL = 'control'             # 控制流程
    ERROR = 'error'                 # 错误处理


class FunctionCallDict(StrEnum):
    SHOWFILE = 'ShowFile'           # 展示文件
    READSCRIPT = 'ReadScript'       # 读脚本
    ASKQUESTION = 'AskQuestion'     # 提问


class IdentityDict(StrEnum):
    CREATOR = '0'       # 主讲教师
    TEACHER = '1'       # 教师
    ASSISTANT = '2'     # 助教
    STUDENT = '3'       # 学生
    SYSTEM = '4'        # 系统
    AI = '5'            # AI
    AI_TEACHER = '6'    # 老师
    AI_ASSISTANT = '7'  # 助教
    AI_STUDENT = '8'    # 同学
    SCRIPT_AGENT = '9'  # 老师


class ContentTypeDict(StrEnum):
    TEXT = 'text'
    IMAGE = 'image'
    VOICE = 'voice'
    VIDEO = 'video'
    FILE = 'file'
    OBJECT = 'object'


class ContentRenderDict(StrEnum):
    TEXT = 'text'
    IMAGE = 'image'
    VOICE = 'voice'
    VIDEO = 'video'
    MARKDOWN = 'markdown'
    HTML = 'html'
