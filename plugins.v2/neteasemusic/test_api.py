#!/usr/bin/env python3
"""
网易云音乐API测试脚本

用于测试API接口功能，包括：
- 健康检查
- 歌曲搜索
- 单曲信息获取
- 音乐下载
"""

import requests
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional


class NeteaseMusicAPITester:
    """网易云音乐API测试类"""
    
    def __init__(self, base_url: str = "http://localhost:5100"):
        """
        初始化测试器
        
        Args:
            base_url: API服务基础URL
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30
        
    def test_health(self) -> Dict[str, Any]:
        """测试健康检查接口"""
        print("🔍 测试健康检查接口...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            result = response.json()
            print(f"✅ 健康检查成功: {result}")
            return result
        except Exception as e:
            print(f"❌ 健康检查失败: {e}")
            return {"error": str(e)}
    
    def search_music(self, keyword: str, limit: int = 5) -> Dict[str, Any]:
        """
        搜索音乐
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量
        """
        print(f"🔍 搜索音乐: {keyword}")
        try:
            params = {
                "keywords": keyword,
                "limit": limit
            }
            response = self.session.get(f"{self.base_url}/search", params=params)
            result = response.json()
            
            if result.get("success"):
                songs = result.get("data", [])
                print(f"✅ 搜索成功，找到 {len(songs)} 首歌曲:")
                for i, song in enumerate(songs, 1):
                    # 适配实际返回的字段名
                    name = song.get('name', '')
                    artists = song.get('artists', '') or song.get('ar_name', '')
                    song_id = song.get('id', '')
                    pic_url = song.get('picUrl', '')
                    print(f"   {i}. {name} - {artists} (ID: {song_id})")
                    if pic_url:
                        print(f"      🖼️ 封面: {pic_url}")
                return result
            else:
                print(f"❌ 搜索失败: {result.get('message')}")
                return result
        except Exception as e:
            print(f"❌ 搜索异常: {e}")
            return {"error": str(e)}
    
    def interactive_search_and_download(self, search_keyword: str = None) -> Dict[str, Any]:
        """
        交互式搜索和下载流程
        
        Args:
            search_keyword: 搜索关键词，如果为None则提示用户输入
        """
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
        
        print("🎵 交互式音乐搜索与下载")
        print("=" * 60)
        
        # 1. 获取搜索关键词
        if not search_keyword:
            search_keyword = input("🔍 请输入搜索关键词: ").strip()
            if not search_keyword:
                return {"error": "搜索关键词不能为空"}
        
        # 2. 获取搜索数量
        search_limit = 10  # 默认值
        limit_input = input(f"📈 请输入返回歌曲数量 (1-100，默认10): ").strip()
        if limit_input:
            try:
                search_limit = int(limit_input)
                if search_limit < 1:
                    search_limit = 1
                    print("⚠️ 数量不能小于1，已设置为1")
                elif search_limit > 100:
                    search_limit = 100
                    print("⚠️ 数量不能大于100，已设置为100")
            except ValueError:
                print("⚠️ 输入无效，使用默认值10")
                search_limit = 10
        
        print(f"📋 将搜索 {search_limit} 首歌曲")
        
        # 3. 搜索歌曲
        print(f"\n🔍 搜索: {search_keyword}")
        search_result = self.search_music(search_keyword, limit=search_limit)
        
        if not search_result.get("success"):
            print(f"❌ 搜索失败: {search_result.get('message')}")
            return search_result
        
        songs = search_result.get("data", [])
        if not songs:
            print("❌ 未找到歌曲")
            return {"error": "未找到歌曲"}
        
        # 4. 让用户选择歌曲（支持翻页）
        print(f"\n🎵 找到 {len(songs)} 首歌曲，请选择要下载的歌曲:")
        
        # 如果歌曲数量大于5，使用翻页逻辑
        if len(songs) > 5:
            current_page = 0
            page_size = 5
            total_pages = (len(songs) + page_size - 1) // page_size
            
            while True:
                # 显示当前页的歌曲
                start_idx = current_page * page_size
                end_idx = min(start_idx + page_size, len(songs))
                
                print(f"\n📄 第 {current_page + 1}/{total_pages} 页 (显示第 {start_idx + 1}-{end_idx} 首)")
                print("-" * 60)
                
                for i in range(start_idx, end_idx):
                    song = songs[i]
                    name = song.get('name', '')
                    artists = song.get('artists', '') or song.get('ar_name', '')
                    album = song.get('album', '')
                    song_id = song.get('id', '')
                    pic_url = song.get('picUrl', '')
                    
                    print(f"  {i + 1}. {name} - {artists}")
                    print(f"     专辑: {album} | ID: {song_id}")
                    if pic_url:
                        print(f"     🖼️ 封面: {pic_url}")
                    print()
                
                # 显示翻页选项
                print("🎮 操作选项:")
                print(f"  输入歌曲序号 (1-{len(songs)}) 选择歌曲")
                if current_page > 0:
                    print("  输入 'p' 或 'prev' 查看上一页")
                if current_page < total_pages - 1:
                    print("  输入 'n' 或 'next' 查看下一页")
                print("  输入 'q' 或 'quit' 退出")
                
                user_input = input("\n请输入选择: ").strip().lower()
                
                # 处理翻页命令
                if user_input in ['p', 'prev'] and current_page > 0:
                    current_page -= 1
                    continue
                elif user_input in ['n', 'next'] and current_page < total_pages - 1:
                    current_page += 1
                    continue
                elif user_input in ['q', 'quit']:
                    print("❌ 用户取消操作")
                    return {"error": "用户取消操作"}
                
                # 处理歌曲选择
                try:
                    song_index = int(user_input) - 1
                    if 0 <= song_index < len(songs):
                        selected_song = songs[song_index]
                        break
                    else:
                        print(f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字")
                except ValueError:
                    print("❌ 无效输入，请输入数字或翻页命令")
        else:
            # 歌曲数量≤5，直接显示所有歌曲
            for i, song in enumerate(songs, 1):
                name = song.get('name', '')
                artists = song.get('artists', '') or song.get('ar_name', '')
                album = song.get('album', '')
                song_id = song.get('id', '')
                pic_url = song.get('picUrl', '')
                
                print(f"  {i}. {name} - {artists}")
                print(f"     专辑: {album} | ID: {song_id}")
                if pic_url:
                    print(f"     🖼️ 封面: {pic_url}")
                print()
            
            # 获取用户选择
            while True:
                try:
                    choice = input(f"请输入歌曲序号 (1-{len(songs)}): ").strip()
                    if not choice:
                        print("❌ 请输入有效的序号")
                        continue
                    
                    song_index = int(choice) - 1
                    if 0 <= song_index < len(songs):
                        selected_song = songs[song_index]
                        break
                    else:
                        print(f"❌ 序号超出范围，请输入 1-{len(songs)} 之间的数字")
                except ValueError:
                    print("❌ 请输入数字")
        
        song_id = str(selected_song.get('id'))
        song_name = selected_song.get('name')
        artist = selected_song.get('artists', '') or selected_song.get('ar_name', '')
        
        print(f"\n✅ 已选择: {song_name} - {artist}")
        
        # 5. 让用户选择音质
        print("\n🎵 请选择下载音质:")
        for i, quality in enumerate(quality_options, 1):
            print(f"  {i}. {quality['name']} ({quality['desc']})")
        
        # 获取音质选择
        while True:
            try:
                choice = input(f"请输入音质序号 (1-{len(quality_options)}): ").strip()
                if not choice:
                    print("❌ 请输入有效的序号")
                    continue
                
                quality_index = int(choice) - 1
                if 0 <= quality_index < len(quality_options):
                    selected_quality = quality_options[quality_index]
                    break
                else:
                    print(f"❌ 序号超出范围，请输入 1-{len(quality_options)} 之间的数字")
            except ValueError:
                print("❌ 请输入数字")
        
        quality_code = selected_quality['code']
        quality_name = selected_quality['name']
        
        print(f"\n✅ 已选择音质: {quality_name}")
        
        # 6. 下载歌曲
        print(f"\n📥 开始下载: {song_name} - {artist} ({quality_name})")
        print("请稍候...（服务器正在下载文件）")
        
        # 调用下载接口，设置返回 JSON 格式获取下载链接
        download_result = self.download_music_for_link(song_id, quality_code)
        
        if download_result.get("success"):
            print("\n✅ 下载完成!")
            return {
                "success": True,
                "selected_song": selected_song,
                "selected_quality": selected_quality,
                "download_result": download_result
            }
        else:
            print(f"\n❌ 下载失败: {download_result.get('message', '未知错误')}")
            return download_result
    
    def download_music_for_link(self, song_id: str, quality: str) -> Dict[str, Any]:
        """
        下载音乐并获取下载链接（JSON模式）
        
        Args:
            song_id: 歌曲ID
            quality: 音质等级
        """
        try:
            # 设置返回 JSON 格式以获取下载信息
            params = {
                "id": song_id,
                "quality": quality,
                "format": "json"  # 关键：设置返回 JSON 格式
            }
            
            # 发送下载请求
            response = self.session.post(f"{self.base_url}/download", data=params, timeout=120)
            
            if response.status_code != 200:
                try:
                    error_info = response.json()
                    return {"success": False, "message": error_info.get('message', '未知错误')}
                except:
                    return {"success": False, "message": f"HTTP {response.status_code}"}
            
            # 解析 JSON 响应
            result = response.json()
            
            if result.get('success'):
                data = result.get('data', {})
                
                # 显示下载信息
                print(f"\n📄 下载信息:")
                print(f"   歌曲: {data.get('name', '')}")
                print(f"   艺术家: {data.get('artist', '')}")
                print(f"   专辑: {data.get('album', '')}")
                print(f"   音质: {data.get('quality_name', '')}")
                print(f"   文件大小: {data.get('file_size_formatted', '')}")
                print(f"   文件类型: {data.get('file_type', '')}")
                
                # 显示封面信息
                pic_url = data.get('pic_url', '')
                if pic_url:
                    print(f"   🖼️ 封面: {pic_url}")
                
                # 显示文件位置
                file_path = data.get('file_path', '')
                if file_path:
                    print(f"   📁 文件位置: {file_path}")
                    # 根据 WEBDL 环境参数，这里应该会推送下载链接
                    print(f"   🔗 下载链接: 服务器已生成下载文件")
                
                return result
            else:
                return {"success": False, "message": result.get('message', '下载失败')}
                
        except Exception as e:
            return {"success": False, "message": f"下载异常: {str(e)}"}
    
    def download_music(self, song_id: str, quality: str = "exhigh", 
                      save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        下载音乐
        
        Args:
            song_id: 歌曲ID
            quality: 音质等级
            save_path: 保存路径，如果为None则保存到当前目录
        """
        quality_names = {
            "standard": "标准音质",
            "exhigh": "极高音质", 
            "lossless": "无损音质",
            "hires": "Hi-Res音质",
            "sky": "沉浸环绕声",
            "jyeffect": "高清环绕声",
            "jymaster": "超清母带"
        }
        quality_display = quality_names.get(quality, quality)
        print(f"🎵 开始下载音乐: ID={song_id}, 音质={quality_display}")
        try:
            params = {
                "id": song_id,
                "quality": quality
            }
            
            # 发送下载请求
            response = self.session.post(f"{self.base_url}/download", data=params, timeout=60)
            
            # 检查响应状态
            if response.status_code != 200:
                try:
                    error_info = response.json()
                    print(f"❌ 下载失败: {error_info.get('message', '未知错误')}")
                    return error_info
                except:
                    print(f"❌ 下载失败: HTTP {response.status_code}")
                    print(f"响应内容: {response.text[:200]}")
                    return {"error": f"HTTP {response.status_code}"}
            
            # 检查Content-Type
            content_type = response.headers.get('Content-Type', '')
            print(f"📋 Content-Type: {content_type}")
            
            # 如果返回JSON格式（WEBDL=true时推送下载链接）
            if 'application/json' in content_type:
                try:
                    download_info = response.json()
                    print(f"📄 获得下载信息（JSON格式）:")
                    if download_info.get('success'):
                        data = download_info.get('data', {})
                        print(f"   歌曲: {data.get('name', '')}")
                        print(f"   艺术家: {data.get('artist', '')}")
                        print(f"   音质: {data.get('quality_name', quality)}")
                        print(f"   文件大小: {data.get('file_size_formatted', 'unknown')}")
                        print(f"   文件路径: {data.get('file_path', '')}")
                        # 添加封面信息显示
                        pic_url = data.get('pic_url', '')
                        if pic_url:
                            print(f"   🖼️ 封面: {pic_url}")
                        return download_info
                    else:
                        print(f"❌ 下载失败: {download_info.get('message', '未知错误')}")
                        return download_info
                except Exception as e:
                    print(f"❌ 解析JSON响应失败: {e}")
                    return {"error": f"解析JSON失败: {e}"}
            
            # 如果返回文件流（WEBDL=false时直接返回文件）
            else:
                # 获取文件名
                filename = None
                if 'X-Download-Filename' in response.headers:
                    filename = response.headers['X-Download-Filename']
                elif 'Content-Disposition' in response.headers:
                    disposition = response.headers['Content-Disposition']
                    if 'filename=' in disposition:
                        filename = disposition.split('filename=')[1].strip('"')
                
                if not filename:
                    filename = f"music_{song_id}_{quality}.mp3"
                
                # 确定保存路径
                if save_path:
                    save_file = Path(save_path) / filename
                else:
                    save_file = Path(filename)
                
                # 保存文件
                save_file.parent.mkdir(parents=True, exist_ok=True)
                
                total_size = len(response.content)
                with open(save_file, 'wb') as f:
                    f.write(response.content)
                
                # 获取下载信息
                download_message = response.headers.get('X-Download-Message', '下载完成')
                
                print(f"✅ 下载成功!")
                print(f"   文件名: {filename}")
                print(f"   保存到: {save_file.absolute()}")
                print(f"   文件大小: {total_size / 1024 / 1024:.2f} MB")
                print(f"   状态: {download_message}")
                
                return {
                    "success": True,
                    "filename": filename,
                    "save_path": str(save_file.absolute()),
                    "file_size": total_size,
                    "message": download_message
                }
            
        except Exception as e:
            print(f"❌ 下载异常: {e}")
            import traceback
            print(f"详细错误: {traceback.format_exc()}")
            return {"error": str(e)}
    
    def test_complete_workflow(self, search_keyword: str = "周杰伦", 
                             quality: str = "exhigh") -> Dict[str, Any]:
        """
        测试完整工作流程：搜索 -> 获取信息 -> 下载
        
        Args:
            search_keyword: 搜索关键词
            quality: 下载音质
        """
        quality_names = {
            "standard": "标准音质",
            "exhigh": "极高音质", 
            "lossless": "无损音质",
            "hires": "Hi-Res音质",
            "sky": "沉浸环绕声",
            "jyeffect": "高清环绕声",
            "jymaster": "超清母带"
        }
        quality_display = quality_names.get(quality, quality)
        print("=" * 60)
        print("🎯 开始完整工作流程测试")
        print(f"🎵 音质设置: {quality_display}")
        print("=" * 60)
        
        # 1. 健康检查
        health_result = self.test_health()
        if "error" in health_result:
            return {"error": "健康检查失败", "details": health_result}
        
        print()
        
        # 2. 搜索音乐
        search_result = self.search_music(search_keyword, limit=3)
        if not search_result.get("success"):
            return {"error": "搜索失败", "details": search_result}
        
        songs = search_result.get("data", [])
        if not songs:
            return {"error": "未找到歌曲"}
        
        # 选择第一首歌
        if songs:
            first_song = songs[0]
            song_id = str(first_song.get("id"))
        
        print()
        
        # 3. 获取歌曲信息
        song_info = self.get_song_info(song_id, quality)
        if not song_info.get("success"):
            return {"error": "获取歌曲信息失败", "details": song_info}
        
        print()
        
        # 4. 下载音乐
        if songs:
            download_result = self.download_music(song_id, quality, "test_downloads")
        else:
            return {"error": "没有找到歌曲可供下载"}
        
        print()
        print("=" * 60)
        if download_result.get("success"):
            print("🎉 完整工作流程测试成功!")
        else:
            print("💔 工作流程测试失败!")
        print("=" * 60)
        
        return {
            "success": download_result.get("success", False),
            "search_result": search_result,
            "song_info": song_info,
            "download_result": download_result
        }


def main():
    """主函数"""
    print("🎵 网易云音乐API测试工具")
    print("=" * 60)
    
    # 创建测试器
    tester = NeteaseMusicAPITester()
    
    # 添加交互式选项
    test_options = {
        "1": "健康检查测试",
        "3": "交互式搜索与下载（支持自定义数量）",
        "5": "完整工作流程测试",
        "6": "快速测试（推荐）"
    }
    
    print("请选择测试项目:")
    for key, value in test_options.items():
        print(f"  {key}. {value}")
    
    choice = input("\n请输入选项数字 (直接回车默认选择6): ").strip()
    if not choice:
        choice = "6"
    
    print()
    
    if choice == "1":
        tester.test_health()
    
    elif choice == "3":
        # 交互式搜索与下载
        tester.interactive_search_and_download()
    
    elif choice == "5":
        keyword = input("请输入搜索关键词 (默认: 周杰伦): ").strip()
        if not keyword:
            keyword = "周杰伦"
        print("可选音质:")
        print("  standard - 标准音质")
        print("  exhigh - 极高音质")
        print("  lossless - 无损音质")
        print("  hires - Hi-Res音质")
        print("  sky - 沉浸环绕声")
        print("  jyeffect - 高清环绕声")
        print("  jymaster - 超清母带")
        quality = input("请输入音质代码 (默认: exhigh): ").strip()
        if not quality:
            quality = "exhigh"
        tester.test_complete_workflow(keyword, quality)
    
    elif choice == "6":
        # 快速测试 - 使用默认参数
        print("🚀 执行快速测试...")
        tester.test_complete_workflow()
    
    else:
        print("❌ 无效的选项")


if __name__ == "__main__":
    main()
