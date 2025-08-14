# -*- coding: utf-8 -*-
"""
主动问候Action组件 - 向后兼容版本
传统的被动触发式主动发言组件

注意：此组件已不推荐使用，建议使用新的主动发言系统
仅为向后兼容而保留
"""

from src.plugin_system import BaseAction, ActionActivationType
from src.common.logger import get_logger

logger = get_logger(__name__)

class ProactiveGreetAction(BaseAction):
    """主动问候Action - 传统版本"""
    
    # Action基本信息
    action_name = "proactive_greet"
    description = "传统主动问候组件（不推荐使用）"
    
    # 激活配置 - 默认禁用
    activation_type = ActionActivationType.NEVER  # 默认禁用
    random_activation_probability = 0.001  # 极低概率
    llm_judge_prompt = ""
    
    def __init__(self, plugin_config):
        super().__init__(plugin_config)
        
        # 检查是否启用传统Action
        self.enabled = plugin_config.get("action", {}).get("enable_action_proactive_greet", False)
        
        if self.enabled:
            # 如果启用了传统Action，使用RANDOM模式
            self.activation_type = ActionActivationType.RANDOM
            self.random_activation_probability = plugin_config.get("action", {}).get("base_trigger_probability", 0.001)
            logger.warning(f"[传统Action] 已启用传统主动问候组件，概率: {self.random_activation_probability}")
            logger.warning(f"[传统Action] ⚠️  建议关闭此组件，使用新的主动发言系统")
        else:
            logger.info(f"[传统Action] 传统主动问候组件已禁用")
    
    async def can_execute(self, message):
        """检查是否可以执行"""
        if not self.enabled:
            return False
        
        # 只在私聊中触发
        if message.message_type != "private":
            return False
        
        # 检查用户白名单
        target_users = self.plugin_config.get("targeting", {}).get("target_private_whitelist", [])
        if str(message.sender.user_id) not in target_users:
            return False
        
        return await super().can_execute(message)
    
    async def execute(self, message):
        """执行主动问候"""
        try:
            logger.info(f"[传统Action] 触发主动问候 - 用户: {message.sender.user_id}")
            
            # 测试API访问能力
            logger.info(f"[API测试] 尝试通过BaseAction访问系统API...")
            
            # 检查是否能访问send_api
            try:
                # 通过父类尝试访问send_api
                # BaseAction已经导入了send_api，我们应该能够访问
                from src.plugin_system.apis import send_api, message_api
                logger.info(f"[API测试] ✅ 成功导入send_api和message_api")
                
                # 测试获取最近消息
                recent_messages = message_api.get_recent_messages(self.chat_id, hours=1, limit=3)
                logger.info(f"[API测试] ✅ 获取到 {len(recent_messages)} 条最近消息")
                
                # 简单的问候内容
                greetings = [
                    "嗨！最近怎么样？",
                    "想起你了，在做什么呢？", 
                    "今天过得开心吗？",
                    "忽然想聊聊天~",
                    "你好呀！有什么新鲜事吗？"
                ]
                
                import random
                greeting = random.choice(greetings)
                
                # 尝试真实发送消息
                success = await send_api.text_to_user(
                    greeting, 
                    str(self.user_id),
                    platform=self.platform,
                    typing=True,
                    storage_message=True
                )
                
                if success:
                    logger.info(f"[API测试] ✅ 真实发送成功: {greeting}")
                else:
                    logger.warning(f"[API测试] ❌ 真实发送失败: {greeting}")
                
                return greeting
                
            except Exception as api_e:
                logger.error(f"[API测试] ❌ API调用失败: {api_e}")
                # 降级到传统返回模式
                import random
                greeting = random.choice([
                    "嗨！最近怎么样？",
                    "想起你了，在做什么呢？"
                ])
                logger.info(f"[传统Action] 降级发送问候: {greeting}")
                return greeting
            
        except Exception as e:
            logger.error(f"[传统Action] 执行主动问候失败: {e}")
            return None
    
    def get_info(self) -> dict:
        """获取Action信息"""
        return {
            "name": self.action_name,
            "description": self.description,
            "activation_type": self.activation_type.value if hasattr(self.activation_type, 'value') else str(self.activation_type),
            "probability": self.random_activation_probability,
            "enabled": self.enabled,
            "deprecated": True,
            "recommendation": "请使用新的主动发言系统替代此组件"
        }
