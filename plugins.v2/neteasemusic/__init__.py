import json
from typing import Any, List, Dict, Tuple, Optional
import sys
import os
import time  # 添加time模块用于会话超时检查

from .test_api import NeteaseMusicAPITester

# 安全导入所有必需模块
try:
    from app.core.event import eventmanager, Event
    from app.log import logger
    from app.plugins import _PluginBase
    from app.schemas.types import EventType, MessageChannel
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"警告: 缺少必要的MoviePilot模块: {e}")
    MODULES_AVAILABLE = False
    
    # 创建模拟类以避免导入错误
    class Event:
        pass
    
    class _PluginBase:
        pass
    
    EventType = None
    MessageChannel = None
    
    # 创建模拟logger
    import logging
    logger = logging.getLogger(__name__)
    
    # 创建模拟eventmanager装饰器
    def eventmanager(func):
        return func

# 导入MCP插件助手（可选）
try:
    from app.plugins.mcpserver.dev.mcp_dev import (
        mcp_tool,
        mcp_prompt,
        MCPDecoratorMixin
    )
    MCP_DEV_AVAILABLE = True
    # 创建基类元组
    BaseClasses = (_PluginBase, MCPDecoratorMixin)
except ImportError:
    # MCP Server 插件不可用时的降级处理
    MCP_DEV_AVAILABLE = False

    def mcp_tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def mcp_prompt(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    class MCPDecoratorMixin:
        pass
    
    # 只使用基础插件类
    BaseClasses = (_PluginBase,)


class NeteaseMusic(*BaseClasses):
    # 插件名称
    plugin_name = "网易云音乐下载"
    # 插件描述
    plugin_desc = "通过命令直接搜索并下载歌曲"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/xiumuzidiao0/MoviePilot-Plugins/main/icons/163music_A.png"
    # 插件版本
    plugin_version = "1.28"
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
    _openlist_url = None  # 添加openlist地址属性
    _sessions = {}  # 用户会话状态存储

    def init_plugin(self, config: Optional[dict] = None):
        """
        初始化插件
        """
        logger.info("开始初始化音乐插件")
        
        if config:
            self._enabled = config.get("enabled", False)
            self._base_url = config.get("base_url")  # 允许为None
            self._search_limit = config.get("search_limit")  # 允许为None
            self._default_quality = config.get("default_quality")  # 允许为None
            self._openlist_url = config.get("openlist_url")  # 初始化openlist地址
            
            logger.debug(f"插件配置加载完成: enabled={self._enabled}, base_url={self._base_url}, "
                        f"search_limit={self._search_limit}, default_quality={self._default_quality}, "
                        f"openlist_url={self._openlist_url}")
        else:
            # 如果没有配置，使用默认值
            self._enabled = False
            self._base_url = None
            self._search_limit = None
            self._default_quality = None
            self._openlist_url = None
            
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
        
        # 初始化MCP装饰器支持
        if MCP_DEV_AVAILABLE:
            self.init_mcp_decorators()

    def stop_service(self):
        """
        退出插件
        """
        logger.info("正在停止音乐插件服务")
        # 清理会话数据
        self._sessions.clear()
        logger.info("插件服务已停止，会话数据已清理")
        
        # 停止MCP装饰器支持
        if MCP_DEV_AVAILABLE and hasattr(self, 'stop_mcp_decorators'):
            self.stop_mcp_decorators()

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API接口列表
        
        Returns:
            API接口列表
        """
        logger.debug("获取插件API接口列表")
        api_endpoints = [
            {
                "path": "/test_connection",
                "endpoint": self.test_connection,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试API连接",
                "description": "测试配置的API地址是否可以正常连接"
            }
        ]
        
        # 添加MCP相关的API端点
        if hasattr(self, 'get_mcp_api_endpoints') and callable(getattr(self, 'get_mcp_api_endpoints')):
            try:
                api_endpoints.extend(self.get_mcp_api_endpoints())
            except Exception as e:
                logger.warning(f"获取MCP API端点时出错: {e}")

        return api_endpoints

    # 添加MCP工具：搜索音乐
    @mcp_tool(
        name="netease-music-search",
        description="搜索网易云音乐",
        parameters=[
            {
                "name": "keyword",
                "description": "搜索关键词（歌曲名或歌手名）",
                "required": True,
                "type": "string"
            },
            {
                "name": "limit",
                "description": "返回结果数量",
                "required": False,
                "type": "integer"
            }
        ]
    )
    def mcp_search_music(self, keyword: str, limit: int = 5) -> dict:
        """MCP音乐搜索工具"""
        if not self._enabled:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "插件未启用"
                    }
                ],
                "isError": True
            }
        
        try:
            # 使用配置的搜索限制或默认值
            search_limit = limit or self._search_limit or self.DEFAULT_SEARCH_LIMIT
            result = self._api_tester.search_music(keyword, limit=search_limit)
            
            if result.get("success"):
                songs = result.get("data", [])
                if not songs:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "未找到相关歌曲"
                            }
                        ],
                        "isError": False
                    }
                
                # 格式化歌曲信息
                song_list = []
                for i, song in enumerate(songs[:search_limit], 1):
                    name = song.get("name", "未知歌曲")
                    artists = song.get("artists", "") or song.get("ar_name", "未知艺术家")
                    album = song.get("album", "未知专辑")
                    song_id = song.get("id", "")
                    pic_url = song.get("picUrl", "") or song.get("album_picUrl", "")
                    
                    song_info = f"{i}. {name} - {artists}\n   专辑: {album}"
                    if song_id:
                        song_info += f"\n   ID: {song_id}"
                    if pic_url:
                        song_info += f"\n   🖼️ 封面: {pic_url}"
                    song_list.append(song_info)
                
                response_text = f"🔍 搜索到 {len(songs)} 首歌曲:\n\n" + "\n\n".join(song_list)
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ],
                    "isError": False
                }
            else:
                error_msg = result.get("message", "搜索失败")
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"搜索失败: {error_msg}"
                        }
                    ],
                    "isError": True
                }
        except Exception as e:
            logger.error(f"MCP音乐搜索出错: {e}", exc_info=True)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"搜索异常: {str(e)}"
                    }
                ],
                "isError": True
            }

    # 添加MCP工具：下载音乐
    @mcp_tool(
        name="netease-music-download",
        description="下载网易云音乐",
        parameters=[
            {
                "name": "song_id",
                "description": "歌曲ID",
                "required": True,
                "type": "string"
            },
            {
                "name": "quality",
                "description": "音质等级",
                "required": False,
                "type": "string",
                "enum": ["standard", "exhigh", "lossless", "hires", "sky", "jyeffect", "jymaster"]
            }
        ]
    )
    def mcp_download_music(self, song_id: str, quality: Optional[str] = None) -> dict:
        """MCP音乐下载工具"""
        if not self._enabled:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "插件未启用"
                    }
                ],
                "isError": True
            }
        
        try:
            # 使用传入的音质参数，如果没有传入则使用配置的默认音质
            download_quality = quality or self._default_quality or self.DEFAULT_QUALITY
            result = self._api_tester.download_music_for_link(song_id, download_quality)
            
            if result.get("success"):
                data = result.get("data", {})
                song_name = data.get("name", "未知歌曲")
                artist = data.get("artist", "未知艺术家")
                quality_name = data.get("quality_name", "未知音质")
                file_size = data.get("file_size_formatted", "未知大小")
                file_path = data.get("file_path", "")
                
                response_text = f"✅ 下载完成!\n\n歌曲: {song_name}\n艺术家: {artist}\n音质: {quality_name}\n文件大小: {file_size}"
                
                # 如果配置了openlist地址，则添加链接信息
                if self._openlist_url and file_path:
                    # 从路径中提取文件名
                    filename = file_path.split("/")[-1]
                    openlist_link = f"{self._openlist_url.rstrip('/')}/{filename}"
                    response_text += f"\n\n🔗 下载链接: {openlist_link}"
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ],
                    "isError": False
                }
            else:
                error_msg = result.get("message", "下载失败")
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"下载失败: {error_msg}"
                        }
                    ],
                    "isError": True
                }
        except Exception as e:
            logger.error(f"MCP音乐下载出错: {e}", exc_info=True)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"下载异常: {str(e)}"
                    }
                ],
                "isError": True
            }

    # 添加MCP提示：音乐推荐
    @mcp_prompt(
        name="music-recommendation-prompt",
        description="音乐推荐提示",
        parameters=[
            {
                "name": "genre",
                "description": "音乐类型/风格",
                "required": False,
                "type": "string"
            },
            {
                "name": "mood",
                "description": "情绪/氛围",
                "required": False,
                "type": "string"
            }
        ]
    )
    def music_recommendation_prompt(self, genre: str = "", mood: str = "") -> dict:
        """音乐推荐提示"""
        prompt_parts = ["请推荐一些音乐"]
        
        if genre:
            prompt_parts.append(f"类型为{genre}")
        if mood:
            prompt_parts.append(f"适合{mood}时听")
            
        prompt_text = "，".join(prompt_parts)
        if not genre and not mood:
            prompt_text = "请推荐一些好听的音乐"
            
        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": prompt_text
                    }
                }
            ]
        }

    # 添加MCP工具：获取音质选项
    @mcp_tool(
        name="netease-music-get-qualities",
        description="获取网易云音乐支持的音质选项",
        parameters=[]
    )
    def mcp_get_qualities(self) -> dict:
        """MCP获取音质选项工具"""
        if not self._enabled:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "插件未启用"
                    }
                ],
                "isError": True
            }
        
        try:
            # 定义音质选项
            quality_options = [
                {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
                {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
                {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
                {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
                {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
                {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
                {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
            ]
            
            # 格式化音质信息
            quality_list = []
            for quality in quality_options:
                quality_list.append(f"• {quality['name']} ({quality['code']}): {quality['desc']}")
            
            response_text = "🎵 网易云音乐支持的音质选项:\n\n" + "\n".join(quality_list)
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": response_text
                    }
                ],
                "isError": False
            }
        except Exception as e:
            logger.error(f"MCP获取音质选项出错: {e}", exc_info=True)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"获取音质选项异常: {str(e)}"
                    }
                ],
                "isError": True
            }

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
        openlist_url_placeholder = self._openlist_url or "https://openlist.example.com/music"
        
        logger.debug(f"表单占位符值: base_url={base_url_placeholder}, search_limit={search_limit_placeholder}, "
                    f"openlist_url={openlist_url_placeholder}")
        
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
                                            'model': 'openlist_url',
                                            'label': 'OpenList地址',
                                            'placeholder': openlist_url_placeholder
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
            "default_quality": self._default_quality,
            "openlist_url": self._openlist_url
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
        处理 /y 和 /n 命令。
        /y 用于发起搜索。
        /n 用于在需要选择音质时响应。
        """
        if not self._enabled:
            return
            
        event_data = event.event_data
        action = event_data.get("action")
        
        if action == "netease_music_download":
            # 这是 /y 命令的入口
            self._handle_music_search(event)
        elif action == "netease_music_select":
            # 这是 /n 命令的入口，现在专门用于处理需要手动输入数字的场景（如选择音质）
            self._handle_manual_selection(event)
        else:
            logger.info(f"未知的动作类型: {action}")

    def _send_song_list_with_buttons(self, event: Event, search_query: str, songs: List[Dict]):
        """
        【新增】构建并发送带有交互按钮的歌曲列表消息。
        """
        event_data = event.event_data
        channel = event_data.get("channel")
        source = event_data.get("source")
        userid = event_data.get("userid") or event_data.get("user")

        if not songs:
            self.post_message(
                channel=channel, source=source, userid=userid,
                title=f"【{search_query}】",
                text="❌ 未找到相关歌曲。"
            )
            return

        text_parts = [f"🔍 为“{search_query}”找到 {len(songs)} 首相关歌曲："]
        buttons = []
        
        for i, song in enumerate(songs, 1):
            name = song.get('name', '未知歌曲')
            artists = song.get('artists', '') or song.get('ar_name', '')
            text_parts.append(f"{i}. {name} - {artists}")

            # 为每首歌创建一个按钮
            song_id = song.get('id')
            if song_id:
                button_text = f"下载 {name}"
                callback_data = f"[PLUGIN]{self.__class__.__name__}|select_song_{song_id}"
                # 每行一个下载按钮，更清晰
                buttons.append([{"text": button_text, "callback_data": callback_data}])
            
        self.post_message(
            channel=channel,
            source=source,
            userid=userid,
            title="搜索结果",
            text="请选择歌曲：",
            buttons=buttons
        )

    def _handle_music_search(self, event: Event):
        """
        处理 /y 命令发起的音乐搜索。
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
            logger.info(f"用户 {userid} 触发音乐下载命令，但未提供参数")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音乐下载",
                    text="请输入要搜索的歌曲名称或歌手，例如：/y 周杰伦",
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
                # 发送简单的错误文本消息
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音乐搜索失败",
                    text=response,
                    userid=userid
                )
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
                    
                    # 【核心改造】调用新的按钮消息发送函数
                    self._send_song_list_with_buttons(event, command_args, songs)
                    return  # 直接返回，不再执行原来的文本格式化逻辑
        
            # 发送结果（仅在没有找到歌曲时执行）
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 音乐搜索结果",
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
                    title="🎵 音乐下载",
                    text="❌ 搜索时发生错误，请稍后重试",
                    userid=userid
                )
            except Exception as e2:
                logger.error(f"发送错误消息失败: {e2}", exc_info=True)

    def _send_quality_selection_message(self, event: Event, song_id_str: str):
        """
        【新增】发送音质选择消息，可以使用按钮或文本列表。
        这里我们继续使用文本列表 + /n 数字的交互，因为音质选项固定，无需动态生成。
        """
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        
        # 【重要】更新会话，告知系统当前正在等待用户为哪个 song_id 选择音质
        session_data = {
            "state": "waiting_for_quality_choice",
            "data": {"song_id": song_id_str}
        }
        self._update_session(userid, session_data)
        
        response = self._format_quality_list()
        
        # 编辑原消息或发送新消息
        self.post_message(
            channel=event_data.get("channel"),
            source=event_data.get("source"),
            userid=userid,
            title="🎵 请选择音质",
            text=response,
            original_message_id=event_data.get("original_message_id"),
            original_chat_id=event_data.get("original_chat_id")
        )

    def _handle_manual_selection(self, event: Event):
        """
        【重构】处理 /n 命令，现在主要用于音质选择。
        """
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        session = self._get_session(userid)

        if not session or session.get("state") != "waiting_for_quality_choice":
            # 如果不是在等待音质选择，则忽略此命令或给出提示
            return
            
        song_id_str = session["data"].get("song_id")
        if not song_id_str:
            return

        command_args = event_data.get("arg_str", "").strip()
        
        quality_options = [ "standard", "exhigh", "lossless", "hires", "sky", "jyeffect", "jymaster" ]
        try:
            quality_index = int(command_args) - 1
            if 0 <= quality_index < len(quality_options):
                quality_code = quality_options[quality_index]
                self._download_song_by_id(event, song_id_str, quality_code)
            else:
                # 序号无效
                pass 
        except ValueError:
            # 输入不是数字
            pass

    def _handle_song_selection_by_id(self, event: Event, song_id_str: str):
        """
        【新增】通过按钮回调接收到 song_id 后的处理器。
        """
        default_quality = self._default_quality or self.DEFAULT_QUALITY
        if default_quality == "ask":
            # 如果需要询问音质，显示音质选择
            self._send_quality_selection_message(event, song_id_str)
        else:
            # 否则，直接使用默认音质下载
            self._download_song_by_id(event, song_id_str, default_quality)

    # 【废弃】以下方法不再需要，可以安全删除
    # - _format_song_list_page
    # - _handle_music_select (大部分逻辑已移入 _handle_manual_selection 和 message_action)
    # - _handle_quality_selection
    # - _download_song_with_quality (逻辑已合并到 _download_song_by_id)
    # - _send_song_list_as_wechat_articles

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

    def _download_song_by_id(self, event: Event, song_id_str: str, quality_code: str):
        """
        【重构】最终的下载执行函数，不再依赖会话中的 song 对象。
        """
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        
        # 清理会话，交互结束
        self._sessions.pop(userid, None)

        # 【优化】因为没有 song 对象，我们需要先获取一下歌曲信息来显示给用户
        # 这是一个可选的API调用，可以提升用户体验
        # 使用搜索功能获取歌曲信息（通过ID搜索）
        song_search_result = self._api_tester.search_music(song_id_str, limit=1)
        song_name = "未知歌曲"
        artist = "未知艺术家"
        
        if song_search_result.get("success"):
            songs = song_search_result.get("data", [])
            if songs:
                song_info = songs[0]
                song_name = song_info.get('name', f"歌曲ID {song_id_str}")
                artist = song_info.get('artists', '') or song_info.get('ar_name', '未知艺术家')
        
        # 发送“正在下载”的提示，并编辑原消息
        self.post_message(
            channel=event_data.get("channel"),
            source=event_data.get("source"),
            userid=userid,
            title="🎵 音乐下载",
            text=f"📥 开始下载: {song_name} - {artist}\n请稍候...",
            original_message_id=event_data.get("original_message_id"),
            original_chat_id=event_data.get("original_chat_id")
        )
        
        try:
            download_result = self._api_tester.download_music_for_link(song_id_str, quality_code)
            
            if download_result.get("success"):
                data = download_result.get("data", {})
                file_path = data.get("file_path", "")
                response_text = f"✅ 下载完成!\n歌曲: {song_name}\n艺术家: {artist}"
                if self._openlist_url and file_path:
                    filename = file_path.split("/")[-1]
                    response_text += f"\n🔗 下载链接: {self._openlist_url.rstrip('/')}/{filename}"
            else:
                error_msg = download_result.get('message', '未知错误')
                response_text = f"❌ 下载失败: {error_msg}"
        except Exception as e:
            logger.error(f"下载歌曲时发生异常: {e}", exc_info=True)
            response_text = "❌ 下载失败: 网络异常，请稍后重试"

        # 再次编辑消息，显示最终结果
        self.post_message(
            channel=event_data.get("channel"),
            source=event_data.get("source"),
            userid=userid,
            title="🎵 音乐下载完成",
            text=response_text,
            original_message_id=event_data.get("original_message_id"),
            original_chat_id=event_data.get("original_chat_id")
        )

    @eventmanager.register(EventType.MessageAction)
    def message_action(self, event: Event):
        """
        【新增】处理消息按钮的回调事件，这是现代交互的核心。
        """
        if not self._enabled:
            return
            
        event_data = event.event_data
        if not event_data:
            return
            
        # 检查是否为本插件的回调
        plugin_id = event_data.get("plugin_id")
        if plugin_id != self.__class__.__name__:
            return
            
        # 获取回调数据
        callback_text = event_data.get("text", "")
        
        # 解析回调内容，并分发到不同的处理器
        if callback_text.startswith("select_song_"):
            song_id_str = callback_text.replace("select_song_", "")
            self._handle_song_selection_by_id(event, song_id_str)
        elif callback_text.startswith("select_quality_"):
            parts = callback_text.replace("select_quality_", "").split("_")
            if len(parts) == 2:
                song_id_str, quality_code = parts
                self._download_song_by_id(event, song_id_str, quality_code)

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
                                                        'text': '音乐下载插件'
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCardText',
                                                'content': [
                                                    {
                                                        'component': 'p',
                                                        'text': '通过命令直接搜索并下载歌曲'
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
                                                                'text': '在聊天中发送"/y 歌曲名/歌手名"直接搜索音乐'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '从搜索结果中点击下载按钮进行下载（推荐方式）'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '或使用"/n 数字"选择歌曲序号进行下载'
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
                                                                'text': 'API基础URL：音乐API服务的基础URL，默认为http://localhost:5000'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认搜索数量：搜索歌曲时返回的结果数量，默认为8首'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认音质：下载歌曲的默认音质，支持多种音质选项'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': 'OpenList地址：歌曲下载完成后的链接地址'
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
                                            'text': '音乐下载'
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
                "cmd": "/y",
                "event": EventType.PluginAction,
                "desc": "音乐下载",
                "category": "媒体搜索",
                "data": {
                    "action": "netease_music_download"
                }
            },
            {
                "cmd": "/n",
                "event": EventType.PluginAction,
                "desc": "歌曲选择",
                "category": "媒体搜索",
                "data": {
                    "action": "netease_music_select"
                }
            }
        ]
