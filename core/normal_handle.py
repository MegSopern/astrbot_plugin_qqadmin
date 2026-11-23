import random

from astrbot import logger
from astrbot.core.message.components import Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..data import QQAdminDB
from ..utils import (
    BAN_ME_QUOTES,
    describe_qq_error,
    extract_image_url,
    get_ats,
    get_nickname,
)


class NormalHandle:
    def __init__(self, config: PluginConfig, db: QQAdminDB):
        self.cfg = config
        self.db = db

    async def set_group_ban(
        self,
        event: AiocqhttpMessageEvent,
        ban_time: int | None = None,
        target_id: str | int = "",
    ):
        group_config = self.db.get_group_snapshot(event.get_group_id())
        try:
            ban_time = int(ban_time) if ban_time is not None else None
        except (ValueError, TypeError):
            ban_time = None

        if ban_time is None:
            ban_time = self.cfg.get_ban_time_with_range(
                group_config.get("random_ban_time"), None
            )
        tids = [target_id] if target_id else get_ats(event)
        results = []
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            try:
                await event.bot.set_group_ban(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    duration=ban_time,
                )
                results.append(f"{target_name}({tid})已被禁言{ban_time}秒")
            except Exception:
                results.append(f"{target_name}({tid})禁言失败")
        event.stop_event()
        return "\n".join(results) if results else "未指定要禁言的用户"

    async def set_group_ban_me(
        self, event: AiocqhttpMessageEvent, ban_time: int | None = None
    ):
        """禁我 60"""
        ban_time = self.cfg.get_ban_time(ban_time)
        try:
            await event.bot.set_group_ban(
                group_id=int(event.get_group_id()),
                user_id=int(event.get_sender_id()),
                duration=ban_time,
            )
            await event.send(event.plain_result(random.choice(BAN_ME_QUOTES)))
        except Exception:
            await event.send(event.plain_result("我可禁言不了你"))
        event.stop_event()

    async def set_group_whole_ban(self, event: AiocqhttpMessageEvent, enable: bool):
        await event.bot.set_group_whole_ban(
            group_id=int(event.get_group_id()), enable=enable
        )
        return "已开启全体禁言" if enable else "已关闭全体禁言"

    async def set_group_card(
        self,
        event: AiocqhttpMessageEvent,
        target_id: str | int = "",
        target_card: str | int = "",
    ):
        tids = ([target_id] if target_id else get_ats(event)) or [event.get_sender_id()]
        results = []
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            try:
                await event.bot.set_group_card(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    card=str(target_card),
                )
            except Exception as e:
                logger.warning(f"修改{tid}的群昵称失败：{e}")
                results.append(f"修改{target_name}的群昵称失败（Bot 需为管理员/群主）")
                continue
            results.append(
                f"已修改{target_name}的群昵称为【{target_card}】"
                if target_card
                else f"已清除{target_name}的群昵称"
            )
        return "\n".join(results) if results else "未指定要设置群昵称的用户"

    async def set_group_card_me(
        self,
        event: AiocqhttpMessageEvent,
        target_card: str | int | None = None,
    ):
        """改我 xxx"""
        target_card = str(target_card) if target_card else ""
        try:
            await event.bot.set_group_card(
                group_id=int(event.get_group_id()),
                user_id=int(event.get_sender_id()),
                card=str(target_card),
            )
        except Exception as e:
            logger.warning(f"修改自己的群昵称失败：{e}")
            await event.send(event.plain_result("修改你的群昵称失败，详见插件日志"))
            return
        await event.send(
            event.plain_result(
                f"已修改你的群昵称为【{target_card}】"
                if target_card
                else "已清除你的群昵称"
            )
        )

    async def _get_bot_role(self, event: AiocqhttpMessageEvent) -> str | None:
        """获取 Bot 在本群的身份，获取失败返回 None"""
        try:
            info = await event.bot.get_group_member_info(
                group_id=int(event.get_group_id()),
                user_id=int(event.get_self_id()),
                no_cache=True,
            )
        except Exception:
            return None
        return info.get("role")

    async def owner_role_error(self, event: AiocqhttpMessageEvent) -> str | None:
        """头衔只能由群主设置，Bot 不是群主时返回提示文本"""
        role = await self._get_bot_role(event)
        if role in (None, "owner"):
            return None
        role_cn = {"admin": "管理员", "member": "普通成员"}.get(role, role)
        return f"头衔只能由群主设置，Bot 当前身份是{role_cn}，无法修改头衔"

    @staticmethod
    def describe_title_error(error: Exception) -> str:
        return describe_qq_error(
            error, hint="头衔仅群主可设置，且不能超长或含特殊字符"
        )

    async def set_group_special_title(
        self,
        event: AiocqhttpMessageEvent,
        target_id: str | int = "",
        special_title: str | int = "",
    ):
        """改头衔 xxx @群友"""
        special_title = str(special_title) if special_title else ""
        if error := await self.owner_role_error(event):
            await event.send(event.plain_result(error))
            return

        tids = ([target_id] if target_id else get_ats(event)) or [event.get_sender_id()]
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            try:
                await event.bot.set_group_special_title(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    special_title=special_title,
                    duration=-1,
                )
            except Exception as e:
                logger.warning(f"设置{tid}的头衔失败：{e}")
                await event.send(
                    event.plain_result(
                        f"设置{target_name}的头衔失败：{self.describe_title_error(e)}"
                    )
                )
                continue
            await event.send(
                event.plain_result(
                    f"已修改{target_name}的头衔为【{special_title}】"
                    if special_title
                    else f"已清除{target_name}的头衔"
                )
            )

    async def set_group_special_title_me(
        self, event: AiocqhttpMessageEvent, new_title: str | int | None = None
    ):
        """申请头衔 xxx"""
        new_title = str(new_title) if new_title else ""
        if error := await self.owner_role_error(event):
            await event.send(event.plain_result(error))
            return

        try:
            await event.bot.set_group_special_title(
                group_id=int(event.get_group_id()),
                user_id=int(event.get_sender_id()),
                special_title=new_title,
                duration=-1,
            )
        except Exception as e:
            logger.warning(f"申请头衔失败：{e}")
            await event.send(
                event.plain_result(f"设置你的头衔失败：{self.describe_title_error(e)}")
            )
            return
        await event.send(
            event.plain_result(
                f"已将你的头衔改为【{new_title}】" if new_title else "已清除你的头衔"
            )
        )

    async def set_group_kick(
        self, event: AiocqhttpMessageEvent, target_id: str | int = ""
    ):
        tids = [target_id] if target_id else get_ats(event)
        results = []
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            try:
                await event.bot.set_group_kick(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    reject_add_request=False,
                )
            except Exception as e:
                logger.warning(f"踢出{tid}失败：{e}")
                results.append(
                    f"踢出【{tid}-{target_name}】失败（Bot 需为管理员/群主，或对方是群主）"
                )
                continue
            results.append(f"已将【{tid}-{target_name}】踢出本群")
        return "\n".join(results) if results else "未指定要踢出的用户"

    async def set_group_block(
        self, event: AiocqhttpMessageEvent, target_id: str | int = ""
    ):
        gid = event.get_group_id()
        tids = [target_id] if target_id else get_ats(event)
        results = []
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            await event.bot.set_group_kick(
                group_id=int(gid),
                user_id=int(tid),
                reject_add_request=True,
            )
            await self.db.add(gid, "block_ids", str(tid))
            results.append(f"已将【{tid}-{target_name}】踢出本群并拉黑!")
        return "\n".join(results) if results else "未指定要拉黑的用户"

    @staticmethod
    async def _get_member_role(event: AiocqhttpMessageEvent, user_id: str | int) -> str:
        """获取群成员角色（owner/admin/member），失败或未知返回空串"""
        try:
            info = (
                await event.bot.get_group_member_info(
                    group_id=int(event.get_group_id()),
                    user_id=int(user_id),
                    no_cache=True,
                )
                or {}
            )
        except Exception as e:
            logger.debug(f"获取 {user_id} 的群角色失败：{e}")
            return ""

        if isinstance(info, dict) and not info.get("role"):
            data = info.get("data")
            if isinstance(data, dict):
                info = data
        if not isinstance(info, dict):
            return ""
        return str(info.get("role", "")).strip().lower()

    async def set_group_admin(self, event: AiocqhttpMessageEvent, enable: bool):
        """上管/下管：逐个校验目标身份并调用接口，单个失败不影响其他目标"""
        gid = int(event.get_group_id())
        action = "设置" if enable else "取消"
        tids = get_ats(event)
        if not tids:
            return "未指定要操作的用户"

        bot_role = await self._get_member_role(event, event.get_self_id())
        if bot_role and bot_role != "owner":
            return f"我目前不是群主，无法{action}管理员"

        results = []
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            target = f"{target_name}({tid})"

            role = await self._get_member_role(event, tid)
            if role == "owner":
                results.append(f"{target} 是群主，不能{action}管理员")
                continue
            if enable and role == "admin":
                results.append(f"{target} 已经是管理员")
                continue
            if not enable and role and role != "admin":
                results.append(f"{target} 不是管理员，无需取消")
                continue

            try:
                await event.bot.set_group_admin(
                    group_id=gid, user_id=int(tid), enable=enable
                )
            except Exception as e:
                logger.warning(f"{action}{target}的管理员身份失败：{e}")
                results.append(
                    f"{target} {action}管理员失败：{describe_qq_error(e)}"
                )
                continue

            results.append(
                f"{target} 已被设为管理员"
                if enable
                else f"{target} 的管理员身份已被取消"
            )
        return "\n".join(results)

    async def set_essence_msg(
        self,
        event: AiocqhttpMessageEvent,
        enable: bool,
        message_id: str | int = "",
    ):
        if not message_id:
            chain = event.get_messages()
            first_seg = chain[0] if chain else None
            if not isinstance(first_seg, Reply):
                return "未指定要设置精华的消息"
            message_id = first_seg.id
        try:
            if enable:
                await event.bot.set_essence_msg(message_id=int(message_id))
            else:
                await event.bot.delete_essence_msg(message_id=int(message_id))
        except Exception as e:
            logger.warning(f"设置精华失败：{e}")
            return "设置精华失败（Bot 需为管理员/群主，且该消息需可设为精华）"
        return "已设为精华消息" if enable else "已取消精华消息"

    async def get_essence_msg_list(self, event: AiocqhttpMessageEvent):
        """查看群精华"""
        essence_data = await event.bot.get_essence_msg_list(
            group_id=int(event.get_group_id())
        )
        if not essence_data:
            return "没有群精华消息"
        return f"{essence_data}"

    async def set_group_portrait(
        self, event: AiocqhttpMessageEvent, image_url: str | None = None
    ):
        image_url = image_url or extract_image_url(chain=event.get_messages())
        if not image_url:
            return "未获取到新头像"
        await event.bot.set_group_portrait(
            group_id=int(event.get_group_id()),
            file=image_url,
        )
        return "群头像已更新"

    async def set_group_name(
        self, event: AiocqhttpMessageEvent, group_name: str | int | None = None
    ):
        if not group_name:
            return "未输入新群名"
        await event.bot.set_group_name(
            group_id=int(event.get_group_id()), group_name=str(group_name)
        )
        return f"本群群名更新为：{group_name}"
