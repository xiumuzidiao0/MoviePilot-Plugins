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

# 导入MCP插件助手
try:
    from app.plugins.mcpserver.dev.mcp_dev import (
        mcp_tool,
        mcp_prompt,
        MCPDecoratorMixin
    )
    MCP_DEV_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MCPServer插件不可用，MCP功能将被禁用。错误详情: {str(e)}")
    MCP_DEV_AVAILABLE = False

    # 定义空的装饰器，避免语法错误
    def mcp_tool(*args, **kwargs):
        """空的MCP工具装饰器，当MCP不可用时使用"""
        def decorator(func):
            return func
        return decorator

    def mcp_prompt(*args, **kwargs):
        """空的MCP提示装饰器，当MCP不可用时使用"""
        def decorator(func):
            return func
        return decorator

    # 定义空的Mixin类
    class MCPDecoratorMixin:
        """空的MCP装饰器混入类，当MCP不可用时使用"""
        pass


class NeteaseMusic(_PluginBase, MCPDecoratorMixin):
    # 插件名称
    plugin_name = "网易云音乐下载"
    # 插件描述
    plugin_desc = "通过命令直接搜索并下载歌曲"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/xiumuzidiao0/MoviePilot-Plugins/main/icons/163music_A.png"
    # 插件版本
    plugin_version = "1.24"
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
        logger.debug(f"插件初始化配置: {config}")
        
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
        
        # 初始化MCP功能
        if MCP_DEV_AVAILABLE:
            try:
                logger.info("初始化MCP功能")
                self.init_mcp_decorators()
            except Exception as e:
                logger.error(f"MCP初始化失败: {str(e)}")

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
        logger.debug(f"插件启用状态已更新: {self._enabled}")
        # 可以在这里添加其他启用/禁用时需要处理的逻辑

    # ==================== MCP工具和提示 ====================

    @mcp_tool(
        name="search_music",
        description="搜索网易云音乐歌曲",
        parameters=[
            {
                "name": "keyword",
                "description": "搜索关键词，可以是歌曲名或歌手名",
                "required": True,
                "type": "string"
            },
            {
                "name": "limit",
                "description": "返回结果数量，默认为8",
                "required": False,
                "type": "integer"
            }
        ]
    )
    def search_music_tool(self, keyword: str, limit: int = 8) -> dict:
        """搜索音乐工具"""
        logger.info(f"[MCP工具] 开始搜索音乐: keyword={keyword}, limit={limit}")
        if not self._enabled:
            logger.warning("[MCP工具] 插件未启用")
            return {"success": False, "message": "插件未启用"}
        
        try:
            # 使用配置的搜索限制或默认值
            search_limit = limit or self._search_limit or self.DEFAULT_SEARCH_LIMIT
            logger.debug(f"[MCP工具] 搜索参数: search_limit={search_limit}")
            # 确保API测试器已初始化
            if not hasattr(self, '_api_tester') or not self._api_tester:
                logger.warning("[MCP工具] API测试器未初始化，正在重新初始化")
                api_base_url = self._base_url or self.DEFAULT_BASE_URL
                self._api_tester = NeteaseMusicAPITester(base_url=api_base_url)
                logger.info(f"[MCP工具] API测试器重新初始化完成，基础URL: {api_base_url}")
            
            search_result = self._api_tester.search_music(keyword, limit=search_limit)
            logger.debug(f"[MCP工具] 搜索结果: {search_result}")
            
            if search_result.get("success"):
                songs = search_result.get("data", [])
                formatted_songs = []
                for i, song in enumerate(songs, 1):
                    name = song.get('name', '')
                    artists = song.get('artists', '') or song.get('ar_name', '')
                    song_id = song.get('id', '')
                    album = song.get('album', '')
                    pic_url = song.get('picUrl', '')
                    formatted_songs.append({
                        "index": i,
                        "id": song_id,
                        "name": name,
                        "artists": artists,
                        "album": album,
                        "pic_url": pic_url
                    })
                
                logger.info(f"[MCP工具] 搜索完成，找到{len(formatted_songs)}首歌曲")
                return {
                    "success": True,
                    "songs": formatted_songs,
                    "total": len(formatted_songs),
                    "message": f"搜索完成，找到{len(formatted_songs)}首歌曲"
                }
            else:
                error_msg = search_result.get('message', '搜索失败')
                logger.warning(f"[MCP工具] 搜索失败: {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }
        except Exception as e:
            logger.error(f"[MCP工具] 搜索音乐时发生异常: {e}", exc_info=True)
            return {"success": False, "message": f"搜索异常: {str(e)}"}

    @mcp_tool(
        name="download_music",
        description="下载网易云音乐歌曲",
        parameters=[
            {
                "name": "song_id",
                "description": "歌曲ID",
                "required": True,
                "type": "string"
            },
            {
                "name": "quality",
                "description": "音质等级，可选值: standard, exhigh, lossless, hires, sky, jyeffect, jymaster",
                "required": False,
                "type": "string",
                "enum": ["standard", "exhigh", "lossless", "hires", "sky", "jyeffect", "jymaster"]
            }
        ]
    )
    def download_music_tool(self, song_id: str, quality: str = "exhigh") -> dict:
        """下载音乐工具"""
        logger.info(f"[MCP工具] 开始下载音乐: song_id={song_id}, quality={quality}")
        if not self._enabled:
            logger.warning("[MCP工具] 插件未启用")
            return {"success": False, "message": "插件未启用"}
        
        try:
            # 使用配置的默认音质或参数指定的音质
            download_quality = quality or self._default_quality or self.DEFAULT_QUALITY
            logger.debug(f"[MCP工具] 下载参数: download_quality={download_quality}")
            # 确保API测试器已初始化
            if not hasattr(self, '_api_tester') or not self._api_tester:
                logger.warning("[MCP工具] API测试器未初始化，正在重新初始化")
                api_base_url = self._base_url or self.DEFAULT_BASE_URL
                self._api_tester = NeteaseMusicAPITester(base_url=api_base_url)
                logger.info(f"[MCP工具] API测试器重新初始化完成，基础URL: {api_base_url}")
                
            download_result = self._api_tester.download_music_for_link(song_id, download_quality)
            logger.debug(f"[MCP工具] 下载结果: {download_result}")
            
            if download_result.get("success"):
                data = download_result.get("data", {})
                file_path = data.get("file_path", "")
                song_name = data.get("name", "")
                artist = data.get("artist", "")
                album = data.get("album", "")
                file_size = data.get("file_size_formatted", "")
                file_type = data.get("file_type", "")
                pic_url = data.get("pic_url", "")
                
                # 提取文件名
                filename = ""
                if file_path:
                    filename = file_path.split("/")[-1]
                
                result = {
                    "success": True,
                    "song_id": song_id,
                    "song_name": song_name,
                    "artist": artist,
                    "album": album,
                    "quality": download_quality,
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": file_size,
                    "file_type": file_type,
                    "pic_url": pic_url,
                    "message": "下载完成"
                }
                
                # 如果配置了openlist地址，添加下载链接
                if self._openlist_url and filename:
                    openlist_link = f"{self._openlist_url.rstrip('/')}/{filename}"
                    result["download_link"] = openlist_link
                    logger.debug(f"[MCP工具] 添加OpenList链接: {openlist_link}")
                
                logger.info(f"[MCP工具] 下载完成: filename={filename}")
                return result
            else:
                error_msg = download_result.get('message', '下载失败')
                logger.warning(f"[MCP工具] 下载失败: {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }
        except Exception as e:
            logger.error(f"[MCP工具] 下载音乐时发生异常: {e}", exc_info=True)
            return {"success": False, "message": f"下载异常: {str(e)}"}

    @mcp_tool(
        name="get_supported_qualities",
        description="获取支持的音质选项",
        parameters=[]
    )
    def get_supported_qualities_tool(self) -> dict:
        """获取支持的音质选项工具"""
        logger.info("[MCP工具] 获取支持的音质选项")
        if not self._enabled:
            logger.warning("[MCP工具] 插件未启用")
            return {"success": False, "message": "插件未启用"}
        
        try:
            quality_options = [
                {"code": "standard", "name": "标准音质", "desc": "128kbps MP3"},
                {"code": "exhigh", "name": "极高音质", "desc": "320kbps MP3"},
                {"code": "lossless", "name": "无损音质", "desc": "FLAC"},
                {"code": "hires", "name": "Hi-Res音质", "desc": "24bit/96kHz"},
                {"code": "sky", "name": "沉浸环绕声", "desc": "空间音频"},
                {"code": "jyeffect", "name": "高清环绕声", "desc": "环绕声效果"},
                {"code": "jymaster", "name": "超清母带", "desc": "母带音质"}
            ]
            
            logger.info("[MCP工具] 成功获取音质选项列表")
            return {
                "success": True,
                "qualities": quality_options,
                "message": "获取音质选项成功"
            }
        except Exception as e:
            logger.error(f"[MCP工具] 获取音质选项时发生异常: {e}", exc_info=True)
            return {"success": False, "message": f"获取音质选项异常: {str(e)}"}

    @mcp_tool(
        name="test_connection",
        description="测试网易云音乐API连接",
        parameters=[
            {
                "name": "url",
                "description": "API基础URL，如果为空则使用插件配置的URL",
                "required": False,
                "type": "string"
            }
        ]
    )
    def test_connection_tool(self, url: str = "") -> dict:
        """测试API连接工具"""
        logger.info(f"[MCP工具] 测试API连接: url={url}")
        if not self._enabled:
            logger.warning("[MCP工具] 插件未启用")
            return {"success": False, "message": "插件未启用"}
        
        try:
            # 确保API测试器已初始化
            if not hasattr(self, '_api_tester') or not self._api_tester:
                logger.warning("[MCP工具] API测试器未初始化，正在重新初始化")
                api_base_url = self._base_url or self.DEFAULT_BASE_URL
                self._api_tester = NeteaseMusicAPITester(base_url=api_base_url)
                logger.info(f"[MCP工具] API测试器重新初始化完成，基础URL: {api_base_url}")
            
            # 使用提供的URL或当前配置的URL
            api_url = url or self._base_url or self.DEFAULT_BASE_URL
            logger.debug(f"[MCP工具] 测试API地址: {api_url}")
            
            # 测试健康检查接口
            test_url = f"{api_url.rstrip('/')}/health"
            logger.debug(f"[MCP工具] 健康检查URL: {test_url}")
            
            response = self._api_tester.session.get(test_url, timeout=10)
            logger.debug(f"[MCP工具] 健康检查响应: status_code={response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"[MCP工具] API连接测试成功: {api_url}")
                return {
                    "success": True,
                    "message": f"成功连接到API服务器: {api_url}",
                    "url": api_url,
                    "status_code": response.status_code
                }
            else:
                logger.warning(f"[MCP工具] API连接测试失败: status_code={response.status_code}")
                return {
                    "success": False,
                    "message": f"连接失败，状态码: {response.status_code}",
                    "url": api_url,
                    "status_code": response.status_code
                }
        except Exception as e:
            logger.error(f"[MCP工具] API连接测试异常: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"连接异常: {str(e)}",
                "url": url or self._base_url or self.DEFAULT_BASE_URL
            }

    @mcp_prompt(
        name="music-search-prompt",
        description="音乐搜索提示，帮助用户构建搜索查询",
        parameters=[
            {
                "name": "user_request",
                "description": "用户的音乐搜索请求",
                "required": True
            }
        ]
    )
    def music_search_prompt(self, user_request: str) -> dict:
        """音乐搜索提示"""
        logger.info(f"[MCP提示] 生成音乐搜索提示: user_request={user_request}")
        
        prompt_content = (
            f"# 网易云音乐搜索查询构建\n\n"
            f"用户请求: **{user_request}**\n\n"
            f"## 请根据用户请求构建合适的搜索查询:\n"
            f"1. 提取关键词（歌曲名、歌手名、专辑名等）\n"
            f"2. 确保查询简洁明确\n"
            f"3. 避免使用特殊符号\n\n"
            f"## 示例格式:\n"
            f"- 周杰伦 告白气球\n"
            f"- 陈奕迅 十年\n"
            f"- 海阔天空 Beyond\n\n"
            f"请提供一个优化后的搜索查询字符串。"
        )

        logger.debug("[MCP提示] 音乐搜索提示生成完成")
        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": prompt_content
                    }
                }
            ]
        }

    @mcp_prompt(
        name="music-download-prompt",
        description="音乐下载提示，帮助用户选择合适的音质",
        parameters=[
            {
                "name": "song_info",
                "description": "歌曲信息",
                "required": True
            },
            {
                "name": "usage_scenario",
                "description": "使用场景（如日常听歌、收藏、专业用途等）",
                "required": False
            }
        ]
    )
    def music_download_prompt(self, song_info: str, usage_scenario: str = "") -> dict:
        """音乐下载提示"""
        logger.info(f"[MCP提示] 生成音乐下载提示: song_info={song_info}, usage_scenario={usage_scenario}")
        
        if usage_scenario:
            prompt_content = (
                f"# 网易云音乐下载音质选择\n\n"
                f"歌曲信息: **{song_info}**\n"
                f"使用场景: **{usage_scenario}**\n\n"
                f"## 请根据歌曲信息和使用场景推荐合适的音质:\n"
                f"1. 考虑文件大小和音质的平衡\n"
                f"2. 根据使用场景推荐音质等级\n"
                f"3. 简要说明推荐理由\n\n"
                f"## 音质选项:\n"
                f"- standard (128kbps MP3) - 标准音质\n"
                f"- exhigh (320kbps MP3) - 极高音质\n"
                f"- lossless (FLAC) - 无损音质\n"
                f"- hires (24bit/96kHz) - Hi-Res音质\n"
                f"- sky (空间音频) - 沉浸环绕声\n"
                f"- jyeffect (环绕声效果) - 高清环绕声\n"
                f"- jymaster (母带音质) - 超清母带\n\n"
                f"请推荐一个合适的音质选项。"
            )
        else:
            prompt_content = (
                f"# 网易云音乐下载音质选择\n\n"
                f"歌曲信息: **{song_info}**\n\n"
                f"## 请根据歌曲信息推荐合适的音质:\n"
                f"1. 考虑文件大小和音质的平衡\n"
                f"2. 根据歌曲类型推荐音质等级\n"
                f"3. 简要说明推荐理由\n\n"
                f"## 音质选项:\n"
                f"- standard (128kbps MP3) - 标准音质\n"
                f"- exhigh (320kbps MP3) - 极高音质\n"
                f"- lossless (FLAC) - 无损音质\n"
                f"- hires (24bit/96kHz) - Hi-Res音质\n"
                f"- sky (空间音频) - 沉浸环绕声\n"
                f"- jyeffect (环绕声效果) - 高清环绕声\n"
                f"- jymaster (母带音质) - 超清母带\n\n"
                f"请推荐一个合适的音质选项。"
            )

        logger.debug("[MCP提示] 音乐下载提示生成完成")
        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": prompt_content
                    }
                }
            ]
        }

    def stop_service(self):
        """插件停止时注销工具和提示"""
        logger.info("正在停止插件服务")
        try:
            if hasattr(self, 'stop_mcp_decorators') and MCP_DEV_AVAILABLE:
                # 停止MCP功能
                logger.debug("正在停止MCP功能")
                self.stop_mcp_decorators()
                logger.info("MCP功能已停止")
        except Exception as e:
            logger.error(f"停止MCP服务失败: {str(e)}")
        logger.info("插件服务已停止")

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
        logger.debug(f"[会话管理] 获取用户 {userid} 的会话数据")
        session = self._sessions.get(userid)
        logger.debug(f"[会话管理] 用户 {userid} 的原始会话数据: {session}")
        if not session:
            logger.debug(f"[会话管理] 用户 {userid} 没有会话数据")
            return None
            
        # 检查会话是否超时
        last_active = session.get("last_active", 0)
        current_time = time.time()
        time_diff = current_time - last_active
        logger.debug(f"[会话管理] 用户 {userid} 会话时间差: {time_diff}秒，超时设置: {self.SESSION_TIMEOUT}秒")
        if time_diff > self.SESSION_TIMEOUT:
            # 会话超时，清理并返回None
            logger.debug(f"[会话管理] 用户 {userid} 的会话已超时，清理会话数据")
            self._sessions.pop(userid, None)
            logger.info(f"[会话管理] 用户 {userid} 的会话已超时并清理")
            return None
            
        logger.debug(f"[会话管理] 用户 {userid} 的会话数据有效")
        return session

    def _update_session(self, userid: str, session_data: Dict):
        """
        更新用户会话数据
        
        :param userid: 用户ID
        :param session_data: 会话数据
        """
        logger.debug(f"[会话管理] 更新用户 {userid} 的会话数据: {session_data}")
        session_data["last_active"] = time.time()
        self._sessions[userid] = session_data
        logger.debug(f"[会话管理] 用户 {userid} 的会话数据已更新: {self._sessions[userid]}")

    @eventmanager.register(EventType.PluginAction)
    def command_action(self, event: Event):
        """
        远程命令响应
        """
        logger.info(f"[命令处理] 收到PluginAction事件: {event}")
        
        if not self._enabled:
            logger.info("[命令处理] 插件未启用")
            return
            
        event_data = event.event_data
        logger.debug(f"[命令处理] 事件数据: {event_data}")
        
        # 获取动作类型
        action = event_data.get("action") if event_data else None
        logger.debug(f"[命令处理] 动作类型: {action}")
        
        # 根据动作类型处理不同命令
        if action == "netease_music_download":
            logger.info("[命令处理] 处理音乐下载命令")
            self._handle_music_download(event)
        elif action == "netease_music_select":
            logger.info("[命令处理] 处理音乐选择命令")
            self._handle_music_select(event)
        else:
            logger.warning(f"[命令处理] 未知的动作类型: {action}")
            return

    def _handle_music_download(self, event: Event):
        """
        处理音乐下载命令
        """
        logger.info("[命令处理] 开始处理音乐下载命令")
        event_data = event.event_data
        # 从事件数据中获取用户ID，可能的字段名包括userid和user
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        
        if not userid:
            logger.warning("[命令处理] 用户ID为空")
            return
            
        # 获取命令参数（歌曲名/歌手名）
        command_args = event_data.get("arg_str", "").strip()
        logger.info(f"[命令处理] 用户 {userid} 触发音乐下载命令，参数: {command_args}")
        if not command_args:
            # 如果没有参数，提示用户输入
            logger.info(f"[命令处理] 用户 {userid} 触发音乐下载命令，但未提供参数")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音乐下载",
                    text="请输入要搜索的歌曲名称或歌手，例如：/y 周杰伦",
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"[命令处理] 发送提示消息失败: {e}", exc_info=True)
            return
        
        logger.info(f"[命令处理] 用户 {userid} 搜索音乐: {command_args}")
        
        # 直接执行搜索
        try:
            # 搜索歌曲
            search_limit = self._search_limit or self.DEFAULT_SEARCH_LIMIT
            logger.debug(f"[命令处理] 开始搜索歌曲: 关键词={command_args}, 限制数量={search_limit}")
            
            search_result = self._api_tester.search_music(command_args, limit=search_limit)
            logger.debug(f"[命令处理] 搜索完成，结果: success={search_result.get('success')}, "
                        f"歌曲数量={len(search_result.get('data', []))}")
            
            if not search_result.get("success"):
                error_msg = search_result.get('message', '未知错误')
                logger.warning(f"[命令处理] 用户 {userid} 搜索失败: {error_msg}")
                response = f"❌ 搜索失败: {error_msg}"
            else:
                songs = search_result.get("data", [])
                if not songs:
                    logger.info(f"[命令处理] 用户 {userid} 搜索未找到结果: {command_args}")
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
                    logger.debug(f"[命令处理] 用户 {userid} 搜索结果已保存到会话，时间戳: {session_data['data']['timestamp']}")
                    
                    # 显示第一页结果
                    response = self._format_song_list_page(userid, songs, 0)
        
            # 发送结果
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 音乐搜索结果",
                text=response,
                userid=userid
            )
            logger.info(f"[命令处理] 已向用户 {userid} 发送搜索结果")
        except Exception as e:
            logger.error(f"[命令处理] 搜索音乐时发生错误: {e}", exc_info=True)
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音乐下载",
                    text="❌ 搜索时发生错误，请稍后重试",
                    userid=userid
                )
            except Exception as e2:
                logger.error(f"[命令处理] 发送错误消息失败: {e2}", exc_info=True)

    def _format_song_list_page(self, userid: str, songs: List[Dict], page: int) -> str:
        """
        格式化歌曲列表页面
        
        :param userid: 用户ID
        :param songs: 歌曲列表
        :param page: 页码（从0开始）
        :return: 格式化后的页面内容
        """
        logger.debug(f"[页面格式化] 格式化用户 {userid} 的歌曲列表页面，页码: {page}")
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
        logger.debug(f"[页面格式化] 页面格式化完成，歌曲数量: {end_idx - start_idx}")
        return response

    def _handle_music_select(self, event: Event):
        """
        处理音乐选择命令
        """
        logger.info("[命令处理] 开始处理音乐选择命令")
        event_data = event.event_data
        # 从事件数据中获取用户ID，可能的字段名包括userid和user
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        
        if not userid:
            logger.warning("[命令处理] 用户ID为空")
            return
            
        # 获取命令参数（数字或翻页指令）
        command_args = event_data.get("arg_str", "").strip()
        logger.info(f"[命令处理] 用户 {userid} 触发音乐选择命令，参数: {command_args}")
        if not command_args:
            # 如果没有参数，提示用户输入
            logger.info(f"[命令处理] 用户 {userid} 触发音乐选择命令，但未提供参数")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text="请输入要选择的歌曲序号，例如：/n 1",
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"[命令处理] 发送提示消息失败: {e}", exc_info=True)
            return
        
        logger.info(f"[命令处理] 用户 {userid} 选择歌曲: {command_args}")
        
        # 检查用户是否有有效的搜索会话
        session = self._get_session(userid)
        if not session:
            logger.info(f"[命令处理] 用户 {userid} 没有有效的搜索会话")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text="请先使用 /y 命令搜索歌曲，然后使用 /n 数字 来选择歌曲下载",
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送提示消息")
            except Exception as e:
                logger.error(f"[命令处理] 发送提示消息失败: {e}", exc_info=True)
            return
        
        # 检查会话是否在有效时间内（5分钟内）
        data = session.get("data", {})
        timestamp = data.get("timestamp", 0)
        current_time = time.time()
        if current_time - timestamp > self.SESSION_TIMEOUT:
            logger.info(f"[命令处理] 用户 {userid} 的搜索会话已超时")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text="搜索结果已过期，请重新使用 /y 命令搜索歌曲",
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送提示消息")
                # 清理会话
                self._sessions.pop(userid, None)
            except Exception as e:
                logger.error(f"[命令处理] 发送提示消息失败: {e}", exc_info=True)
            return
        
        # 检查会话状态
        state = session.get("state")
        songs = data.get("songs", [])
        current_page = data.get("current_page", 0)
        PAGE_SIZE = 8
        
        logger.debug(f"[命令处理] 用户 {userid} 会话状态: {state}")
        # 根据会话状态处理不同情况
        if state == "waiting_for_quality_choice":
            # 处理音质选择
            selected_song = data.get("selected_song")
            if selected_song:
                logger.info(f"[命令处理] 处理用户 {userid} 的音质选择")
                return self._handle_quality_selection(event, selected_song)
        elif state == "waiting_for_song_choice":
            # 处理歌曲选择或翻页
            logger.debug(f"[命令处理] 用户 {userid} 处于歌曲选择状态")
            pass
        else:
            logger.warning(f"[命令处理] 用户 {userid} 会话状态无效: {state}")
            try:
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text="会话状态异常，请重新使用 /y 命令搜索歌曲",
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送提示消息")
                # 清理会话
                self._sessions.pop(userid, None)
            except Exception as e:
                logger.error(f"[命令处理] 发送提示消息失败: {e}", exc_info=True)
            return
        
        # 处理翻页指令
        if command_args.lower() == 'n':  # 下一页
            logger.info(f"[命令处理] 用户 {userid} 请求下一页")
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
                    title="🎵 音乐搜索结果",
                    text=response,
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送下一页搜索结果")
            else:
                response = "❌ 已经是最后一页了"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text=response,
                    userid=userid
                )
            return
        elif command_args.lower() == 'p':  # 上一页
            logger.info(f"[命令处理] 用户 {userid} 请求上一页")
            if current_page > 0:
                # 更新会话中的页码
                data["current_page"] = current_page - 1
                self._update_session(userid, {"state": "waiting_for_song_choice", "data": data})
                
                # 显示上一页
                response = self._format_song_list_page(userid, songs, current_page - 1)
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音乐搜索结果",
                    text=response,
                    userid=userid
                )
                logger.info(f"[命令处理] 已向用户 {userid} 发送上一页搜索结果")
            else:
                response = "❌ 已经是第一页了"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text=response,
                    userid=userid
                )
            return
        
        # 处理数字选择
        try:
            song_index = int(command_args) - 1
            logger.debug(f"[命令处理] 用户 {userid} 选择歌曲序号: {command_args} (索引: {song_index})")
            
            if 0 <= song_index < len(songs):
                selected_song = songs[song_index]
                song_name = selected_song.get('name', '')
                song_artists = selected_song.get('artists', '') or selected_song.get('ar_name', '')
                
                logger.info(f"[命令处理] 用户 {userid} 选择歌曲: {song_name} - {song_artists}")
                
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
                    logger.info(f"[命令处理] 已向用户 {userid} 发送音质选择列表")
                else:
                    # 使用默认音质下载
                    logger.info(f"[命令处理] 使用默认音质 {default_quality} 下载歌曲")
                    self._download_song_with_quality(event, selected_song, default_quality)
            else:
                logger.warning(f"[命令处理] 用户 {userid} 选择的歌曲序号超出范围: {song_index} (有效范围: 0-{len(songs)-1})")
                response = f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text=response,
                    userid=userid
                )
        except ValueError:
            logger.warning(f"[命令处理] 用户 {userid} 输入的歌曲序号无效: {command_args}")
            response = "❌ 请输入有效的数字序号或翻页指令 (/n n 下一页, /n p 上一页)"
            self.post_message(
                channel=channel,
                    source=source,
                    title="🎵 歌曲选择",
                    text=response,
                    userid=userid
            )

    def _handle_quality_selection(self, event: Event, selected_song: Dict):
        """
        处理音质选择
        
        :param event: 事件对象
        :param selected_song: 选中的歌曲
        """
        logger.info("[命令处理] 开始处理音质选择")
        event_data = event.event_data
        userid = event_data.get("userid") or event_data.get("user")
        channel = event_data.get("channel")
        source = event_data.get("source")
        command_args = event_data.get("arg_str", "").strip()
        
        logger.info(f"[命令处理] 用户 {userid} 选择音质，参数: {command_args}")
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
                
                logger.info(f"[命令处理] 用户 {userid} 选择音质: {quality_name}")
                
                # 重置会话状态
                self._update_session(userid, {"state": "idle"})
                
                # 下载歌曲
                logger.info(f"[命令处理] 开始下载歌曲，音质: {quality_code}")
                self._download_song_with_quality(event, selected_song, quality_code)
            else:
                logger.warning(f"[命令处理] 用户 {userid} 选择的音质序号超出范围: {quality_index}")
                response = f"❌ 序号超出范围，请输入 1-{len(quality_options)} 之间的数字"
                self.post_message(
                    channel=channel,
                    source=source,
                    title="🎵 音质选择",
                    text=response,
                    userid=userid
                )
        except ValueError:
            logger.warning(f"[命令处理] 用户 {userid} 输入的音质序号无效: {command_args}")
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
        logger.debug("[页面格式化] 格式化音质列表")
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
        logger.debug(f"[页面格式化] 音质列表格式化完成，选项数量: {len(quality_options)}")
        return response

    def _download_song_with_quality(self, event: Event, selected_song: Dict, quality_code: str):
        """
        使用指定音质下载歌曲
        
        :param event: 事件对象
        :param selected_song: 选中的歌曲
        :param quality_code: 音质代码
        """
        logger.info(f"[下载处理] 开始下载歌曲，音质代码: {quality_code}")
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
        
        logger.info(f"[下载处理] 用户 {userid} 准备下载歌曲: {song_name} - {artist} ({quality_name})")
        
        # 重置会话状态
        self._update_session(userid, {"state": "idle"})
        logger.debug(f"[下载处理] 用户 {userid} 会话状态重置为: idle")
        
        # 执行下载
        response = f"📥 开始下载: {song_name} - {artist} ({quality_name})\n请稍候..."
        logger.debug(f"[下载处理] 开始下载歌曲 {song_id}，音质: {quality_code}")
        
        try:
            download_result = self._api_tester.download_music_for_link(song_id, quality_code)
            logger.debug(f"[下载处理] 下载完成，结果: success={download_result.get('success')}")
        except Exception as e:
            logger.error(f"[下载处理] 下载歌曲时发生异常: {e}", exc_info=True)
            self.post_message(
                channel=channel,
                source=source,
                title="🎵 音乐下载",
                text="❌ 下载失败: 网络异常，请稍后重试",
                userid=userid
            )
            return
        
        if download_result.get("success"):
            response += "\n✅ 下载完成!"
            logger.info(f"[下载处理] 用户 {userid} 下载完成: {song_name} - {artist} ({quality_name})")
            
            # 如果配置了openlist地址，则添加链接信息
            if self._openlist_url:
                # 从返回结果中获取完整的文件名（包含后缀）
                data = download_result.get("data", {})
                file_path = data.get("file_path", "")
                
                # 提取文件名部分
                if file_path:
                    # 从路径中提取文件名，例如 "/app/downloads/傅如乔 - 微微.flac" -> "傅如乔 - 微微.flac"
                    filename = file_path.split("/")[-1]
                    openlist_link = f"{self._openlist_url.rstrip('/')}/{filename}"
                    response += f"\n🔗 下载链接: {openlist_link}"
                    logger.debug(f"[下载处理] 添加OpenList链接: {openlist_link}")
                else:
                    # 如果没有文件路径信息，使用原来的处理方式
                    filename = f"{song_name} - {artist}".replace("/", "_").replace("\\", "_").replace(":", "_")
                    openlist_link = f"{self._openlist_url.rstrip('/')}/{filename}"
                    response += f"\n🔗 下载链接: {openlist_link}"
                    logger.debug(f"[下载处理] 添加默认OpenList链接: {openlist_link}")
        else:
            error_msg = download_result.get('message', '未知错误')
            response += f"\n❌ 下载失败: {error_msg}"
            logger.warning(f"[下载处理] 用户 {userid} 下载失败: {error_msg}")
        
        # 发送结果
        self.post_message(
            channel=channel,
            source=source,
            title="🎵 音乐下载完成",
            text=response,
            userid=userid
        )
        logger.info(f"[下载处理] 已向用户 {userid} 发送下载结果")

    @eventmanager.register(EventType.UserMessage)
    def handle_user_message(self, event: Event):
        """
        监听用户消息事件
        """
        logger.debug(f"[消息处理] 收到用户消息事件: {event}")
        
        if not self._enabled:
            logger.debug("[消息处理] 插件未启用，忽略消息")
            return
            
        # 获取消息内容
        text = event.event_data.get("text")
        userid = event.event_data.get("userid") or event.event_data.get("user")
        channel = event.event_data.get("channel")
        
        if not text or not userid:
            logger.warning("[消息处理] 消息缺少必要信息: text或userid为空")
            return
            
        logger.info(f"[消息处理] 收到用户消息: {text} (用户: {userid})")
        
        # 现在使用专门的命令处理，不再处理普通用户消息
        logger.debug(f"[消息处理] 用户 {userid} 发送普通消息，交由系统处理")

    def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """
        测试API连接
        
        Args:
            url: API地址，如果未提供则使用当前配置的地址
            
        Returns:
            连接测试结果
        """
        logger.info("[连接测试] 开始测试API连接")
        
        try:
            # 使用提供的URL或当前配置的URL
            api_url = url or self._base_url or self.DEFAULT_BASE_URL
            logger.debug(f"[连接测试] 测试API地址: {api_url}")
            
            # 测试健康检查接口
            test_url = f"{api_url.rstrip('/')}/health"
            logger.debug(f"[连接测试] 健康检查URL: {test_url}")
            
            response = self._api_tester.session.get(test_url, timeout=10)
            logger.debug(f"[连接测试] 健康检查响应: status_code={response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"[连接测试] API连接测试成功: {api_url}")
                return {
                    "success": True,
                    "message": f"成功连接到API服务器: {api_url}",
                    "status_code": response.status_code
                }
            else:
                logger.warning(f"[连接测试] API连接测试失败: status_code={response.status_code}")
                return {
                    "success": False,
                    "message": f"连接失败，状态码: {response.status_code}",
                    "status_code": response.status_code
                }
        except Exception as e:
            logger.error(f"[连接测试] API连接测试异常: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"连接异常: {str(e)}",
                "error": str(e)
            }

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API接口列表
        
        Returns:
            API接口列表
        """
        logger.debug("[API管理] 获取插件API接口列表")
        api_list = [
            {
                "path": "/test_connection",
                "endpoint": self.test_connection,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试API连接",
                "description": "测试配置的API地址是否可以正常连接"
            }
        ]
        logger.debug(f"[API管理] API接口列表: {api_list}")
        return api_list

    def get_page(self) -> List[dict]:
        """
        获取插件详情页面配置
        
        Returns:
            页面配置列表
        """
        logger.debug("[页面管理] 生成插件详情页面配置")
        page_config = [
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
        logger.debug(f"[页面管理] 页面配置生成完成")
        return page_config

    def get_dashboard(self, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], str]]:
        """
        获取仪表板组件配置
        
        Returns:
            仪表板组件配置元组(组件配置, 数据, 样式)
        """
        logger.debug("[仪表板] 生成仪表板组件配置")
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
        logger.debug("[仪表板] 仪表板组件配置生成完成")
        return component, {}, 'row span-4'

    def get_state(self) -> bool:
        """
        获取插件状态
        
        Returns:
            bool: 插件启用状态
        """
        logger.debug(f"[状态管理] 获取插件状态: {self._enabled}")
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        注册插件命令
        
        Returns:
            List[Dict[str, Any]]: 命令列表
        """
        logger.debug("[命令管理] 注册插件命令")
        command_list = [
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
        logger.debug(f"[命令管理] 命令列表: {command_list}")
        return command_list
