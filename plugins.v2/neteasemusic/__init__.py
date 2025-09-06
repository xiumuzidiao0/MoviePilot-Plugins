import json
from typing import Any, List, Dict, Tuple, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from music_api import NeteaseMusicAPITester

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, MessageChannel


class NeteaseMusic(_PluginBase):
    # 插件名称
    plugin_name = "网易云音乐下载"
    # 插件描述
    plugin_desc = "通过消息交互下载网易云音乐歌曲"
    # 插件图标
    plugin_icon = "163music_A.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "xiumuzidiao0"
    # 作者主页
    author_url = "https://github.com/xiumuzidiao0"
    # 插件配置项ID前缀
    plugin_config_prefix = "neteasemusic_"
    # 加载顺序
    plugin_order = 15
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _base_url = "http://localhost:5100"
    _search_limit = 10
    _default_quality = "exhigh"
    _sessions = {}  # 用户会话状态存储

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._enabled = config.get("enabled")
            self._base_url = config.get("base_url", "http://localhost:5100")
            self._search_limit = config.get("search_limit", 10)
            self._default_quality = config.get("default_quality", "exhigh")
            
        # 初始化API测试器
        self._api_tester = NeteaseMusicAPITester(base_url=self._base_url)
        
        # 初始化会话存储
        self._sessions = {}

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        """
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'base_url',
                                            'label': 'API基础URL',
                                            'placeholder': 'http://localhost:5100'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'search_limit',
                                            'label': '默认搜索数量',
                                            'placeholder': '10'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'default_quality',
                                            'label': '默认音质',
                                            'items': [
                                                {'title': '标准音质', 'value': 'standard'},
                                                {'title': '极高音质', 'value': 'exhigh'},
                                                {'title': '无损音质', 'value': 'lossless'},
                                                {'title': 'Hi-Res音质', 'value': 'hires'},
                                                {'title': '沉浸环绕声', 'value': 'sky'},
                                                {'title': '高清环绕声', 'value': 'jyeffect'},
                                                {'title': '超清母带', 'value': 'jymaster'}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '配置API基础URL、默认搜索数量和默认音质。用户可在交互中自定义这些参数。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "base_url": "http://localhost:5100",
            "search_limit": 10,
            "default_quality": "exhigh"
        }

    def get_page(self) -> List[dict]:
        """
        获取插件页面
        """
        pass

    @eventmanager.register(EventType.UserMessage)
    def handle_user_message(self, event: Event):
        """
        监听用户消息事件
        """
        if not self._enabled:
            return
            
        # 获取消息内容
        text = event.event_data.get("text")
        userid = event.event_data.get("userid")
        channel = event.event_data.get("channel")
        
        if not text or not userid:
            return
            
        logger.info(f"收到用户消息: {text} (用户: {userid})")
        
        # 处理用户消息
        response = self._process_user_message(userid, text)
        
        # 发送回复消息
        if response:
            self.post_message(channel=channel, title=response, userid=userid)

    def _process_user_message(self, userid: str, text: str) -> Optional[str]:
        """
        处理用户消息并生成回复
        
        :param userid: 用户ID
        :param text: 消息文本
        :return: 回复内容
        """
        # 获取用户会话状态
        session = self._sessions.get(userid, {})
        state = session.get("state", "idle")
        
        # 根据会话状态处理消息
        if state == "idle":
            return self._handle_idle_state(userid, text)
        elif state == "waiting_for_keyword":
            return self._handle_waiting_for_keyword(userid, text)
        elif state == "waiting_for_song_choice":
            return self._handle_waiting_for_song_choice(userid, text)
        elif state == "waiting_for_quality_choice":
            return self._handle_waiting_for_quality_choice(userid, text)
        else:
            # 重置状态
            self._sessions[userid] = {"state": "idle"}
            return "抱歉，会话状态异常，已重置。请重新开始下载流程。"

    def _handle_idle_state(self, userid: str, text: str) -> str:
        """
        处理空闲状态下的用户消息
        """
        # 检查是否是开始下载的关键词
        if any(keyword in text.lower() for keyword in ["下载音乐", "下载歌曲", "网易云音乐", "netease"]):
            # 设置会话状态为等待关键词输入
            self._sessions[userid] = {
                "state": "waiting_for_keyword",
                "data": {}
            }
            return "🎵 请输入要搜索的歌曲名称或歌手:"
        
        # 默认回复
        return "您好！发送'下载音乐'来开始下载网易云音乐歌曲。"

    def _handle_waiting_for_keyword(self, userid: str, text: str) -> str:
        """
        处理等待关键词状态下的用户消息
        """
        session = self._sessions[userid]
        data = session.get("data", {})
        
        # 保存搜索关键词
        data["keyword"] = text
        
        # 询问搜索数量
        self._sessions[userid] = {
            "state": "waiting_for_song_choice",  # 这里需要先搜索歌曲
            "data": data
        }
        
        # 搜索歌曲
        search_limit = self._search_limit
        search_result = self._api_tester.search_music(text, limit=search_limit)
        
        if not search_result.get("success"):
            self._sessions[userid] = {"state": "idle"}
            return f"❌ 搜索失败: {search_result.get('message', '未知错误')}"
        
        songs = search_result.get("data", [])
        if not songs:
            self._sessions[userid] = {"state": "idle"}
            return "❌ 未找到相关歌曲，请尝试其他关键词。"
        
        # 保存搜索结果
        data["songs"] = songs
        self._sessions[userid] = {
            "state": "waiting_for_song_choice",
            "data": data
        }
        
        # 构造歌曲列表回复
        response = f"🔍 搜索到 {len(songs)} 首歌曲，请选择要下载的歌曲:\n"
        for i, song in enumerate(songs, 1):
            name = song.get('name', '')
            artists = song.get('artists', '') or song.get('ar_name', '')
            response += f"{i}. {name} - {artists}\n"
        response += f"请输入歌曲序号 (1-{len(songs)}):"
        
        return response

    def _handle_waiting_for_song_choice(self, userid: str, text: str) -> str:
        """
        处理等待歌曲选择状态下的用户消息
        """
        session = self._sessions[userid]
        data = session.get("data", {})
        songs = data.get("songs", [])
        
        # 处理歌曲选择
        try:
            song_index = int(text) - 1
            if 0 <= song_index < len(songs):
                selected_song = songs[song_index]
                data["selected_song"] = selected_song
                
                # 询问音质选择
                self._sessions[userid] = {
                    "state": "waiting_for_quality_choice",
                    "data": data
                }
                
                # 构造音质选择回复
                response = "🎵 请选择下载音质:\n"
                quality_options = [
                    {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
                    {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
                    {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
                    {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
                    {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
                    {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
                    {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
                ]
                
                for i, quality in enumerate(quality_options, 1):
                    response += f"{i}. {quality['name']} ({quality['desc']})\n"
                response += f"请输入音质序号 (1-{len(quality_options)}):"
                
                return response
            else:
                return f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字"
        except ValueError:
            return "❌ 请输入有效的数字序号"

    def _handle_waiting_for_quality_choice(self, userid: str, text: str) -> str:
        """
        处理等待音质选择状态下的用户消息
        """
        session = self._sessions[userid]
        data = session.get("data", {})
        selected_song = data.get("selected_song", {})
        
        # 音质选项
        quality_options = [
            {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
            {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
            {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
            {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
            {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
            {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
            {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
        ]
        
        # 处理音质选择
        try:
            quality_index = int(text) - 1
            if 0 <= quality_index < len(quality_options):
                selected_quality = quality_options[quality_index]
                data["selected_quality"] = selected_quality
                
                # 开始下载
                song_id = str(selected_song.get('id', ''))
                quality_code = selected_quality['code']
                song_name = selected_song.get('name', '')
                artist = selected_song.get('artists', '') or selected_song.get('ar_name', '')
                quality_name = selected_quality['name']
                
                # 重置会话状态
                self._sessions[userid] = {"state": "idle"}
                
                # 执行下载
                response = f"📥 开始下载: {song_name} - {artist} ({quality_name})\n请稍候..."
                download_result = self._api_tester.download_music_for_link(song_id, quality_code)
                
                if download_result.get("success"):
                    response += "\n✅ 下载完成!"
                    # 可以在这里添加下载链接或其他信息
                else:
                    response += f"\n❌ 下载失败: {download_result.get('message', '未知错误')}"
                
                return response
            else:
                return f"❌ 序号超出范围，请输入 1-{len(quality_options)} 之间的数字"
        except ValueError:
            return "❌ 请输入有效的数字序号"

    def stop_service(self):
        """
        退出插件
        """
        pass
