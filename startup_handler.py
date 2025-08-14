# -*- coding: utf-8 -*-
"""
启动事件处理器
监听系统启动事件，启动主动发言管理器

功能：
- 监听ON_START事件
- 启动ProactiveManager
- 处理启动异常
"""

import asyncio
import os
import toml
from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.plugin_system.base.component_types import EventType
from src.common.logger import get_logger

# 导入管理器
from .proactive_manager import ProactiveManager

logger = get_logger(__name__)

class ProactiveStartupHandler(BaseEventHandler):
    """主动发言启动事件处理器"""
    
    event_type = EventType.ON_START
    
    def __init__(self):
        super().__init__()
        self.plugin_config = None
        self.manager = None
        self._auto_started = False  # 防重复启动标志
        logger.info(f"[启动处理器] 初始化完成")
        
        # 🚀 启动延迟自启动任务（绕过ON_START事件缺失问题）
        try:
            asyncio.create_task(self._delayed_auto_start())
            logger.info(f"[启动处理器] ✅ 自启动任务已创建")
        except Exception as e:
            logger.error(f"[启动处理器] ❌ 自启动任务创建失败: {e}")
    
    def _load_config_from_file(self) -> dict:
        """直接从config.toml文件读取配置（fallback机制）"""
        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(plugin_dir, "config.toml")
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    config = toml.load(f)
                logger.info(f"[启动处理器] ✅ 从文件直接读取配置: {config_file}")
                return config
            else:
                logger.warning(f"[启动处理器] ⚠️ 配置文件不存在: {config_file}")
                return {}
        except Exception as e:
            logger.error(f"[启动处理器] ❌ 读取配置文件失败: {e}")
            return {}
    
    async def execute(self, message=None):
        """执行启动处理逻辑"""
        try:
            logger.info(f"[启动处理器] 🎯 收到系统启动事件")
            
            # 检查配置
            if not self.plugin_config:
                logger.error(f"[启动处理器] 插件配置未设置")
                return
            
            # 检查是否启用
            if not self.plugin_config.get("plugin", {}).get("enabled", True):
                logger.info(f"[启动处理器] 插件已禁用，跳过启动")
                return
            
            # 创建管理器
            self.manager = ProactiveManager(self.plugin_config)
            
            # 异步启动管理器
            asyncio.create_task(self.manager.start_all_triggers())
            
            logger.info(f"[启动处理器] ✅ 主动发言系统启动成功")
            
        except Exception as e:
            logger.error(f"[启动处理器] 启动失败: {e}")
    
    async def _delayed_auto_start(self):
        """延迟自启动方法 - 绕过ON_START事件缺失"""
        try:
            # 延迟启动，确保系统完全就绪
            startup_delay = 10  # 10秒延迟
            logger.info(f"[启动处理器] ⏰ 延迟{startup_delay}秒后自动启动主动发言系统")
            
            await asyncio.sleep(startup_delay)
            
            # 检查是否已经启动过
            if self._auto_started:
                logger.info(f"[启动处理器] ✅ 系统已启动，跳过重复启动")
                return
            
            # 等待配置设置，如果失败则使用fallback
            retry_count = 0
            max_retries = 3  # 减少等待时间，只等待30秒
            while not self.plugin_config and retry_count < max_retries:
                logger.info(f"[启动处理器] ⏳ 等待插件配置设置... (尝试 {retry_count + 1}/{max_retries})")
                logger.debug(f"[启动处理器] 调试: plugin_config = {self.plugin_config}")
                await asyncio.sleep(10)
                retry_count += 1
            
            # 如果插件系统配置不可用，使用直接读取文件的fallback
            if not self.plugin_config:
                logger.warning(f"[启动处理器] ⚠️ 插件系统配置未设置，尝试直接读取配置文件")
                self.plugin_config = self._load_config_from_file()
            
            if not self.plugin_config:
                logger.error(f"[启动处理器] ❌ 无法获取插件配置，无法自动启动")
                logger.error(f"[启动处理器] 调试: 最终plugin_config = {self.plugin_config}")
                return
            
            # 执行启动逻辑
            logger.info(f"[启动处理器] 🚀 开始自动启动主动发言系统")
            await self._perform_startup()
            
        except Exception as e:
            logger.error(f"[启动处理器] ❌ 延迟自启动失败: {e}")
    
    async def _perform_startup(self):
        """执行实际的启动逻辑"""
        try:
            # 检查是否启用
            if not self.plugin_config.get("plugin", {}).get("enabled", True):
                logger.info(f"[启动处理器] 插件已禁用，跳过启动")
                return
            
            # 🧪 测试API访问能力
            logger.info(f"[API测试] EventHandler开始测试系统API访问能力...")
            await self._test_api_access()
            
            # 创建管理器
            self.manager = ProactiveManager(self.plugin_config)
            
            # 异步启动管理器
            asyncio.create_task(self.manager.start_all_triggers())
            
            # 标记已启动
            self._auto_started = True
            
            logger.info(f"[启动处理器] ✅ 主动发言系统自动启动成功")
            
        except Exception as e:
            logger.error(f"[启动处理器] ❌ 启动执行失败: {e}")
    
    async def _test_api_access(self):
        """测试外部插件的API访问能力"""
        try:
            logger.info(f"[API测试] 尝试导入系统API...")
            
            # 尝试导入各种API
            from src.plugin_system.apis import send_api, message_api, person_api, llm_api
            logger.info(f"[API测试] ✅ 成功导入所有核心API")
            
            # 测试LLM API
            models = llm_api.get_available_models()
            logger.info(f"[API测试] ✅ 获取到 {len(models)} 个可用LLM模型")
            
            # 测试获取白名单用户
            target_users = self.plugin_config.get("targeting", {}).get("target_private_whitelist", [])
            logger.info(f"[API测试] 配置的目标用户: {target_users}")
            
            if target_users:
                # 测试获取用户信息
                first_user = target_users[0]
                try:
                    person_id = person_api.get_person_id("qq", first_user)
                    logger.info(f"[API测试] ✅ 获取用户 {first_user} 的person_id: {person_id}")
                except Exception as e:
                    logger.warning(f"[API测试] ⚠️ 获取用户信息失败: {e}")
                
                # 测试LLM调用
                try:
                    if "utils_small" in models:
                        model = models["utils_small"]
                        ok, response, _, _ = await llm_api.generate_with_model(
                            "简单回答：你好",
                            model,
                            request_type="proactive.test"
                        )
                        if ok:
                            logger.info(f"[API测试] ✅ LLM调用成功: {response[:50]}...")
                        else:
                            logger.warning(f"[API测试] ⚠️ LLM调用失败")
                except Exception as e:
                    logger.warning(f"[API测试] ⚠️ LLM测试失败: {e}")
            
            logger.info(f"[API测试] 🎉 外部插件API访问测试完成！")
            
        except ImportError as e:
            logger.error(f"[API测试] ❌ API导入失败: {e}")
        except Exception as e:
            logger.error(f"[API测试] ❌ API测试异常: {e}")
    
    def get_info(self) -> dict:
        """获取处理器信息"""
        return {
            "name": "ProactiveStartupHandler",
            "event_type": "ON_START",
            "description": "启动主动发言系统（带自启动绕过机制）",
            "status": "auto_started" if self._auto_started else ("manager_ready" if self.manager else "waiting"),
            "auto_started": self._auto_started,
            "manager_created": self.manager is not None
        }
