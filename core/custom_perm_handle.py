import json
import re
from pathlib import Path
from typing import Any, Dict, List

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..permission import PermLevel, perm_manager, perm_required
from ..utils import get_ats

PERM_FIELD_MAP = {
    "禁言": "set_group_ban",
    "禁我": "set_group_ban_me",
    "解禁": "cancel_group_ban",
    "全体禁言": "whole_ban",
    "全体禁言相关指令": "whole_ban",
    "全禁": "whole_ban",
    "改名": "set_group_card",
    "改我": "set_group_card_me",
    "头衔": "set_group_special_title",
    "申请头衔": "set_group_special_title_me",
    "踢了": "set_group_kick",
    "拉黑": "set_group_block",
    "设置管理员": "admin",
    "上管": "admin",
    "下管": "admin",
    "设置管理员指令": "admin",
    "操作群精华": "essence",
    "设精": "essence",
    "移精": "essence",
    "操作群精华指令": "essence",
    "群精华": "get_essence_msg_list",
    "撤回": "delete_msg",
    "发布群公告": "send_group_notice",
    "查看群公告": "get_group_notice",
    "设置群头像": "set_group_portrait",
    "设置群名": "set_group_name",
    "禁词": "word_ban",
    "内置禁词": "word_ban",
    "设置禁词": "word_ban",
    "禁词指令": "word_ban",
    "刷屏禁言": "handle_builtin_ban_words",
    "刷屏禁言指令": "handle_builtin_ban_words",
    "投票禁言": "vote",
    "投票禁言指令": "vote",
    "宵禁": "curfew",
    "宵禁指令": "curfew",
    "进群审核": "join",
    "进群审核指令": "join",
    "批准": "approve",
    "驳回": "approve",
    "批准/驳回（进群申请）": "approve",
    "进群欢迎": "welcome",
    "进群欢迎与禁言": "welcome",
    "退群通知": "leave",
    "退群通知与拉黑": "leave",
    "群友信息": "get_group_member_list",
    "清理群友": "clear_group_member",
    "上传群文件": "upload_group_file",
    "删除群文件": "delete_group_file",
    "查看群文件": "view_group_file",
    "取名": "ai_set_card",
    "取头衔": "ai_set_title",
    "群管配置": "set_config",
    "群管重置": "reset_config",
}

VALID_CUSTOM_LEVELS = {
    "超管",
    "群主",
    "管理员",
    "次管理员",
    "高等级成员",
    "成员",
    "未知",
    "无权限",
}


class CustomPermManager:
    def __init__(self):
        self.file_path: Path = None
        self.data: dict = {}

    def _ensure_group(self, group_id: str) -> dict:
        group_id = str(group_id)
        if group_id not in self.data:
            self.data[group_id] = {
                "extra_owners": [],
                "extra_admins": [],
                "extra_subadmins": [],
                "perms": {},
            }
        group_data = self.data[group_id]
        group_data.setdefault("extra_owners", [])
        group_data.setdefault("extra_admins", [])
        group_data.setdefault("extra_subadmins", [])
        group_data.setdefault("perms", {})
        return group_data

    def init(self, data_dir: Path):
        self.file_path = data_dir / "custom_group_perms.json"
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}
            self.save()

    def save(self):
        if self.file_path:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_group_perm(self, group_id: str, perm_key: str) -> str | None:
        """获取特定群聊独立配置的权限，如果没配置则返回None"""
        return self.data.get(str(group_id), {}).get("perms", {}).get(perm_key)

    def get_group_extra_owners(self, group_id: str) -> list[str]:
        """获取特定群聊独立配置的额外群主列表"""
        return self.data.get(str(group_id), {}).get("extra_owners", [])

    def get_group_extra_admins(self, group_id: str) -> list[str]:
        """获取特定群聊独立配置的额外管理员列表"""
        return self.data.get(str(group_id), {}).get("extra_admins", [])

    def get_group_extra_subadmins(self, group_id: str) -> list[str]:
        """获取特定群聊独立配置的额外次管理员列表"""
        return self.data.get(str(group_id), {}).get("extra_subadmins", [])

    def set_group_perm(self, group_id: str, perm_key: str, level_str: str):
        self.set_group_perms(group_id, {perm_key: level_str})

    def set_group_perms(self, group_id: str, perm_levels: dict[str, str]):
        group_id = str(group_id)
        if not perm_levels:
            return
        group_data = self._ensure_group(group_id)
        group_data["perms"].update(perm_levels)
        self.save()

    def add_extra_owner(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        group_data = self._ensure_group(group_id)
        if qq not in group_data["extra_owners"]:
            group_data["extra_owners"].append(qq)
        self.save()

    def add_extra_admin(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        group_data = self._ensure_group(group_id)
        if qq not in group_data["extra_admins"]:
            group_data["extra_admins"].append(qq)
        self.save()

    def add_extra_subadmin(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        group_data = self._ensure_group(group_id)
        if qq not in group_data["extra_subadmins"]:
            group_data["extra_subadmins"].append(qq)
        self.save()

    def remove_extra_admin(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        if group_id in self.data and "extra_admins" in self.data[group_id]:
            if qq in self.data[group_id]["extra_admins"]:
                self.data[group_id]["extra_admins"].remove(qq)
                self.save()

    def remove_extra_subadmin(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        if group_id in self.data and "extra_subadmins" in self.data[group_id]:
            if qq in self.data[group_id]["extra_subadmins"]:
                self.data[group_id]["extra_subadmins"].remove(qq)
                self.save()

    def remove_extra_owner(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        if group_id in self.data and "extra_owners" in self.data[group_id]:
            if qq in self.data[group_id]["extra_owners"]:
                self.data[group_id]["extra_owners"].remove(qq)
                self.save()


custom_perm_manager = CustomPermManager()


class CustomPermHandle:
    def __init__(self, config: PluginConfig):
        self.config = config
        custom_perm_manager.init(config.data_dir)

    def _resolve_group_id(self, event: AiocqhttpMessageEvent) -> str | None:
        group_id = str(event.get_group_id())
        return group_id if group_id and group_id != "0" else None

    @staticmethod
    def _dedupe_ids(ids: list[str]) -> list[str]:
        uniq: list[str] = []
        seen = set()
        for item in ids:
            if item not in seen:
                uniq.append(item)
                seen.add(item)
        return uniq

    def _resolve_target_qqs(
        self, event: AiocqhttpMessageEvent, qq: str | None
    ) -> tuple[list[str] | None, str | None]:
        at_ids = get_ats(event)
        if qq:
            raw_parts = re.split(r"[\s,，、;；]+", str(qq).strip())
            parts = [p for p in raw_parts if p]
            if not parts and not at_ids:
                return None, "请提供QQ号或@用户"

            digit_parts = [p for p in parts if p.isdigit()]
            non_digit_parts = [p for p in parts if not p.isdigit()]

            if non_digit_parts and not at_ids:
                return None, "QQ号必须是数字或@指定用户"

            combined = digit_parts + at_ids
            if combined:
                return self._dedupe_ids(combined), None

            return None, "请提供QQ号或@用户"

        if at_ids:
            return self._dedupe_ids(at_ids), None

        return None, "请提供QQ号或@用户"

    def _get_perm_display_name(self, perm_key: str) -> str:
        cn_names = [
            k
            for k, v in PERM_FIELD_MAP.items()
            if v == perm_key and not k.endswith("指令") and "（" not in k
        ]
        return cn_names[0] if cn_names else perm_key

    def _resolve_perm_key(self, perm_key: str) -> tuple[str | None, str | None]:
        perm_key = perm_key.strip()
        if not perm_key:
            return None, "权限名不能为空"

        valid_keys = self.config.perms.keys()
        if perm_key in valid_keys:
            return perm_key, None

        if perm_key in PERM_FIELD_MAP:
            return PERM_FIELD_MAP[perm_key], None

        cn_keys = [
            k
            for k, v in PERM_FIELD_MAP.items()
            if not k.endswith("指令") and "（" not in k
        ]
        return (
            None,
            f"未知的权限名：{perm_key}，可使用的中文命令/权限名有：{', '.join(cn_keys)}",
        )

    def _normalize_perm_level(self, level: str) -> str | None:
        level = level.strip()
        return level if level in VALID_CUSTOM_LEVELS else None

    async def set_custom_perm(
        self, event: AiocqhttpMessageEvent, group_id: str, perm_key: str, level: str
    ):
        """
        为特定群聊单独设置某个指令的权限
        如：/特殊群权限设置 123456 禁言 管理员
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return

        perm_key, error = self._resolve_perm_key(perm_key)
        if error:
            yield event.plain_result(error)
            return

        normalized_level = self._normalize_perm_level(level)
        if not normalized_level:
            yield event.plain_result(
                f"未知的权限等级：{level}。有效等级例如：超管、群主、管理员、次管理员、成员、未知、无权限。"
            )
            return

        custom_perm_manager.set_group_perm(group_id, perm_key, normalized_level)
        yield event.plain_result(
            f"已将群 {group_id} 的 {self._get_perm_display_name(perm_key)} 权限修改为 {normalized_level}。"
        )

    async def set_custom_perm_batch(self, event: AiocqhttpMessageEvent):
        """
        为特定群聊批量设置多个指令权限
        如：/特殊群权限批量设置 123456 禁言=次管理员 改名=管理员
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return

        raw = event.message_str.partition(" ")[2].strip()
        if not raw:
            yield event.plain_result(
                "用法：/特殊群权限批量设置 <群号> <权限名=权限等级> ...\n例如：/特殊群权限批量设置 123456 禁言=次管理员 改名=管理员"
            )
            return

        raw = raw.strip().strip("[]【】()（）").strip()
        group_part, sep, rule_text = raw.partition(" ")
        if not sep or not group_part:
            yield event.plain_result(
                "用法：/特殊群权限批量设置 <群号> <权限名=权限等级> ...\n例如：/特殊群权限批量设置 123456 禁言=次管理员 改名=管理员"
            )
            return

        group_id = group_part.strip()
        if not group_id.isdigit():
            yield event.plain_result(f"群号必须是数字：{group_id}")
            return

        items = [
            item.replace("＝", "=").strip()
            for item in re.split(r"[\s,，、;；]+", rule_text.strip())
            if item.strip()
        ]
        if not items:
            yield event.plain_result(
                "请提供至少一项权限配置，例如：/特殊群权限批量设置 123456 禁言=次管理员 改名=管理员"
            )
            return

        perm_updates: dict[str, str] = {}
        success_items: list[str] = []
        failed_items: list[str] = []

        for item in items:
            if "=" not in item:
                failed_items.append(f"{item}（缺少 =）")
                continue

            perm_name, level = item.split("=", 1)
            perm_name = perm_name.strip()
            level = level.strip()

            resolved_perm_key, error = self._resolve_perm_key(perm_name)
            if error:
                failed_items.append(f"{item}（{error}）")
                continue

            normalized_level = self._normalize_perm_level(level)
            if not normalized_level:
                failed_items.append(f"{item}（未知的权限等级：{level}）")
                continue

            perm_updates[resolved_perm_key] = normalized_level
            success_items.append(
                f"{self._get_perm_display_name(resolved_perm_key)}={normalized_level}"
            )

        if not perm_updates:
            fail_text = "；".join(failed_items) if failed_items else "没有可保存的配置"
            yield event.plain_result(f"批量设置失败：{fail_text}")
            return

        custom_perm_manager.set_group_perms(group_id, perm_updates)

        result_lines = [
            f"已为群 {group_id} 批量更新 {len(perm_updates)} 项：{', '.join(success_items)}"
        ]
        if failed_items:
            result_lines.append(
                f"未生效 {len(failed_items)} 项：{'；'.join(failed_items)}"
            )

        yield event.plain_result("\n".join(result_lines))

    async def add_custom_owner(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊添加额外群主
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return

        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        for target_qq in target_qqs:
            custom_perm_manager.add_extra_owner(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 添加额外群主：{', '.join(target_qqs)}。"
        )

    async def add_custom_admin(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊添加额外管理员
        """
        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        user_level = await perm_manager.get_perm_level(
            event, event.get_sender_id(), group_id=group_id
        )
        if user_level > PermLevel.OWNER:
            yield event.plain_result("你没群主权限")
            return

        for target_qq in target_qqs:
            custom_perm_manager.add_extra_admin(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 添加额外管理员：{', '.join(target_qqs)}。"
        )

    async def add_custom_subadmin(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊添加额外次管理员
        """
        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        user_level = await perm_manager.get_perm_level(
            event, event.get_sender_id(), group_id=group_id
        )
        if user_level > PermLevel.OWNER:
            yield event.plain_result("你没群主权限")
            return

        for target_qq in target_qqs:
            custom_perm_manager.add_extra_subadmin(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 添加额外次管理员：{', '.join(target_qqs)}。"
        )

    async def remove_custom_admin(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊删除额外管理员
        """
        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        user_level = await perm_manager.get_perm_level(
            event, event.get_sender_id(), group_id=group_id
        )
        if user_level > PermLevel.OWNER:
            yield event.plain_result("你没群主权限")
            return

        for target_qq in target_qqs:
            custom_perm_manager.remove_extra_admin(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 移除额外管理员：{', '.join(target_qqs)}。"
        )

    async def remove_custom_subadmin(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊删除额外次管理员
        """
        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        user_level = await perm_manager.get_perm_level(
            event, event.get_sender_id(), group_id=group_id
        )
        if user_level > PermLevel.OWNER:
            yield event.plain_result("你没群主权限")
            return

        for target_qq in target_qqs:
            custom_perm_manager.remove_extra_subadmin(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 移除额外次管理员：{', '.join(target_qqs)}。"
        )

    async def remove_custom_owner(
        self, event: AiocqhttpMessageEvent, qq: str | None = None
    ):
        """
        为特定群聊删除额外群主
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return

        group_id = self._resolve_group_id(event)
        if not group_id:
            yield event.plain_result("请在群聊中使用该指令")
            return

        target_qqs, error = self._resolve_target_qqs(event, qq)
        if error:
            yield event.plain_result(error)
            return

        for target_qq in target_qqs:
            custom_perm_manager.remove_extra_owner(group_id, target_qq)
        yield event.plain_result(
            f"已为群 {group_id} 移除额外群主：{', '.join(target_qqs)}。"
        )

    async def view_custom_perm(
        self, event: AiocqhttpMessageEvent, group_id: str | None = None
    ):
        """
        查看特定群聊的独立权限配置信息
        """
        if not group_id:
            group_id = str(event.get_group_id())
            if not group_id or group_id == "0":
                yield event.plain_result("私聊中请指定群号，如：/特殊群权限查看 123456")
                return

        group_id = str(group_id)
        custom_perms = custom_perm_manager.data.get(group_id, {}).get("perms", {})
        extra_owners = custom_perm_manager.get_group_extra_owners(group_id)
        extra_admins = custom_perm_manager.get_group_extra_admins(group_id)
        extra_subadmins = custom_perm_manager.get_group_extra_subadmins(group_id)

        lines = [f"【群 {group_id} 权限配置】"]
        if extra_owners:
            lines.append(f"👑 独立额外群主: {', '.join(extra_owners)}")
        else:
            lines.append("👑 独立额外群主: 无")

        if extra_admins:
            lines.append(f"🛡️ 独立额外管理员: {', '.join(extra_admins)}")
        else:
            lines.append("🛡️ 独立额外管理员: 无")

        if extra_subadmins:
            lines.append(f"🧩 独立额外次管理员: {', '.join(extra_subadmins)}")
        else:
            lines.append("🧩 独立额外次管理员: 无")

        lines.append("\n📌 指令权限列表:")
        for key, default_level in self.config.perms.items():
            display_name = self._get_perm_display_name(key)

            if key in custom_perms:
                lines.append(f"  - {display_name}: {custom_perms[key]} 【独立配置】")
            else:
                lines.append(f"  - {display_name}: {default_level} (全局沿用)")

        yield event.plain_result("\n".join(lines))
