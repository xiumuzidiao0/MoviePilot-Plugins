import json
from typing import Any, List, Dict, Tuple, Optional
import sys
import os
import time  # 添加time模块用于会话超时检查

from .test_api import NeteaseMusicAPITester

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, MessageChannel


class NeteaseMusic(_PluginBase):
    # 插件名称
    plugin_name = "网易云音乐下载"
    # 插件描述
    plugin_desc = "通过命令直接搜索并下载网易云音乐歌曲"
    # 插件图标
    plugin_icon = "163music_A.png"
    # 插件版本
    plugin_version = "1.07"
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
    
    # 默认配置常量
    DEFAULT_BASE_URL = "http://localhost:5000"
    DEFAULT_SEARCH_LIMIT = 8
    DEFAULT_QUALITY = "exhigh"
    SESSION_TIMEOUT = 300  # 会话超时时间（秒），5分钟

    # 私有属性
    _enabled = False
    _base_url = None
    _search_limit = None
    _default_quality = None
    _sessions = {}  # 用户会话状态存储

    def init_plugin(self, config: Optional[dict] = None):
        """
        初始化插件
        """
        logger.info("开始初始化网易云音乐插件")
        
        if config:
            self._enabled = config.get("enabled", False)
            self._base_url = config.get("base_url")  # 允许为None
            self._search_limit = config.get("search_limit")  # 允许为None
            self._default_quality = config.get("default_quality")  # 允许为None
            
            logger.debug(f"插件配置加载完成: enabled={self._enabled}, base_url={self._base_url}, "
                        f"search_limit={self._search_limit}, default_quality={self._default_quality}")
        else:
            # 如果没有配置，使用默认值
            self._enabled = False
            self._base_url = None
            self._search_limit = None
            self._default_quality = None
            
            logger.info("未找到插件配置，使用默认配置")
            
        # 初始化API测试器
        api_base_url = self._base_url or self.DEFAULT_BASE_URL
        self._api_tester = NeteaseMusicAPITester(base_url=api_base_url)
        logger.info(f"API测试器初始化完成，基础URL: {api_base_url}")
        
        # 检测支持的音质选项并输出到日志
        self._log_supported_qualities()
        
        # 初始化会话存储
        self._sessions = {}
        logger.info("插件初始化完成")

    def _log_supported_qualities(self):
        """
        检测并记录支持的音质选项
        """
        quality_options = [
            {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
            {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
            {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
            {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
            {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
            {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
            {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
        ]
        
        logger.info("支持的音质选项:")
        for quality in quality_options:
            logger.info(f"  - {quality['name']} ({quality['code']}): {quality['desc']}")

    def set_enabled(self, enabled: bool):
        """
        设置插件启用状态
        
        Args:
            enabled: 是否启用插件
        """
        logger.info(f"设置插件启用状态: {enabled}")
        self._enabled = enabled
        # 可以在这里添加其他启用/禁用时需要处理的逻辑

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        通过get_form方法实现配置界面：
        使用Vuetify组件库的JSON配置方式构建界面
        定义了插件配置页面的表单结构，包括：
        - 启用插件开关 (VSwitch组件)
        - API基础URL配置 (VTextField组件)
        - 默认搜索数量 (VTextField组件，数字类型)
        - 默认音质选择 (VSelect组件)
        """
        logger.debug("生成插件配置表单")
        
        # 动态生成表单，使用当前配置值作为默认值
        base_url_placeholder = self._base_url or self.DEFAULT_BASE_URL
        search_limit_placeholder = str(self._search_limit or self.DEFAULT_SEARCH_LIMIT)
        
        logger.debug(f"表单占位符值: base_url={base_url_placeholder}, search_limit={search_limit_placeholder}")
        
        form_config = [
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
                                    'md': 4
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
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'base_url',
                                            'label': 'API基础URL',
                                            'placeholder': base_url_placeholder
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'search_limit',
                                            'label': '默认搜索数量',
                                            'placeholder': search_limit_placeholder,
                                            'type': 'number'
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
                                                {'title': '每首歌都询问', 'value': 'ask'},
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
        ]
        
        form_data = {
            "enabled": self._enabled,
            "base_url": self._base_url,
            "search_limit": self._search_limit,
            "default_quality": self._default_quality
        }
        
        logger.debug(f"配置表单数据: {form_data}")
        return form_config, form_data

    def _get_session(self, userid: str) -> Optional[Dict]:
        """
        获取用户会话，检查超时
        
        :param userid: 用户ID
        :return: 会话数据，如果超时或不存在则返回None
        """
        logger.debug(f"获取用户 {userid} 的会话数据")
        session = self._sessions.get(userid)
        logger.debug(f"用户 {userid} 的原始会话数据: {session}")
        if not session:
            logger.debug(f"用户 {userid} 没有会话数据")
            return None
            
        # 检查会话是否超时
        last_active = session.get("last_active", 0)
        current_time = time.time()
        time_diff = current_time - last_active
        logger.debug(f"用户 {userid} 会话时间差: {time_diff}秒，超时设置: {self.SESSION_TIMEOUT}秒")
        if time_diff > self.SESSION_TIMEOUT:
            # 会话超时，清理并返回None
            logger.debug(f"用户 {userid} 的会话已超时，清理会话数据")
            self._sessions.pop(userid, None)
            return None
            
        logger.debug(f"用户 {userid} 的会话数据有效")
        return session

    def _update_session(self, userid: str, session_data: Dict):
        """
        更新用户会话数据
        
        :param userid: 用户ID
        :param session_data: 会话数据
        """
        logger.debug(f"更新用户 {userid} 的会话数据: {session_data}")
        session_data["last_active"] = time.time()
        self._sessions[userid] = session_data
        logger.debug(f"用户 {userid} 的会话数据已更新: {self._sessions[userid]}")

    @eventmanager.register(EventType.PluginAction)
    def command_action(self, event: Event):
        """
        远程命令响应
        """
        logger.info(f"收到PluginAction事件: {event}")
        
        if not self._enabled:
            logger.info("插件未启用")
            return
            
        event_data = event.event_data
        logger.info(f"事件数据: {event_data}")
        
        # 获取动作类型
        action = event_data.get("action") if event_data else None
        
        # 根据动作类型处理不同命令
        if action == "netease_music_download":
            self._handle_music_download(event)
        elif action == "netease_music_select":
            self._handle_music_select(event)
        else:
            logger.info(f"未知的动作类型: {action}")
            return

    def _handle_music_download(self, event: Event):
        """
        处理音乐下载命令
        """
        event_data = event.event_data
        # 从事件数据中获取用户ID，可能的字段名包括userid和user
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        
        if not userid:
            logger.info("用户ID为空")
            return
            
        # 获取命令参数（歌曲名/歌手名）
        command_args = event_data.get("arg_str", "").strip()
        if not command_args:
            # 如果没有参数，提示用户输入
            logger.info(f"用户 {userid} 触发网易云音乐下载命令，但未提供参数")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐下载",
                    text="请输入要搜索的歌曲名称或歌手，例如：/音乐 周杰伦",
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"发送提示消息失败: {e}", exc_info=True)
            return
        
        logger.info(f"用户 {userid} 搜索音乐: {command_args}")
        
        # 直接执行搜索
        try:
            # 搜索歌曲
            search_limit = self._search_limit or self.DEFAULT_SEARCH_LIMIT
            logger.debug(f"开始搜索歌曲: 关键词={command_args}, 限制数量={search_limit}")
            
            search_result = self._api_tester.search_music(command_args, limit=search_limit)
            logger.debug(f"搜索完成，结果: success={search_result.get('success')}, "
                        f"歌曲数量={len(search_result.get('data', []))}")
            
            if not search_result.get("success"):
                error_msg = search_result.get('message', '未知错误')
                logger.warning(f"用户 {userid} 搜索失败: {error_msg}")
                response = f"❌ 搜索失败: {error_msg}"
            else:
                songs = search_result.get("data", [])
                if not songs:
                    logger.info(f"用户 {userid} 搜索未找到结果: {command_args}")
                    response = "❌ 未找到相关歌曲，请尝试其他关键词。"
                else:
                    # 保存搜索结果到会话，包含分页信息
                    session_data = {
                        "state": "waiting_for_song_choice",
                        "data": {
                            "songs": songs,
                            "timestamp": time.time(),  # 添加时间戳
                            "current_page": 0  # 添加当前页码
                        }
                    }
                    self._update_session(userid, session_data)
                    logger.debug(f"用户 {userid} 搜索结果已保存到会话，时间戳: {session_data['data']['timestamp']}")
                    
                    # 显示第一页结果
                    response = self._format_song_list_page(userid, songs, 0)
        
            # 发送结果
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 网易云音乐搜索结果",
                text=response,
                userid=userid
            )
            logger.info(f"已向用户 {userid} 发送搜索结果")
        except Exception as e:
            logger.error(f"搜索音乐时发生错误: {e}", exc_info=True)
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐下载",
                    text="❌ 搜索时发生错误，请稍后重试",
                    userid=userid
                )
            except Exception as e2:
                logger.error(f"发送错误消息失败: {e2}", exc_info=True)

    def _format_song_list_page(self, userid: str, songs: List[Dict], page: int) -> str:
        """
        格式化歌曲列表页面
        
        :param userid: 用户ID
        :param songs: 歌曲列表
        :param page: 页码（从0开始）
        :return: 格式化后的页面内容
        """
        PAGE_SIZE = 8  # 每页显示8首歌曲
        total_songs = len(songs)
        total_pages = (total_songs + PAGE_SIZE - 1) // PAGE_SIZE  # 计算总页数
        
        # 计算当前页的起始和结束索引
        start_idx = page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_songs)
        
        # 构造歌曲列表回复
        response = f"🔍 搜索到 {total_songs} 首歌曲 (第 {page + 1}/{total_pages} 页):\n"
        
        # 显示当前页的歌曲
        for i in range(start_idx, end_idx):
            song = songs[i]
            name = song.get('name', '')
            artists = song.get('artists', '') or song.get('ar_name', '')
            response += f"{i + 1}. {name} - {artists}\n"
        
        # 添加翻页提示
        if total_pages > 1:
            response += "\n"
            if page > 0:
                response += "输入 /n p 查看上一页\n"
            if page < total_pages - 1:
                response += "输入 /n n 查看下一页\n"
        
        response += "输入 /n 数字 选择歌曲下载，例如：/n 1"
        
        return response

    def _handle_music_select(self, event: Event):
        """
        处理音乐选择命令
        """
        event_data = event.event_data
        # 从事件数据中获取用户ID，可能的字段名包括userid和user
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        
        if not userid:
            logger.info("用户ID为空")
            return
            
        # 获取命令参数（数字或翻页指令）
        command_args = event_data.get("arg_str", "").strip()
        if not command_args:
            # 如果没有参数，提示用户输入
            logger.info(f"用户 {userid} 触发网易云音乐选择命令，但未提供参数")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text="请输入要选择的歌曲序号，例如：/n 1",
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"发送提示消息失败: {e}", exc_info=True)
            return
        
        logger.info(f"用户 {userid} 选择歌曲: {command_args}")
        
        # 检查用户是否有有效的搜索会话
        session = self._get_session(userid)
        if not session:
            logger.info(f"用户 {userid} 没有有效的搜索会话")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text="请先使用 /音乐 命令搜索歌曲，然后使用 /n 数字 来选择歌曲下载",
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"发送提示消息失败: {e}", exc_info=True)
            return
        
        # 检查会话是否在有效时间内（5分钟内）
        data = session.get("data", {})
        timestamp = data.get("timestamp", 0)
        current_time = time.time()
        if current_time - timestamp > self.SESSION_TIMEOUT:
            logger.info(f"用户 {userid} 的搜索会话已超时")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text="搜索结果已过期，请重新使用 /音乐 命令搜索歌曲",
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送提示消息")
                # 清理会话
                self._sessions.pop(userid, None)
            except Exception as e:
                logger.error(f"发送提示消息失败: {e}", exc_info=True)
            return
        
        # 检查会话状态
        state = session.get("state")
        songs = data.get("songs", [])
        current_page = data.get("current_page", 0)
        PAGE_SIZE = 8
        
        # 根据会话状态处理不同情况
        if state == "waiting_for_quality_choice":
            # 处理音质选择
            selected_song = data.get("selected_song")
            if selected_song:
                return self._handle_quality_selection(event, selected_song)
        elif state == "waiting_for_song_choice":
            # 处理歌曲选择或翻页
            pass
        else:
            logger.info(f"用户 {userid} 会话状态无效: {state}")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text="会话状态异常，请重新使用 /音乐 命令搜索歌曲",
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送提示消息")
                # 清理会话
                self._sessions.pop(userid, None)
            except Exception as e:
                logger.error(f"发送提示消息失败: {e}", exc_info=True)
            return
        
        # 处理翻页指令
        if command_args.lower() == 'n':  # 下一页
            total_pages = (len(songs) + PAGE_SIZE - 1) // PAGE_SIZE
            if current_page < total_pages - 1:
                # 更新会话中的页码
                data["current_page"] = current_page + 1
                self._update_session(userid, {"state": "waiting_for_song_choice", "data": data})
                
                # 显示下一页
                response = self._format_song_list_page(userid, songs, current_page + 1)
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐搜索结果",
                    text=response,
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送下一页搜索结果")
            else:
                response = "❌ 已经是最后一页了"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text=response,
                    userid=userid
                )
            return
        elif command_args.lower() == 'p':  # 上一页
            if current_page > 0:
                # 更新会话中的页码
                data["current_page"] = current_page - 1
                self._update_session(userid, {"state": "waiting_for_song_choice", "data": data})
                
                # 显示上一页
                response = self._format_song_list_page(userid, songs, current_page - 1)
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐搜索结果",
                    text=response,
                    userid=userid
                )
                logger.info(f"已向用户 {userid} 发送上一页搜索结果")
            else:
                response = "❌ 已经是第一页了"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text=response,
                    userid=userid
                )
            return
        
        # 处理数字选择
        try:
            song_index = int(command_args) - 1
            logger.debug(f"用户 {userid} 选择歌曲序号: {command_args} (索引: {song_index})")
            
            if 0 <= song_index < len(songs):
                selected_song = songs[song_index]
                song_name = selected_song.get('name', '')
                song_artists = selected_song.get('artists', '') or selected_song.get('ar_name', '')
                
                logger.info(f"用户 {userid} 选择歌曲: {song_name} - {song_artists}")
                
                # 检查是否需要询问音质
                default_quality = self._default_quality or self.DEFAULT_QUALITY
                if default_quality == "ask":
                    # 保存选中的歌曲到会话并询问音质
                    data["selected_song"] = selected_song
                    self._update_session(userid, {"state": "waiting_for_quality_choice", "data": data})
                    
                    # 显示音质选择列表
                    response = self._format_quality_list()
                    self.post_message(
                        channel=channel,
                        source=source,
                        title="🎵 选择音质",
                        text=response,
                        userid=userid
                    )
                    logger.info(f"已向用户 {userid} 发送音质选择列表")
                else:
                    # 使用默认音质下载
                    self._download_song_with_quality(event, selected_song, default_quality)
            else:
                logger.warning(f"用户 {userid} 选择的歌曲序号超出范围: {song_index} (有效范围: 0-{len(songs)-1})")
                response = f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text=response,
                    userid=userid
                )
        except ValueError:
            logger.warning(f"用户 {userid} 输入的歌曲序号无效: {command_args}")
            response = "❌ 请输入有效的数字序号或翻页指令 (/n n 下一页, /n p 上一页)"
            self.post_message(
                channel=channel,
                    source=source,
                    title="🎵 网易云音乐歌曲选择",
                    text=response,
                    userid=userid
            )

    def _handle_quality_selection(self, event: Event, selected_song: Dict):
        """
        处理音质选择
        
        :param event: 事件对象
        :param selected_song: 选中的歌曲
        """
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        command_args = event_data.get("arg_str", "").strip()
        
        try:
            quality_index = int(command_args) - 1
            quality_options = [
                {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
                {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
                {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
                {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
                {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
                {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
                {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
            ]
            
            if 0 <= quality_index < len(quality_options):
                selected_quality = quality_options[quality_index]
                quality_code = selected_quality["code"]
                quality_name = selected_quality["name"]
                
                logger.info(f"用户 {userid} 选择音质: {quality_name}")
                
                # 重置会话状态
                self._update_session(userid, {"state": "idle"})
                
                # 下载歌曲
                self._download_song_with_quality(event, selected_song, quality_code)
            else:
                logger.warning(f"用户 {userid} 选择的音质序号超出范围: {quality_index}")
                response = f"❌ 序号超出范围，请输入 1-{len(quality_options)} 之间的数字"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音质选择",
                    text=response,
                    userid=userid
                )
        except ValueError:
            logger.warning(f"用户 {userid} 输入的音质序号无效: {command_args}")
            response = "❌ 请输入有效的数字序号选择音质"
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 音质选择",
                text=response,
                userid=userid
            )

    def _format_quality_list(self) -> str:
        """
        格式化音质列表
        
        :return: 格式化后的音质列表
        """
        quality_options = [
            {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
            {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
            {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
            {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
            {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
            {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
            {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
        ]
        
        response = "🎵 请选择下载音质:\n"
        for i, quality in enumerate(quality_options, 1):
            response += f"{i}. {quality['name']} ({quality['desc']})\n"
        
        response += "\n请输入 /n 数字 选择音质，例如：/n 2"
        return response

    def _download_song_with_quality(self, event: Event, selected_song: Dict, quality_code: str):
        """
        使用指定音质下载歌曲
        
        :param event: 事件对象
        :param selected_song: 选中的歌曲
        :param quality_code: 音质代码
        """
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        
        # 获取音质信息
        quality_options = {
            "standard": {"name": "标准音质", "desc": "128kbps MP3"},
            "exhigh": {"name": "极高音质", "desc": "320kbps MP3"},
            "lossless": {"name": "无损音质", "desc": "FLAC"},
            "hires": {"name": "Hi-Res音质", "desc": "24bit/96kHz"},
            "sky": {"name": "沉浸环绕声", "desc": "空间音频"},
            "jyeffect": {"name": "高清环绕声", "desc": "环绕声效果"},
            "jymaster": {"name": "超清母带", "desc": "母带音质"}
        }
        
        quality_info = quality_options.get(quality_code, quality_options[self.DEFAULT_QUALITY])
        quality_name = quality_info["name"]
        
        # 获取歌曲信息
        song_name = selected_song.get('name', '')
        song_id = str(selected_song.get('id', ''))
        artist = selected_song.get('artists', '') or selected_song.get('ar_name', '')
        
        logger.info(f"用户 {userid} 准备下载歌曲: {song_name} - {artist} ({quality_name})")
        
        # 重置会话状态
        self._update_session(userid, {"state": "idle"})
        logger.debug(f"用户 {userid} 会话状态重置为: idle")
        
        # 执行下载
        response = f"📥 开始下载: {song_name} - {artist} ({quality_name})\n请稍候..."
        logger.debug(f"开始下载歌曲 {song_id}，音质: {quality_code}")
        
        try:
            download_result = self._api_tester.download_music_for_link(song_id, quality_code)
            logger.debug(f"下载完成，结果: success={download_result.get('success')}")
        except Exception as e:
            logger.error(f"下载歌曲时发生异常: {e}", exc_info=True)
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 网易云音乐下载",
                text="❌ 下载失败: 网络异常，请稍后重试",
                userid=userid
            )
            return
        
        if download_result.get("success"):
            response += "\n✅ 下载完成!"
            logger.info(f"用户 {userid} 下载完成: {song_name} - {artist} ({quality_name})")
        else:
            error_msg = download_result.get('message', '未知错误')
            response += f"\n❌ 下载失败: {error_msg}"
            logger.warning(f"用户 {userid} 下载失败: {error_msg}")
        
        # 发送结果
        self.post_message(
            channel=channel,
            source=source,
            title="🎵 网易云音乐下载完成",
            text=response,
            userid=userid
        )
        logger.info(f"已向用户 {userid} 发送下载结果")

    @eventmanager.register(EventType.UserMessage)
    def handle_user_message(self, event: Event):
        """
        监听用户消息事件
        """
        logger.debug(f"收到用户消息事件: {event}")
        
        if not self._enabled:
            logger.debug("插件未启用，忽略消息")
            return
            
        # 获取消息内容
        text = event.event_data.get("text")
        userid = event.event_data.get("userid") or event.event_data.get("user")
        channel = event.event_data.get("channel")
        
        if not text or not userid:
            logger.warning("消息缺少必要信息: text或userid为空")
            return
            
        logger.info(f"收到用户消息: {text} (用户: {userid})")
        
        # 现在使用专门的命令处理，不再处理普通用户消息
        logger.debug(f"用户 {userid} 发送普通消息，交由系统处理")

    def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """
        测试API连接
        
        Args:
            url: API地址，如果未提供则使用当前配置的地址
            
        Returns:
            连接测试结果
        """
        logger.info("开始测试API连接")
        
        try:
            # 使用提供的URL或当前配置的URL
            api_url = url or self._base_url or self.DEFAULT_BASE_URL
            logger.debug(f"测试API地址: {api_url}")
            
            # 测试健康检查接口
            test_url = f"{api_url.rstrip('/')}/health"
            logger.debug(f"健康检查URL: {test_url}")
            
            response = self._api_tester.session.get(test_url, timeout=10)
            logger.debug(f"健康检查响应: status_code={response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"API连接测试成功: {api_url}")
                return {
                    "success": True,
                    "message": f"成功连接到API服务器: {api_url}",
                    "status_code": response.status_code
                }
            else:
                logger.warning(f"API连接测试失败: status_code={response.status_code}")
                return {
                    "success": False,
                    "message": f"连接失败，状态码: {response.status_code}",
                    "status_code": response.status_code
                }
        except Exception as e:
            logger.error(f"API连接测试异常: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"连接异常: {str(e)}",
                "error": str(e)
            }

    def stop_service(self):
        """
        退出插件
        """
        logger.info("正在停止网易云音乐插件服务")
        # 清理会话数据
        self._sessions.clear()
        logger.info("插件服务已停止，会话数据已清理")

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API接口列表
        
        Returns:
            API接口列表
        """
        logger.debug("获取插件API接口列表")
        return [
            {
                "path": "/test_connection",
                "endpoint": self.test_connection,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试API连接",
                "description": "测试配置的API地址是否可以正常连接"
            }
        ]

    def get_page(self) -> List[dict]:
        """
        获取插件详情页面配置
        
        Returns:
            页面配置列表
        """
        logger.debug("生成插件详情页面配置")
        return [
            {
                'component': 'VContainer',
                'props': {
                    'fluid': True
                },
                'content': [
                    {
                        'component': 'VRow',
                        'props': {
                            'justify': 'center'
                        },
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VCard',
                                        'content': [
                                            {
                                                'component': 'VCardTitle',
                                                'content': [
                                                    {
                                                        'component': 'span',
                                                        'text': '网易云音乐下载插件'
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCardText',
                                                'content': [
                                                    {
                                                        'component': 'p',
                                                        'text': '通过命令直接搜索并下载网易云音乐歌曲'
                                                    },
                                                    {
                                                        'component': 'h3',
                                                        'text': '使用方法：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': '在聊天中发送"/音乐 歌曲名/歌手名"直接搜索音乐'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '从搜索结果中选择歌曲序号进行下载'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '使用"/n n"查看下一页搜索结果'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '使用"/n p"查看上一页搜索结果'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'h3',
                                                        'text': '配置说明：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': 'API基础URL：网易云音乐API服务的基础URL，默认为http://localhost:5000'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认搜索数量：搜索歌曲时返回的结果数量，默认为8首'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认音质：下载歌曲的默认音质，支持多种音质选项'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'h3',
                                                        'text': '支持的音质选项：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': '标准音质(standard)：128kbps MP3'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '极高音质(exhigh)：320kbps MP3'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '无损音质(lossless)：FLAC'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': 'Hi-Res音质(hires)：24bit/96kHz'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '沉浸环绕声(sky)：空间音频'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '高清环绕声(jyeffect)：环绕声效果'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '超清母带(jymaster)：母带音质'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'h3',
                                                        'text': '分页说明：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': '搜索结果默认每页显示8首歌曲'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '使用"/n 数字"选择歌曲下载'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '使用"/n n"查看下一页'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '使用"/n p"查看上一页'
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def get_dashboard(self, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], str]]:
        """
        获取仪表板组件配置
        
        Returns:
            仪表板组件配置元组(组件配置, 数据, 样式)
        """
        logger.debug("生成仪表板组件配置")
        component = {
            'component': 'VCard',
            'content': [
                {
                    'component': 'VCardText',
                    'content': [
                        {
                            'component': 'div',
                            'props': {
                                'class': 'd-flex align-center'
                            },
                            'content': [
                                {
                                    'component': 'VIcon',
                                    'props': {
                                        'icon': 'mdi-music-note',
                                        'size': 'large',
                                        'color': 'primary'
                                    }
                                },
                                {
                                    'component': 'div',
                                    'props': {
                                        'class': 'ml-3'
                                    },
                                    'content': [
                                        {
                                            'component': 'div',
                                            'props': {
                                                'class': 'text-h6'
                                            },
                                            'text': '网易云音乐下载'
                                        },
                                        {
                                            'component': 'div',
                                            'props': {
                                                'class': 'text-subtitle-1'
                                            },
                                            'text': '通过消息交互下载音乐'
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return component, {}, 'row span-4'

    def get_state(self) -> bool:
        """
        获取插件状态
        
        Returns:
            bool: 插件启用状态
        """
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        注册插件命令
        
        Returns:
            List[Dict[str, Any]]: 命令列表
        """
        return [
            {
                "cmd": "/音乐",
                "event": EventType.PluginAction,
                "desc": "网易云音乐下载",
                "category": "媒体搜索",
                "data": {
                    "action": "netease_music_download"
                }
            },
            {
                "cmd": "/音乐下载",
                "event": EventType.PluginAction,
                "desc": "网易云音乐下载",
                "category": "媒体搜索",
                "data": {
                    "action": "netease_music_download"
                }
            },
            {
                "cmd": "/n",
                "event": EventType.PluginAction,
                "desc": "网易云音乐歌曲选择",
                "category": "媒体搜索",
                "data": {
                    "action": "netease_music_select"
                }
            }
        ]

