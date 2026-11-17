import inspect
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from enum import IntEnum
from functools import wraps
from pathlib import Path
from typing import Any, cast

from astrbot import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .data import QQAdminDB
from .utils import get_ats


class PermLevel(IntEnum):
    """
    定义用户的权限等级。数字越小，权限越高。
    """

    SUPERUSER = 0
    OWNER = 1
    ADMIN = 2
    SUBADMIN = 3
    HIGH = 4
    MEMBER = 5
    UNKNOWN = 6

    def __str__(self):
        return {
            PermLevel.SUPERUSER: "超管",
            PermLevel.OWNER: "群主",
            PermLevel.ADMIN: "管理员",
            PermLevel.SUBADMIN: "次管理员",
            PermLevel.HIGH: "高等级成员",
            PermLevel.MEMBER: "成员",
            PermLevel.UNKNOWN: "未知/无权限",
        }.get(self, "未知/无权限")

    @classmethod
    def from_str(cls, perm_str: str):
        mapping = {
            "超管": cls.SUPERUSER,
            "群主": cls.OWNER,
            "管理员": cls.ADMIN,
            "次管理员": cls.SUBADMIN,
            "高等级成员": cls.HIGH,
            "成员": cls.MEMBER,
            "未知": cls.UNKNOWN,
            "无权限": cls.UNKNOWN,
        }
        return mapping.get(str(perm_str).strip(), cls.UNKNOWN)


class PermissionManager:
    _initialized = False

    def __init__(self):
        self.cfg: PluginConfig | None = None
        self.db: QQAdminDB | None = None

    def lazy_init(self, config: PluginConfig, db: QQAdminDB):
        if self._initialized:
            raise RuntimeError("PermissionManager already initialized")
        self.cfg = config
        self.db = db
        self._initialized = True

    def refresh(self, config: PluginConfig, db: QQAdminDB | None = None):
        self.cfg = config
        if db is not None:
            self.db = db
        self._initialized = True

    def get_group_level_threshold(self, group_id: str) -> int:
        group_config = (
            self.db.get_group_snapshot(group_id)
            if self.db is not None
            else {"level_threshold": self.cfg.level_threshold if self.cfg else 50}
        )
        return int(group_config.get("level_threshold", 50))

    def get_group_perms(self, group_id: str) -> dict:
        group_config = (
            self.db.get_group_snapshot(group_id)
            if self.db is not None
            else {"perms": self.cfg.perms if self.cfg else {}}
        )
        return group_config.get("perms", {}) or {}

    async def get_perm_level(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | int,
        group_id: str | int | None = None,
    ) -> PermLevel:
        from .core.custom_perm_handle import custom_perm_manager

        group_id = str(group_id or event.get_group_id())
        user_id = str(user_id)
        if not group_id.isdigit() or not user_id.isdigit():
            return PermLevel.UNKNOWN
        if int(group_id) == 0 or int(user_id) == 0:
            return PermLevel.UNKNOWN
        if self.cfg and user_id in self.cfg.admins_id:
            return PermLevel.SUPERUSER

        # 兼容 ranranbot_chatmanage 插件的额外审批人配置
        extra_approvers: list[str] = []
        ranran_config_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "ranranbot_chatmanage_config.json"
        )
        try:
            with open(ranran_config_path, "r", encoding="utf-8-sig") as f:
                extra_approvers = [
                    str(i)
                    for i in json.load(f).get("qqadmin", {}).get(
                        "extra_approvers", []
                    )
                ]
        except Exception:
            extra_approvers = []

        custom_extra_owners = custom_perm_manager.get_group_extra_owners(group_id)
        custom_extra_admins = custom_perm_manager.get_group_extra_admins(group_id)
        custom_extra_subadmins = custom_perm_manager.get_group_extra_subadmins(group_id)

        try:
            info = await event.bot.get_group_member_info(
                group_id=int(group_id), user_id=int(user_id), no_cache=True
            )
        except Exception:
            return PermLevel.UNKNOWN

        role = info.get("role", "unknown")
        level = int(info.get("level", 0))
        level_threshold = self.get_group_level_threshold(group_id)

        if user_id in custom_extra_owners:
            return PermLevel.OWNER

        match role:
            case "owner":
                return PermLevel.OWNER
            case "admin":
                return PermLevel.ADMIN

        if user_id in custom_extra_admins:
            return PermLevel.ADMIN

        # 群审批管理拥有次管理员权限（优先级低于群主/管理员）
        if user_id in extra_approvers or user_id in custom_extra_subadmins:
            return PermLevel.SUBADMIN

        match role:
            case "member":
                return (
                    PermLevel.HIGH if level >= level_threshold else PermLevel.MEMBER
                )
            case _:
                return PermLevel.UNKNOWN

    def get_required_level(self, group_id: str, perm_key: str) -> PermLevel:
        """获取某群某指令所需权限，优先使用该群独立配置的权限"""
        from .core.custom_perm_handle import custom_perm_manager

        custom_perm_str = custom_perm_manager.get_group_perm(group_id, perm_key)
        if custom_perm_str:
            return PermLevel.from_str(custom_perm_str)
        perms = self.get_group_perms(group_id)
        return PermLevel.from_str(str(perms.get(perm_key, "管理员")))

    async def perm_block(
        self,
        event: AiocqhttpMessageEvent,
        bot_perm: PermLevel,
        perm_key: str,
        check_at: bool = True,
    ) -> str | None:
        group_id = str(event.get_group_id())
        user_level = await self.get_perm_level(event, user_id=event.get_sender_id())

        # 未指定权限，则默认至少需要管理员权限
        required_level = self.get_required_level(group_id, perm_key)

        if user_level > required_level:
            return f"你没{required_level}权限"

        bot_level = await self.get_perm_level(event, user_id=event.get_self_id())
        if bot_level > bot_perm:
            return f"我没{bot_perm}权限"

        if check_at:
            for at_id in get_ats(event):
                at_level = await self.get_perm_level(event, user_id=at_id)
                if bot_level >= at_level:
                    return f"我动不了{at_level}"

        return None

    async def llm_perm_block(
        self,
        event: AiocqhttpMessageEvent,
        perm_key: str,
        bot_perm: PermLevel = PermLevel.ADMIN,
    ) -> str | None:
        if event.platform_meta.name != "aiocqhttp":
            return "该工具仅支持通过 QQ 群聊调用"

        if event.is_private_chat():
            return "该工具仅支持在 QQ 群聊中调用"

        if not self._initialized:
            logger.error(
                "PermissionManager is not initialized while checking LLM tool permission: %s",
                perm_key,
            )
            return "内部错误：权限系统尚未正确加载"

        return await self.perm_block(
            event,
            bot_perm=bot_perm,
            perm_key=perm_key,
            check_at=False,
        )


perm_manager = PermissionManager()


def perm_required(
    bot_perm: PermLevel = PermLevel.ADMIN,
    perm_key: str | None = None,
    check_at: bool = True,
    allow_private: bool = False,
):
    """
    权限检查装饰器。
    :param perm_key: 可选。用户执行命令所需的最低权限键名，默认使用被装饰函数的函数名。
    :param bot_perm: Bot 执行此命令所需的最低权限等级。
    :param check_at: 是否检查“是否有权对被@者实施操作”。
    :param allow_private: 是否允许在私信中执行（私信不做权限校验，由指令内部自行鉴权）。
    """

    def decorator(
        func: Callable[..., AsyncGenerator[Any, Any] | Awaitable[Any]],
    ) -> Callable[..., AsyncGenerator[Any, Any]]:
        actual_perm_key = perm_key or func.__name__

        @wraps(func)
        async def wrapper(
            plugin_instance: Any,
            event: AiocqhttpMessageEvent,
            *args: Any,
            **kwargs: Any,
        ) -> AsyncGenerator[Any, Any]:

            # 仅限aiocqhttp
            if event.platform_meta.name != "aiocqhttp":
                return

            # 私信处理：仅放行允许私信执行的指令，权限由指令内部校验
            if event.is_private_chat():
                if not allow_private:
                    return
                if inspect.isasyncgenfunction(func):
                    async for item in func(plugin_instance, event, *args, **kwargs):
                        yield item
                else:
                    await cast(
                        Awaitable[Any], func(plugin_instance, event, *args, **kwargs)
                    )
                return

            # 权限管理未初始化
            if not perm_manager._initialized:
                logger.error(
                    f"PermissionManager 未初始化（尝试访问权限项：{perm_key}）"
                )
                yield event.plain_result("内部错误：权限系统未正确加载")
                event.stop_event()
                return

            # 判断权限
            result = await perm_manager.perm_block(
                event, bot_perm=bot_perm, perm_key=actual_perm_key, check_at=check_at
            )
            if result:
                yield event.plain_result(result)
                event.stop_event()
                return

            # 执行原始方法
            if inspect.isasyncgenfunction(func):
                async for item in func(plugin_instance, event, *args, **kwargs):
                    yield item
            else:
                await cast(
                    Awaitable[Any], func(plugin_instance, event, *args, **kwargs)
                )

        return wrapper

    return decorator
