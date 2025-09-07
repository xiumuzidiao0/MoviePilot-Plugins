import json
from typing import Any, List, Dict, Tuple, Optional
import sys
import os

from .test_api import NeteaseMusicAPITester

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
    plugin_icon = ""
    # 插件版本
    plugin_version = "1.01"
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
    DEFAULT_BASE_URL = "http://localhost:5100"
    DEFAULT_SEARCH_LIMIT = 10
    DEFAULT_QUALITY = "exhigh"

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
        
        # 初始化会话存储
        self._sessions = {}
        logger.info("插件初始化完成")

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
        - 启用插件开关
        - 默认音质
        - 默认搜索数量
        - 配置API基础URL
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
        userid = event.event_data.get("userid")
        channel = event.event_data.get("channel")
        
        if not text or not userid:
            logger.warning("消息缺少必要信息: text或userid为空")
            return
            
        logger.info(f"收到用户消息: {text} (用户: {userid})")
        
        # 处理用户消息
        try:
            response = self._process_user_message(userid, text)
            logger.debug(f"消息处理完成，回复内容: {response}")
        except Exception as e:
            logger.error(f"处理用户消息时发生错误: {e}", exc_info=True)
            response = "❌ 处理消息时发生错误，请稍后重试"
        
        # 发送回复消息
        if response:
            logger.debug(f"发送回复消息到频道 {channel}，用户 {userid}")
            self.post_message(channel=channel, title=response, userid=userid)

    def _process_user_message(self, userid: str, text: str) -> Optional[str]:
        """
        处理用户消息并生成回复
        
        :param userid: 用户ID
        :param text: 消息文本
        :return: 回复内容
        """
        logger.debug(f"开始处理用户 {userid} 的消息: {text}")
        
        # 获取用户会话状态
        session = self._sessions.get(userid, {})
        state = session.get("state", "idle")
        
        logger.debug(f"用户 {userid} 当前会话状态: {state}")
        
        # 根据会话状态处理消息
        try:
            if state == "idle":
                result = self._handle_idle_state(userid, text)
            elif state == "waiting_for_keyword":
                result = self._handle_waiting_for_keyword(userid, text)
            elif state == "waiting_for_song_choice":
                result = self._handle_waiting_for_song_choice(userid, text)
            elif state == "waiting_for_quality_choice":
                result = self._handle_waiting_for_quality_choice(userid, text)
            else:
                # 重置状态
                logger.warning(f"用户 {userid} 处于未知状态 {state}，重置会话")
                self._sessions[userid] = {"state": "idle"}
                result = "抱歉，会话状态异常，已重置。请重新开始下载流程。"
                
            logger.debug(f"用户 {userid} 消息处理结果: {result}")
            return result
        except Exception as e:
            logger.error(f"处理用户 {userid} 消息时发生异常: {e}", exc_info=True)
            return "❌ 处理消息时发生错误，请稍后重试"

    def _handle_idle_state(self, userid: str, text: str) -> str:
        """
        处理空闲状态下的用户消息
        """
        logger.debug(f"用户 {userid} 处于空闲状态，收到消息: {text}")
        
        # 检查是否是开始下载的关键词
        if any(keyword in text.lower() for keyword in ["下载音乐", "下载歌曲", "网易云音乐", "netease"]):
            logger.info(f"用户 {userid} 启动下载流程")
            # 设置会话状态为等待关键词输入
            self._sessions[userid] = {
                "state": "waiting_for_keyword",
                "data": {}
            }
            logger.debug(f"用户 {userid} 会话状态已更新为: waiting_for_keyword")
            return "🎵 请输入要搜索的歌曲名称或歌手:"
        
        # 默认回复
        logger.debug(f"用户 {userid} 发送普通消息，返回默认回复")
        return "您好！发送'下载音乐'来开始下载网易云音乐歌曲。"

    def _handle_waiting_for_keyword(self, userid: str, text: str) -> str:
        """
        处理等待关键词状态下的用户消息
        """
        logger.debug(f"用户 {userid} 处于等待关键词状态，收到消息: {text}")
        
        session = self._sessions[userid]
        data = session.get("data", {})
        
        # 保存搜索关键词
        data["keyword"] = text
        logger.info(f"用户 {userid} 设置搜索关键词: {text}")
        
        # 搜索歌曲
        search_limit = self._search_limit or self.DEFAULT_SEARCH_LIMIT
        logger.debug(f"开始搜索歌曲: 关键词={text}, 限制数量={search_limit}")
        
        try:
            search_result = self._api_tester.search_music(text, limit=search_limit)
            logger.debug(f"搜索完成，结果: success={search_result.get('success')}, "
                        f"歌曲数量={len(search_result.get('data', []))}")
        except Exception as e:
            logger.error(f"搜索歌曲时发生异常: {e}", exc_info=True)
            self._sessions[userid] = {"state": "idle"}
            return f"❌ 搜索失败: 网络异常，请稍后重试"
        
        if not search_result.get("success"):
            error_msg = search_result.get('message', '未知错误')
            logger.warning(f"用户 {userid} 搜索失败: {error_msg}")
            self._sessions[userid] = {"state": "idle"}
            return f"❌ 搜索失败: {error_msg}"
        
        songs = search_result.get("data", [])
        if not songs:
            logger.info(f"用户 {userid} 搜索未找到结果: {text}")
            self._sessions[userid] = {"state": "idle"}
            return "❌ 未找到相关歌曲，请尝试其他关键词。"
        
        # 保存搜索结果
        data["songs"] = songs
        self._sessions[userid] = {
            "state": "waiting_for_song_choice",
            "data": data
        }
        logger.debug(f"用户 {userid} 搜索结果已保存，会话状态更新为: waiting_for_song_choice")
        
        # 构造歌曲列表回复
        response = f"🔍 搜索到 {len(songs)} 首歌曲，请选择要下载的歌曲:\n"
        for i, song in enumerate(songs, 1):
            name = song.get('name', '')
            artists = song.get('artists', '') or song.get('ar_name', '')
            response += f"{i}. {name} - {artists}\n"
        response += f"请输入歌曲序号 (1-{len(songs)}):"
        
        logger.debug(f"用户 {userid} 收到歌曲列表，共 {len(songs)} 首歌曲")
        return response

    def _handle_waiting_for_song_choice(self, userid: str, text: str) -> str:
        """
        处理等待歌曲选择状态下的用户消息
        """
        logger.debug(f"用户 {userid} 处于等待歌曲选择状态，收到消息: {text}")
        
        session = self._sessions[userid]
        data = session.get("data", {})
        songs = data.get("songs", [])
        
        # 处理歌曲选择
        try:
            song_index = int(text) - 1
            logger.debug(f"用户 {userid} 选择歌曲序号: {text} (索引: {song_index})")
            
            if 0 <= song_index < len(songs):
                selected_song = songs[song_index]
                song_name = selected_song.get('name', '')
                song_artists = selected_song.get('artists', '') or selected_song.get('ar_name', '')
                data["selected_song"] = selected_song
                
                logger.info(f"用户 {userid} 选择歌曲: {song_name} - {song_artists}")
                
                # 询问音质选择
                self._sessions[userid] = {
                    "state": "waiting_for_quality_choice",
                    "data": data
                }
                logger.debug(f"用户 {userid} 会话状态更新为: waiting_for_quality_choice")
                
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
                
                logger.debug(f"用户 {userid} 收到音质选择列表，共 {len(quality_options)} 种音质")
                return response
            else:
                logger.warning(f"用户 {userid} 选择的歌曲序号超出范围: {song_index} (有效范围: 0-{len(songs)-1})")
                return f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字"
        except ValueError:
            logger.warning(f"用户 {userid} 输入的歌曲序号无效: {text}")
            return "❌ 请输入有效的数字序号"

    def _handle_waiting_for_quality_choice(self, userid: str, text: str) -> str:
        """
        处理等待音质选择状态下的用户消息
        """
        logger.debug(f"用户 {userid} 处于等待音质选择状态，收到消息: {text}")
        
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
            logger.debug(f"用户 {userid} 选择音质序号: {text} (索引: {quality_index})")
            
            if 0 <= quality_index < len(quality_options):
                selected_quality = quality_options[quality_index]
                data["selected_quality"] = selected_quality
                
                # 获取歌曲信息
                song_id = str(selected_song.get('id', ''))
                quality_code = selected_quality['code']
                song_name = selected_song.get('name', '')
                artist = selected_song.get('artists', '') or selected_song.get('ar_name', '')
                quality_name = selected_quality['name']
                
                logger.info(f"用户 {userid} 选择音质: {quality_name}，准备下载歌曲: {song_name} - {artist}")
                
                # 重置会话状态
                self._sessions[userid] = {"state": "idle"}
                logger.debug(f"用户 {userid} 会话状态重置为: idle")
                
                # 执行下载
                response = f"📥 开始下载: {song_name} - {artist} ({quality_name})\n请稍候..."
                logger.debug(f"开始下载歌曲 {song_id}，音质: {quality_code}")
                
                try:
                    download_result = self._api_tester.download_music_for_link(song_id, quality_code)
                    logger.debug(f"下载完成，结果: success={download_result.get('success')}")
                except Exception as e:
                    logger.error(f"下载歌曲时发生异常: {e}", exc_info=True)
                    return f"❌ 下载失败: 网络异常，请稍后重试"
                
                if download_result.get("success"):
                    response += "\n✅ 下载完成!"
                    logger.info(f"用户 {userid} 下载完成: {song_name} - {artist} ({quality_name})")
                else:
                    error_msg = download_result.get('message', '未知错误')
                    response += f"\n❌ 下载失败: {error_msg}"
                    logger.warning(f"用户 {userid} 下载失败: {error_msg}")
                
                return response
            else:
                logger.warning(f"用户 {userid} 选择的音质序号超出范围: {quality_index} (有效范围: 0-{len(quality_options)-1})")
                return f"❌ 序号超出范围，请输入 1-{len(quality_options)} 之间的数字"
        except ValueError:
            logger.warning(f"用户 {userid} 输入的音质序号无效: {text}")
            return "❌ 请输入有效的数字序号"

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
                                                        'text': '通过消息交互下载网易云音乐歌曲'
                                                    },
                                                    {
                                                        'component': 'p',
                                                        'text': '使用方法：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': '在聊天中发送"下载音乐"开始下载流程'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '输入歌曲名称或歌手进行搜索'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '从搜索结果中选择歌曲'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '选择下载音质'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'p',
                                                        'text': '配置说明：'
                                                    },
                                                    {
                                                        'component': 'ul',
                                                        'content': [
                                                            {
                                                                'component': 'li',
                                                                'text': 'API基础URL：网易云音乐API服务的基础URL'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认搜索数量：搜索歌曲时返回的结果数量'
                                                            },
                                                            {
                                                                'component': 'li',
                                                                'text': '默认音质：下载歌曲的默认音质'
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
