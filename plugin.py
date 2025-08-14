# -*- coding: utf-8 -*-
"""
主动发言插件 - 外部版本
实现低频率、高质量的机器人主动发言功能

创建时间: 2025-08-12
版本: v2.0.0
作者: AI Assistant
许可证: MIT License
"""

# ⚡ 优先应用系统热修复 - 确保插件能正常加载
try:
    from .system_hotfix import apply_all_hotfixes
    apply_all_hotfixes()
    print("✅ [主动发言插件] 系统热修复已应用")
except Exception as e:
    print(f"⚠️ [主动发言插件] 热修复应用失败: {e}")

import os
import asyncio
from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.base.component_types import ComponentInfo
from src.common.logger import get_logger

# 导入组件
from .proactive_greet_action import ProactiveGreetAction
from .startup_handler import ProactiveStartupHandler
from .followup_boost_handler import ProactiveFollowupBoostHandler

logger = get_logger(__name__)

@register_plugin
class ProactiveTalkPlugin(BasePlugin):
    """主动发言插件主类"""
    
    # 插件基本信息 - 必需属性
    plugin_name: str = "proactive_talk"
    enable_plugin: bool = True
    dependencies: list[str] = []
    python_dependencies: list[str] = []
    config_file_name: str = "config.toml"
    
    # 元数据
    author = "AI Assistant"
    description = "智能主动发言系统 - 低频率高质量的机器人主动互动"
    version = "2.0.0"
    plugin_type = "interactive"
    
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="启用主动发言插件（关闭则不注册事件处理器）"),
            "debug_mode": ConfigField(type=bool, default=False, description="调试模式：随机触发缩短为分钟级，仅用于测试"),
        },
        
        "frequency_control": {
            "max_daily_triggers": ConfigField(type=int, default=5, description="每日允许的主动发言总次数（情绪+随机合计），0 表示关闭"),
            "mood_max_daily": ConfigField(type=int, default=2, description="情绪触发的每日上限"),
            "random_max_daily": ConfigField(type=int, default=3, description="随机触发的每日上限"),
            "min_interval_hours": ConfigField(type=float, default=2.0, description="两次主动发言之间的最小间隔（小时）"),
        },
        
        "mood_trigger": {
            "enabled": ConfigField(type=bool, default=True, description="开启情绪触发：在检测到情绪明显变化时尝试主动"),
            "trigger_probability": ConfigField(type=float, default=0.15, description="命中概率：情绪变化被识别后，按该概率决定是否尝试主动"),
            "mood_threshold": ConfigField(type=str, default="显著变化", description="触发阈值：显著变化/强烈变化等（占位，供未来细化）"),
        },
        
        "random_trigger": {
            "enabled": ConfigField(type=bool, default=True, description="开启随机触发：按随机等待间隔尝试主动"),
            "min_interval_hours": ConfigField(type=float, default=3.0, description="随机等待的最小间隔（小时）"),
            "max_interval_hours": ConfigField(type=float, default=8.0, description="随机等待的最大间隔（小时）"),
        },

        "random_event": {
            "enabled": ConfigField(type=bool, default=True, description="随机事件式开场（与人设匹配的日常/番剧/校园/工作等）"),
            "probability": ConfigField(type=float, default=0.55, description="在随机触发路径中采用随机事件式开场的概率"),
            "themes": ConfigField(type=list, default=["anime","campus","daily","work","games","travel","food"], description="随机事件主题池"),
            "allow_bored": ConfigField(type=bool, default=True, description="允许以“有点无聊，想找你聊聊”的开场"),
            "bored_probability": ConfigField(type=float, default=0.35, description="无聊式开场出现概率"),
        },
        
        "llm_judge": {
            "use_llm_final_decision": ConfigField(type=bool, default=True, description="由 LLM 最终裁决是否现在说话（开启更自然）"),
            "judge_model": ConfigField(type=str, default="utils_small", description="判定模型（建议使用轻量模型以降低成本）"),
            # 更积极的放行控制参数
            "ambiguous_allow_rate_random": ConfigField(type=float, default=0.5, description="LLM 回复不明确时（随机触发）的放行概率"),
            "ambiguous_allow_rate_mood": ConfigField(type=float, default=0.6, description="LLM 回复不明确时（情绪触发）的放行概率"),
            "failure_allow_rate": ConfigField(type=float, default=0.5, description="LLM 失败或超时时的放行概率"),
            "positive_bias": ConfigField(type=bool, default=True, description="正向偏置：出现“也许/可能/试试”等语气时更倾向放行"),
        },
        
        "content_generation": {
            "model": ConfigField(type=str, default="chat", description="内容生成模型（主输出模型）"),
            "min_length": ConfigField(type=int, default=10, description="生成后长度校验的最小字数"),
            "max_length": ConfigField(type=int, default=60, description="生成后长度校验的最大字数"),
            "tone": ConfigField(type=str, default="warm_natural", description="语气风格：warm_natural/humorous_light/gentle_care"),
            "use_recent_context": ConfigField(type=bool, default=True, description="是否融合最近上下文片段以避免生硬开场"),
            "recent_context_messages": ConfigField(type=int, default=3, description="融合的最近消息条数"),
            "max_snippet_chars": ConfigField(type=int, default=24, description="每条上下文片段的最大截断长度（字符数）"),
            "avoid_phrases": ConfigField(type=list, default=["在忙什么呢？","有空聊聊吗？","最近怎么样？","聊聊天吧"], description="需要避免的模板化短语列表"),
            "ask_follow_up_probability": ConfigField(type=float, default=0.6, description="结尾带轻量问题的倾向（0-1）"),
            "short_mode": ConfigField(type=bool, default=True, description="短句模式：更精炼的开场（建议开启）"),
            "target_length": ConfigField(type=int, default=20, description="短句目标字数"),
            "variety_styles": ConfigField(type=list, default=["question","observation","context","emoji","teaser"], description="开场风格集合：提问/观察/延续/表情/悬念"),
            "style_weights": ConfigField(type=list, default=["question:1.0","observation:1.0","context:1.0","emoji:0.8","teaser:0.8"], description="风格权重，格式 'style:weight'"),
        },
        
        "targeting": {
            "enable_private": ConfigField(type=bool, default=True, description="是否对私聊启用主动发言（推荐开启）"),
            "enable_group": ConfigField(type=bool, default=False, description="是否对群聊启用主动发言（谨慎开启）"),
            "target_private_whitelist": ConfigField(type=list, default=[], description="插件级私聊白名单；为空时遵循适配器私聊白名单(whitelist)"),
            "target_groups": ConfigField(type=list, default=[], description="插件级群聊白名单；为空时遵循适配器群聊白名单(whitelist)"),
        },

        "followup_boost": {
            "enabled": ConfigField(type=bool, default=True, description="主动消息后临时提升该会话回复意愿"),
            "window_seconds": ConfigField(type=int, default=300, description="主动后生效窗口(秒)"),
            "willing_value": ConfigField(type=float, default=0.85, description="窗口内设置的会话意愿值[0-1]"),
        },
        
        "error_handling": {
            "max_retry_attempts": ConfigField(type=int, default=3, description="API调用最大重试次数"),
            "retry_delay_seconds": ConfigField(type=int, default=5, description="重试间隔秒数"),
            "fallback_enabled": ConfigField(type=bool, default=True, description="启用降级机制"),
            "stop_on_consecutive_failures": ConfigField(type=int, default=10, description="连续失败N次后停止系统"),
            "error_cooldown_minutes": ConfigField(type=int, default=30, description="错误后冷却时间（分钟）"),
            "safe_mode": ConfigField(type=bool, default=True, description="安全模式：确保错误不影响正常聊天"),
        },
        
        # 保留原有Action的配置兼容性
        "action": {
            "enable_action_proactive_greet": ConfigField(type=bool, default=False, description="启用传统Action组件(建议关闭)"),
            "base_trigger_probability": ConfigField(type=float, default=0.001, description="传统Action基础触发概率"),
        }
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proactive_manager = None
        logger.info(f"[{self.plugin_name}] 主动发言插件初始化")
    
    def register_plugin(self) -> bool:
        """注册插件和组件"""
        try:
            # 基础注册
            ok = super().register_plugin()
            if not ok:
                logger.error(f"[{self.plugin_name}] 基础插件注册失败")
                return False
            
            # 检查是否启用
            if not self.get_config("plugin.enabled", True):
                logger.info(f"[{self.plugin_name}] 插件已禁用")
                return True
                
            # 注册传统Action组件（向后兼容）
            if self.get_config("action.enable_action_proactive_greet", False):
                logger.info(f"[{self.plugin_name}] 传统Action组件已启用")
            
            # 启动事件处理器会通过get_plugin_components自动注册
            logger.info(f"[{self.plugin_name}] 启动事件处理器已配置")
            
            logger.info(f"[{self.plugin_name}] ✅ 插件注册成功")
            logger.info(f"[{self.plugin_name}] 📊 配置摘要:")
            logger.info(f"  • 每日最大触发: {self.get_config('frequency_control.max_daily_triggers', 5)}次")
            logger.info(f"  • 情绪触发: {'启用' if self.get_config('mood_trigger.enabled', True) else '禁用'}")
            logger.info(f"  • 随机触发: {'启用' if self.get_config('random_trigger.enabled', True) else '禁用'}")
            logger.info(f"  • LLM判断: {'启用' if self.get_config('llm_judge.use_llm_final_decision', True) else '禁用'}")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.plugin_name}] 插件注册失败: {e}")
            return False
    
    def get_plugin_info(self) -> dict:
        """获取插件信息"""
        return {
            "name": self.plugin_name,
            "author": self.author,
            "description": self.description,
            "version": self.version,
            "type": self.plugin_type,
            "status": "active" if self.get_config("plugin.enabled", True) else "disabled"
        }
    
    def get_plugin_components(self):
        """获取插件组件列表"""
        from src.plugin_system.base.component_types import ActionInfo, EventHandlerInfo, EventType, ComponentType
        
        components = []
        
        # 添加传统Action组件（如果启用）
        if self.get_config("action.enable_action_proactive_greet", False):
            action_info = ActionInfo(
                component_type=ComponentType.ACTION,
                name="proactive_greet_action",
                description="主动问候动作组件"
            )
            components.append((action_info, ProactiveGreetAction))
        
        # 添加启动事件处理器（仅在插件启用时）
        if self.get_config("plugin.enabled", True):
            event_handler_info = EventHandlerInfo(
                component_type=ComponentType.EVENT_HANDLER,
                name="proactive_startup_handler",
                description="主动发言系统启动处理器",
                event_type=EventType.ON_START
            )
            components.append((event_handler_info, ProactiveStartupHandler))

            # 注册跟进加权处理器（ON_MESSAGE）
            if self.get_config("followup_boost.enabled", True):
                boost_handler_info = EventHandlerInfo(
                    component_type=ComponentType.EVENT_HANDLER,
                    name="proactive_followup_boost_handler",
                    description="主动后在窗口内临时提升该会话回复意愿",
                    event_type=EventType.ON_MESSAGE,
                    weight=5,
                )
                components.append((boost_handler_info, ProactiveFollowupBoostHandler))
        
        return components