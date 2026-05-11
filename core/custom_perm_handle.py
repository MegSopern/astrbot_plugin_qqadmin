import json
from pathlib import Path
from typing import Dict, List, Any

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

from ..config import PluginConfig
from ..permission import PermLevel, perm_required

PERM_FIELD_MAP = {
    '禁言': 'set_group_ban', '禁我': 'set_group_ban_me', '解禁': 'cancel_group_ban', '全体禁言': 'whole_ban', 
    '全体禁言相关指令': 'whole_ban', '全禁': 'whole_ban', '改名': 'set_group_card', '改我': 'set_group_card_me', 
    '头衔': 'set_group_special_title', '申请头衔': 'set_group_special_title_me', '踢了': 'set_group_kick', 
    '拉黑': 'set_group_block', '设置管理员': 'admin', '上管': 'admin', '下管': 'admin', '设置管理员指令': 'admin',
    '操作群精华': 'essence', '设精': 'essence', '移精': 'essence', '操作群精华指令': 'essence', 
    '群精华': 'get_essence_msg_list', '撤回': 'delete_msg', '发布群公告': 'send_group_notice', 
    '查看群公告': 'get_group_notice', '设置群头像': 'set_group_portrait', '设置群名': 'set_group_name', 
    '禁词': 'word_ban', '内置禁词': 'word_ban', '设置禁词': 'word_ban', '禁词指令': 'word_ban', 
    '刷屏禁言': 'handle_builtin_ban_words', '刷屏禁言指令': 'handle_builtin_ban_words',
    '投票禁言': 'vote', '投票禁言指令': 'vote', '宵禁': 'curfew', '宵禁指令': 'curfew', 
    '进群审核': 'join', '进群审核指令': 'join', '批准': 'approve', '驳回': 'approve', 
    '批准/驳回（进群申请）': 'approve', '进群欢迎': 'welcome', '进群欢迎与禁言': 'welcome', 
    '退群通知': 'leave', '退群通知与拉黑': 'leave', '群友信息': 'get_group_member_list', 
    '清理群友': 'clear_group_member', '上传群文件': 'upload_group_file', '删除群文件': 'delete_group_file', 
    '查看群文件': 'view_group_file', '取名': 'ai_set_card', '取头衔': 'ai_set_title', 
    '群管配置': 'set_config', '群管重置': 'reset_config'
}

class CustomPermManager:
    def __init__(self):
        self.file_path: Path = None
        self.data: dict = {}
        
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
        
    def set_group_perm(self, group_id: str, perm_key: str, level_str: str):
        group_id = str(group_id)
        if group_id not in self.data:
            self.data[group_id] = {"extra_owners": [], "perms": {}}
        if "perms" not in self.data[group_id]:
            self.data[group_id]["perms"] = {}
        self.data[group_id]["perms"][perm_key] = level_str
        self.save()

    def add_extra_owner(self, group_id: str, qq: str):
        group_id = str(group_id)
        qq = str(qq)
        if group_id not in self.data:
            self.data[group_id] = {"extra_owners": [], "perms": {}}
        if "extra_owners" not in self.data[group_id]:
            self.data[group_id]["extra_owners"] = []
        if qq not in self.data[group_id]["extra_owners"]:
            self.data[group_id]["extra_owners"].append(qq)
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

    async def set_custom_perm(self, event: AiocqhttpMessageEvent, group_id: str, perm_key: str, level: str):
        """
        为特定群聊单独设置某个指令的权限
        如：/单群权限设置 123456 禁言 管理员
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return
            
        valid_keys = self.config.perms.keys()
        
        # 允许用户输入中文别名
        if perm_key not in valid_keys:
            if perm_key in PERM_FIELD_MAP:
                perm_key = PERM_FIELD_MAP[perm_key]
            else:
                cn_keys = [k for k, v in PERM_FIELD_MAP.items() if not k.endswith("指令") and "（" not in k]
                yield event.plain_result(f"未知的权限名：{perm_key}，可使用的中文命令/权限名有：{', '.join(cn_keys)}")
                return
            
        try:
            PermLevel.from_str(level)
        except Exception:
            yield event.plain_result(f"未知的权限等级：{level}。有效等级例如：超管、群主、管理员、成员等。")
            return
            
        custom_perm_manager.set_group_perm(group_id, perm_key, level)
        yield event.plain_result(f"已将群 {group_id} 的 {perm_key} 权限修改为 {level}。")

    async def add_custom_owner(self, event: AiocqhttpMessageEvent, group_id: str, qq: str):
        """
        为特定群聊添加额外群主
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return
            
        custom_perm_manager.add_extra_owner(group_id, qq)
        yield event.plain_result(f"已为群 {group_id} 添加额外群主 {qq}。")

    async def remove_custom_owner(self, event: AiocqhttpMessageEvent, group_id: str, qq: str):
        """
        为特定群聊删除额外群主
        """
        if str(event.get_sender_id()) not in self.config.admins_id:
            yield event.plain_result("你没超管权限")
            return
            
        custom_perm_manager.remove_extra_owner(group_id, qq)
        yield event.plain_result(f"已为群 {group_id} 移除额外群主 {qq}。")

    async def view_custom_perm(self, event: AiocqhttpMessageEvent, group_id: str | None = None):
        """
        查看特定群聊的独立权限配置信息
        """
        if not group_id:
            group_id = str(event.get_group_id())
            if not group_id or group_id == "0":
                yield event.plain_result("私聊中请指定群号，如：/单群权限查看 123456")
                return

        group_id = str(group_id)
        custom_perms = custom_perm_manager.data.get(group_id, {}).get("perms", {})
        extra_owners = custom_perm_manager.get_group_extra_owners(group_id)

        lines = [f"【群 {group_id} 权限配置】"]
        if extra_owners:
            lines.append(f"👑 独立额外群主: {', '.join(extra_owners)}")
        else:
            lines.append("👑 独立额外群主: 无")

        lines.append("\n📌 指令权限列表:")
        for key, default_level in self.config.perms.items():
            # 找到对应的主要中文名用于展示
            cn_names = [k for k, v in PERM_FIELD_MAP.items() if v == key and not k.endswith("指令") and "（" not in k]
            display_name = cn_names[0] if cn_names else key
            
            if key in custom_perms:
                lines.append(f"  - {display_name}: {custom_perms[key]} 【独立配置】")
            else:
                lines.append(f"  - {display_name}: {default_level} (全局沿用)")

        yield event.plain_result("\n".join(lines))