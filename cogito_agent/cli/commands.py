from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    handled: bool
    should_exit: bool = False
    output: str | None = None


HELP_TEXT = """可用命令：
/exit              退出程序
/reset             清空当前 session
/history           查看当前会话历史
/tools             查看已注册工具
/memory            查看长期记忆
/memory optimize   将 pending 记忆归档到长期记忆
/forget <id>       删除指定记忆
/schedules         查看本地 schedules
/plugins           查看已加载插件
/debug on          开启调试输出
/debug off         关闭调试输出
/trace last        查看上一轮请求链路
/trace <trace_id>  查看指定 trace
/proactive status  查看主动推送状态
/proactive tick    执行一次主动推送判断
/drift skills      查看后台任务技能
/drift run         执行一次后台任务
/help              查看帮助
"""
