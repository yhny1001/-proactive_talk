# -*- coding: utf-8 -*-
"""
主动发言管理器
负责统筹管理所有主动发言逻辑，包括情绪感知和随机触发

功能：
- 管理双路径触发机制
- LLM最终判断逻辑
- 内容生成和发送
- 全局状态协调
"""

import asyncio
import random
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from src.common.logger import get_logger
# from src.plugin_system.apis import llm_api  # TODO: 完善LLM API调用

# 导入触发控制器
from .trigger_controller import TriggerController

logger = get_logger(__name__)

class ProactiveManager:
    """主动发言管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.controller = TriggerController(config)
        
        # 配置参数
        self.use_llm_judge = config.get("llm_judge", {}).get("use_llm_final_decision", True)
        self.judge_model = config.get("llm_judge", {}).get("judge_model", "utils_small")
        self.target_users = config.get("targeting", {}).get("target_private_whitelist", [])
        self.target_groups = config.get("targeting", {}).get("target_groups", [])
        self.debug_mode = config.get("plugin", {}).get("debug_mode", False)
        
        # 错误处理配置
        error_config = config.get("error_handling", {})
        self.max_retry_attempts = error_config.get("max_retry_attempts", 3)
        self.retry_delay_seconds = error_config.get("retry_delay_seconds", 5)
        self.fallback_enabled = error_config.get("fallback_enabled", True)
        self.stop_on_consecutive_failures = error_config.get("stop_on_consecutive_failures", 10)
        self.error_cooldown_minutes = error_config.get("error_cooldown_minutes", 30)
        self.safe_mode = error_config.get("safe_mode", True)
        
        # 错误追踪状态
        self.consecutive_failures = 0
        self.last_error_time = None
        self.error_types = {}  # 错误类型统计
        self.is_in_cooldown = False
        self.total_attempts = 0
        self.total_successes = 0
        
        # 运行状态
        self.is_running = False
        self.mood_trigger_task = None
        self.random_trigger_task = None
        
        logger.info(f"[主动管理器] 初始化完成")
        logger.info(f"  • LLM判断: {'启用' if self.use_llm_judge else '禁用'}")
        logger.info(f"  • 目标私聊: {len(self.target_users)}个用户")
        logger.info(f"  • 目标群聊: {len(self.target_groups)}个群")
        logger.info(f"  • 错误处理: 重试{self.max_retry_attempts}次, 安全模式{'开启' if self.safe_mode else '关闭'}")
        logger.info(f"  • 调试模式: {'开启(快速循环)' if self.debug_mode else '关闭'}")
    
    async def start_all_triggers(self):
        """启动所有触发器"""
        if self.is_running:
            logger.warning(f"[主动管理器] 已在运行中，跳过重复启动")
            return
        
        self.is_running = True
        logger.info(f"[主动管理器] 🚀 启动所有触发器")
        
        try:
            # 启动情绪感知触发器
            if self.config.get("mood_trigger", {}).get("enabled", True):
                self.mood_trigger_task = asyncio.create_task(self._mood_trigger_loop())
                logger.info(f"[主动管理器] ✅ 情绪触发器已启动")
            
            # 启动随机触发器
            if self.config.get("random_trigger", {}).get("enabled", True):
                self.random_trigger_task = asyncio.create_task(self._random_trigger_loop())
                logger.info(f"[主动管理器] ✅ 随机触发器已启动")
            
            # 等待任务完成（除非出错否则会一直运行）
            tasks = [t for t in [self.mood_trigger_task, self.random_trigger_task] if t]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"[主动管理器] 启动触发器失败: {e}")
        finally:
            self.is_running = False
    
    async def _mood_trigger_loop(self):
        """情绪感知触发循环"""
        logger.info(f"[情绪触发] 开始监控情绪变化...")
        
        # 配置参数
        trigger_probability = self.config.get("mood_trigger", {}).get("trigger_probability", 0.15)
        check_interval = 30 if not self.debug_mode else 5
        
        try:
            while self.is_running:
                # 周期检查情绪状态
                await asyncio.sleep(check_interval)
                
                # 检查是否可以触发
                if not self.controller.can_trigger_mood():
                    continue
                
                # 检测情绪变化
                mood_change = await self._detect_mood_change()
                if not mood_change:
                    continue
                
                # 概率判断
                if random.random() > trigger_probability:
                    logger.debug(f"[情绪触发] 情绪变化但概率未命中 ({trigger_probability:.0%})")
                    continue
                
                # 尝试主动发言
                await self._attempt_proactive_speak("mood", mood_change)
                
        except asyncio.CancelledError:
            logger.info(f"[情绪触发] 任务被取消")
        except Exception as e:
            logger.error(f"[情绪触发] 循环异常: {e}")
    
    async def _random_trigger_loop(self):
        """随机触发循环"""
        logger.info(f"[随机触发] 开始随机触发循环...")
        
        # 配置参数
        min_hours = self.config.get("random_trigger", {}).get("min_interval_hours", 3.0)
        max_hours = self.config.get("random_trigger", {}).get("max_interval_hours", 8.0)
        if self.debug_mode:
            # 调试模式加速随机触发，强制缩短至分钟级
            min_hours = 0.02  # ~1.2 分钟
            max_hours = 0.05  # ~3 分钟
        
        try:
            while self.is_running:
                # 随机间隔等待
                interval_hours = random.uniform(min_hours, max_hours)
                interval_seconds = interval_hours * 3600
                
                logger.info(f"[随机触发] 等待 {interval_hours:.1f} 小时后尝试触发")
                await asyncio.sleep(interval_seconds)
                
                # 检查是否可以触发
                if not self.controller.can_trigger_random():
                    logger.debug(f"[随机触发] 频率限制，跳过本次触发")
                    continue
                
                # 尝试主动发言
                await self._attempt_proactive_speak("random", None)
                
        except asyncio.CancelledError:
            logger.info(f"[随机触发] 任务被取消")
        except Exception as e:
            logger.error(f"[随机触发] 循环异常: {e}")
    
    async def _detect_mood_change(self) -> Optional[Dict[str, Any]]:
        """检测情绪变化"""
        try:
            # TODO: 实现情绪变化检测逻辑
            # 这里应该连接到情绪管理器，检测情绪状态变化
            # 暂时返回模拟数据用于测试
            
            # 模拟情绪变化检测
            if random.random() < 0.1:  # 10%概率检测到情绪变化
                moods = ["开心", "沮丧", "兴奋", "平静", "焦虑"]
                return {
                    "mood": random.choice(moods),
                    "intensity": random.uniform(0.5, 1.0),
                    "change_type": "显著变化"
                }
            return None
            
        except Exception as e:
            logger.error(f"[情绪检测] 检测情绪变化失败: {e}")
            return None
    
    async def _attempt_proactive_speak(self, trigger_type: str, context: Optional[Dict[str, Any]]):
        """尝试主动发言 - 带错误处理版本"""
        try:
            logger.info(f"[{trigger_type}触发] 准备尝试主动发言...")
            
            # 🔍 系统健康检查
            if not self._is_system_healthy():
                logger.warning(f"[{trigger_type}触发] 系统处于不健康状态，跳过发言")
                return
            
            # 获取目标用户列表
            targets = self._get_available_targets()
            if not targets:
                logger.warning(f"[{trigger_type}触发] 没有可用的目标用户")
                return
            
            # 选择目标
            target = random.choice(targets)
            logger.info(f"[{trigger_type}触发] 选择目标: {target}")
            
            # 🔍 用户活跃度检测（带重试）
            try:
                is_active = await self._retry_with_backoff(
                    "用户活跃度检测",
                    self._is_user_currently_active,
                    target
                )
                if is_active is None:  # 重试失败，降级处理
                    logger.warning(f"[{trigger_type}触发] 活跃度检测失败，谨慎继续...")
                    is_active = False  # 假设用户不活跃，允许发言
                elif is_active:
                    logger.info(f"[{trigger_type}触发] 用户 {target} 当前活跃，避免打扰")
                    return
            except Exception as e:
                if self.safe_mode:
                    logger.error(f"[{trigger_type}触发] 安全模式：活跃度检测异常，停止发言: {e}")
                    return
                else:
                    logger.warning(f"[{trigger_type}触发] 活跃度检测异常，继续发言: {e}")
            
            # 🔍 LLM最终判断（带重试）
            if self.use_llm_judge:
                try:
                    should_speak = await self._retry_with_backoff(
                        "LLM判断",
                        self._llm_should_speak,
                        target, context, trigger_type
                    )
                    if should_speak is None:  # 重试失败，降级处理
                        should_speak = random.random() < 0.3  # 保守的随机判断
                        logger.warning(f"[{trigger_type}触发] LLM判断失败，降级到随机判断: {'允许' if should_speak else '拒绝'}")
                    
                    if not should_speak:
                        logger.info(f"[{trigger_type}触发] 判断不应发言，跳过")
                        return
                except Exception as e:
                    if self.safe_mode:
                        logger.error(f"[{trigger_type}触发] 安全模式：LLM判断异常，停止发言: {e}")
                        return
                    else:
                        logger.warning(f"[{trigger_type}触发] LLM判断异常，继续发言: {e}")
            
            # 🔍 内容生成（带重试）
            try:
                content = await self._retry_with_backoff(
                    "内容生成",
                    self._generate_content,
                    target, context, trigger_type
                )
                if not content:
                    logger.warning(f"[{trigger_type}触发] 所有内容生成尝试失败")
                    return
            except Exception as e:
                logger.error(f"[{trigger_type}触发] 内容生成严重异常: {e}")
                return
            
            # 🔍 消息发送（带重试）
            try:
                success = await self._retry_with_backoff(
                    "消息发送",
                    self._send_proactive_message,
                    target, content
                )
                
                if success:
                    # 记录触发成功
                    if trigger_type == "mood":
                        self.controller.record_mood_trigger()
                    else:
                        self.controller.record_random_trigger()
                        
                    logger.info(f"[{trigger_type}触发] ✅ 主动发言成功: {content[:30]}...")
                elif success is None:  # 重试失败
                    logger.error(f"[{trigger_type}触发] ❌ 所有发送尝试失败: {target}")
                else:
                    logger.warning(f"[{trigger_type}触发] ❌ 发送失败: {target}")
                    
            except Exception as e:
                logger.error(f"[{trigger_type}触发] 消息发送严重异常: {e}")
                
        except Exception as e:
            logger.error(f"[{trigger_type}触发] 主动发言流程严重异常: {e}")
            self._record_error(e, f"{trigger_type}触发流程")
    
    def _get_available_targets(self) -> list:
        """获取可用目标列表（按用户要求的优先级）

        逻辑：
        1) 如果“在适配器白名单里且插件相应白名单为空”，则使用适配器白名单内容（该类全部可用）
        2) 如果“插件相应白名单为空，但全局白名单不为空”，则使用全局白名单
        3) 如果“插件白名单和全局白名单均为空”，则默认不开启该类

        私聊与群聊按各自开关独立评估后合并。
        """
        final_targets: list[str] = []

        # 读取开关与插件名单
        enable_private = bool(self.config.get("targeting", {}).get("enable_private", True))
        enable_group = bool(self.config.get("targeting", {}).get("enable_group", True))
        plugin_priv = [str(x) for x in (self.config.get("targeting", {}).get("target_private_whitelist", []) or [])]
        plugin_group = [str(x) for x in (self.config.get("targeting", {}).get("target_groups", []) or [])]

        # 读取适配器白名单
        adapter_priv: list[str] = []
        adapter_group: list[str] = []
        try:
            from src.config.config import global_config
            chat_cfg = getattr(global_config, "chat", None)
            if chat_cfg:
                try:
                    if str(getattr(chat_cfg, "private_list_type", "")).lower() == "whitelist":
                        adapter_priv = [str(x) for x in (getattr(chat_cfg, "private_list", []) or [])]
                except Exception:
                    pass
                try:
                    if str(getattr(chat_cfg, "group_list_type", "")).lower() == "whitelist":
                        adapter_group = [str(x) for x in (getattr(chat_cfg, "group_list", []) or [])]
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[目标选择] 读取适配器白名单异常: {e}")

        # 私聊路径
        if enable_private:
            priv_candidates: list[str] = []
            if not plugin_priv and adapter_priv:
                # 情况1/2：插件为空，适配器非空 → 用适配器
                priv_candidates = [f"private:{uid}" for uid in adapter_priv]
                logger.info(f"[目标选择/私聊] 使用适配器白名单 {len(priv_candidates)}")
            elif plugin_priv:
                # 插件非空 → 按插件
                priv_candidates = [f"private:{uid}" for uid in plugin_priv]
                logger.info(f"[目标选择/私聊] 使用插件白名单 {len(priv_candidates)}")
            else:
                # 插件空 且 适配器空 → 不开启
                logger.info("[目标选择/私聊] 插件与适配器白名单均为空，未开启")
            final_targets.extend(priv_candidates)

        # 群聊路径
        if enable_group:
            group_candidates: list[str] = []
            if not plugin_group and adapter_group:
                group_candidates = [f"group:{gid}" for gid in adapter_group]
                logger.info(f"[目标选择/群聊] 使用适配器白名单 {len(group_candidates)}")
            elif plugin_group:
                group_candidates = [f"group:{gid}" for gid in plugin_group]
                logger.info(f"[目标选择/群聊] 使用插件白名单 {len(group_candidates)}")
            else:
                logger.info("[目标选择/群聊] 插件与适配器白名单均为空，未开启")
            final_targets.extend(group_candidates)

        return final_targets
    
    def _is_system_healthy(self) -> bool:
        """检查系统健康状态"""
        # 检查是否在冷却期
        if self.is_in_cooldown:
            if self.last_error_time:
                cooldown_end = self.last_error_time + timedelta(minutes=self.error_cooldown_minutes)
                if datetime.now() < cooldown_end:
                    remaining = (cooldown_end - datetime.now()).total_seconds() / 60
                    logger.debug(f"[系统健康] 仍在冷却期，剩余{remaining:.1f}分钟")
                    return False
                else:
                    # 冷却期结束，重置状态
                    self.is_in_cooldown = False
                    self.consecutive_failures = 0
                    logger.info(f"[系统健康] 冷却期结束，系统恢复正常")
        
        # 检查连续失败次数
        if self.consecutive_failures >= self.stop_on_consecutive_failures:
            logger.warning(f"[系统健康] 连续失败{self.consecutive_failures}次，系统暂停")
            return False
        
        # 安全模式检查
        if self.safe_mode and self.consecutive_failures > 0:
            success_rate = self.total_successes / max(self.total_attempts, 1)
            if success_rate < 0.3:  # 成功率低于30%
                logger.warning(f"[系统健康] 安全模式：成功率{success_rate:.1%}过低，暂停运行")
                return False
        
        return True
    
    def _record_error(self, error: Exception, operation: str):
        """记录错误并更新错误统计"""
        error_type = type(error).__name__
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
        self.consecutive_failures += 1
        self.last_error_time = datetime.now()
        
        logger.error(f"[错误记录] {operation}失败: {error_type} - {str(error)}")
        logger.info(f"[错误统计] 连续失败{self.consecutive_failures}次, 错误类型: {self.error_types}")
        
        # 判断是否进入冷却期
        if self.consecutive_failures >= 5:  # 连续失败5次进入冷却
            self.is_in_cooldown = True
            logger.warning(f"[错误记录] 进入{self.error_cooldown_minutes}分钟冷却期")
    
    def _record_success(self, operation: str):
        """记录成功操作"""
        self.consecutive_failures = 0  # 重置连续失败计数
        self.total_successes += 1
        
        # 如果之前在冷却期，现在可以提前结束
        if self.is_in_cooldown:
            self.is_in_cooldown = False
            logger.info(f"[成功记录] {operation}成功，冷却期提前结束")
        
        logger.debug(f"[成功记录] {operation}成功, 总成功率: {self.total_successes}/{self.total_attempts}")
    
    async def _retry_with_backoff(self, operation_name: str, operation_func, *args, **kwargs):
        """带重试和退避的操作执行"""
        last_error = None
        
        for attempt in range(1, self.max_retry_attempts + 1):
            try:
                self.total_attempts += 1
                result = await operation_func(*args, **kwargs)
                
                # 操作成功
                self._record_success(operation_name)
                logger.debug(f"[重试机制] {operation_name} 第{attempt}次尝试成功")
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"[重试机制] {operation_name} 第{attempt}次尝试失败: {e}")
                
                if attempt < self.max_retry_attempts:
                    delay = self.retry_delay_seconds * attempt  # 递增延迟
                    logger.info(f"[重试机制] {delay}秒后进行第{attempt + 1}次重试...")
                    await asyncio.sleep(delay)
                else:
                    # 所有重试都失败了
                    self._record_error(e, operation_name)
                    break
        
        # 如果启用了降级机制
        if self.fallback_enabled:
            logger.info(f"[重试机制] {operation_name} 所有重试失败，尝试降级处理")
            return None  # 调用方需要处理降级逻辑
        else:
            raise last_error
    
    async def _is_user_currently_active(self, target: str) -> bool:
        """检测用户是否当前活跃（正在聊天），避免打扰"""
        try:
            # 解析目标格式
            if ":" not in target:
                return False
            
            target_type, target_id = target.split(":", 1)
            
            # 导入必要的API
            from src.plugin_system.apis import message_api
            from src.chat.message_receive.chat_stream import get_chat_manager
            
            # 获取聊天流ID
            if target_type == "private":
                chat_id = get_chat_manager().get_stream_id("qq", target_id, is_group=False)
            elif target_type == "group":
                chat_id = get_chat_manager().get_stream_id("qq", target_id, is_group=True)
            else:
                logger.warning(f"[活跃度检测] 不支持的目标类型: {target_type}")
                return False
            
            if not chat_id:
                logger.debug(f"[活跃度检测] 未找到 {target} 的聊天流")
                return False
            
            # 检查最近的消息活动
            recent_minutes = 10  # 检查最近10分钟
            recent_messages = message_api.get_recent_messages(
                chat_id, 
                hours=recent_minutes/60,  # 转换为小时
                limit=10,
                limit_mode="latest"
            )
            
            if not recent_messages:
                logger.debug(f"[活跃度检测] {target} 最近{recent_minutes}分钟无消息，用户不活跃")
                return False
            
            # 分析消息频率和时间
            now = datetime.now()
            active_threshold = 3  # 如果最近有3条或以上消息，认为很活跃
            very_recent_threshold = 3  # 最近3分钟内有消息，认为正在聊天
            
            # 统计最近消息数量
            if len(recent_messages) >= active_threshold:
                logger.info(f"[活跃度检测] {target} 最近{recent_minutes}分钟有{len(recent_messages)}条消息，用户很活跃")
                return True
            
            # 检查最新消息的时间
            latest_message = recent_messages[0]
            latest_time = latest_message.timestamp if hasattr(latest_message, 'timestamp') else None
            
            if latest_time:
                time_diff = (now - latest_time).total_seconds() / 60  # 转换为分钟
                if time_diff <= very_recent_threshold:
                    logger.info(f"[活跃度检测] {target} {time_diff:.1f}分钟前有消息，用户可能正在聊天")
                    return True
            
            # 检查是否有bot自己的消息（说明最近有互动）
            bot_messages = [msg for msg in recent_messages if hasattr(msg, 'sender') and getattr(msg.sender, 'is_bot', False)]
            if bot_messages:
                logger.info(f"[活跃度检测] {target} 最近有bot消息，说明有互动，避免立即主动发言")
                return True
            
            logger.debug(f"[活跃度检测] {target} 用户不活跃，可以主动发言")
            return False
            
        except ImportError as e:
            logger.error(f"[活跃度检测] 无法导入必要API: {e}")
            return False  # 如果无法检测，默认认为不活跃
        except Exception as e:
            logger.error(f"[活跃度检测] 检测异常: {e}")
            return False  # 出错时默认认为不活跃，允许发言
    
    async def _get_user_persona_info(self, target: str) -> Dict[str, Any]:
        """获取用户个人信息和关系数据"""
        persona_info = {
            "user_id": None,
            "nickname": "朋友",
            "relationship": "unknown",
            "impression": "",
            "recent_topics": [],
            "chat_style": "casual",
            "available": True
        }
        
        try:
            # 解析目标格式
            if ":" not in target:
                return persona_info
                
            target_type, target_id = target.split(":", 1)
            persona_info["user_id"] = target_id
            
            # 导入person_api
            from src.plugin_system.apis import person_api, message_api
            
            if target_type == "private":
                # 获取私聊用户信息
                try:
                    user_info = person_api.get_user_info(target_id, platform="qq")
                    if user_info:
                        persona_info["nickname"] = getattr(user_info, 'nickname', '朋友') or '朋友'
                        logger.debug(f"[用户信息] 获取到用户昵称: {persona_info['nickname']}")
                except Exception as e:
                    logger.debug(f"[用户信息] 获取用户基础信息失败: {e}")
                
                # 获取关系信息
                try:
                    relationship = person_api.get_relationship_info(target_id, platform="qq")
                    if relationship:
                        persona_info["relationship"] = getattr(relationship, 'relationship_type', 'unknown')
                        persona_info["impression"] = getattr(relationship, 'impression', '')
                        logger.debug(f"[用户信息] 关系: {persona_info['relationship']}, 印象: {persona_info['impression'][:50]}...")
                except Exception as e:
                    logger.debug(f"[用户信息] 获取关系信息失败: {e}")
                    
            elif target_type == "group":
                # 群聊信息（可能需要特殊处理）
                persona_info["nickname"] = f"群{target_id}"
                persona_info["relationship"] = "group_member"
                persona_info["chat_style"] = "group"
                
            # 获取最近聊天话题
            try:
                from src.chat.message_receive.chat_stream import get_chat_manager
                
                if target_type == "private":
                    chat_id = get_chat_manager().get_stream_id("qq", target_id, is_group=False)
                elif target_type == "group":
                    chat_id = get_chat_manager().get_stream_id("qq", target_id, is_group=True)
                else:
                    chat_id = None
                    
                if chat_id:
                    recent_messages = message_api.get_recent_messages(chat_id, hours=24, limit=20)
                    if recent_messages:
                        # 提取最近的话题关键词（简单版本）
                        topics = []
                        for msg in recent_messages[-5:]:  # 看最近5条消息
                            if hasattr(msg, 'content') and msg.content:
                                content = str(msg.content)
                                if len(content) > 5 and not content.startswith('/'):  # 过滤命令
                                    topics.append(content[:20])  # 取前20字符作为话题
                        persona_info["recent_topics"] = topics
                        logger.debug(f"[用户信息] 最近话题: {topics}")
                        
            except Exception as e:
                logger.debug(f"[用户信息] 获取聊天话题失败: {e}")
            
            logger.info(f"[用户信息] {target} 信息获取完成: {persona_info['nickname']} ({persona_info['relationship']})")
            return persona_info
            
        except ImportError as e:
            logger.error(f"[用户信息] 无法导入person_api: {e}")
            return persona_info
        except Exception as e:
            logger.error(f"[用户信息] 获取用户信息异常: {e}")
            return persona_info
    
    async def _llm_should_speak(self, target: str, context: Optional[Dict], trigger_type: str) -> bool:
        """LLM判断是否应该主动发言 - 真实LLM版本"""
        try:
            # 导入LLM API
            from src.plugin_system.apis import llm_api
            
            # 获取可用模型，优先使用小模型避免资源冲突
            models = llm_api.get_available_models()
            lj = self.config.get("llm_judge", {})
            model_name = lj.get("judge_model", "utils_small")
            model = models.get(model_name) or models.get("utils_small") or models.get("utils")
            
            if not model:
                logger.warning(f"[LLM判断] 未找到可用模型，使用随机判断")
                return random.random() < 0.6  # 降级到随机判断
            
            # 构建判断提示词
            prompt = self._build_judge_prompt(target, context, trigger_type)
            
            # 调用LLM进行判断
            logger.debug(f"[LLM判断] 使用模型 {model_name} 进行判断...")
            ok, response, _, _ = await llm_api.generate_with_model(
                prompt,
                model,
                request_type=f"proactive.judge.{trigger_type}"
            )
            
            if not ok or not response:
                # 失败回退放行率(更积极)
                allow_rate = float(lj.get("failure_allow_rate", 0.5))
                logger.warning(f"[LLM判断] LLM调用失败，使用回退放行率 {allow_rate:.0%}")
                return random.random() < allow_rate
            
            # 解析LLM响应
            response_lower = response.lower().strip()
            should_speak = False
            
            if "yes" in response_lower or "是" in response_lower or "可以" in response_lower:
                should_speak = True
            elif "no" in response_lower or "否" in response_lower or "不" in response_lower:
                should_speak = False
            else:
                # 不明确时使用更积极的放行率
                if trigger_type == "mood":
                    allow_rate = float(lj.get("ambiguous_allow_rate_mood", 0.6))
                else:
                    allow_rate = float(lj.get("ambiguous_allow_rate_random", 0.5))
                # 轻度正向偏置：若出现“也许/可能/试试”等词更倾向YES
                if lj.get("positive_bias", True) and any(k in response_lower for k in ["maybe", "可能", "也许", "试试", "可以吧", "ok"]):
                    allow_rate = max(allow_rate, 0.7)
                should_speak = random.random() < allow_rate
                
                logger.debug(f"[LLM判断] 响应不明确: '{response[:30]}...'，使用放行率 {allow_rate:.0%}")
            
            logger.info(f"[LLM判断] {trigger_type}触发 -> {target} -> {'YES' if should_speak else 'NO'} (LLM: {response[:30]}...)")
            return should_speak
            
        except ImportError as e:
            logger.error(f"[LLM判断] 无法导入llm_api: {e}")
            return random.random() < 0.3  # 降级判断
        except Exception as e:
            logger.error(f"[LLM判断] 判断异常: {e}")
            return True  # 出现异常时默认允许，但记录错误
    
    def _build_judge_prompt(self, target: str, context: Optional[Dict], trigger_type: str) -> str:
        """构建LLM判断提示词 - 智能版本"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        current_hour = datetime.now().hour
        
        # 基础时间判断
        time_suitable = True
        time_note = ""
        if current_hour < 7:
            time_suitable = False
            time_note = "太早，用户可能在睡觉"
        elif current_hour > 23:
            time_suitable = False
            time_note = "太晚，用户可能在睡觉"
        elif 12 <= current_hour <= 13:
            time_note = "午饭时间，要谨慎"
        elif 18 <= current_hour <= 19:
            time_note = "晚饭时间，要谨慎"
        else:
            time_note = "时间合适"
        
        prompt = f"""你是一个智能机器人的判断系统，需要决定是否应该主动向用户发起对话。

基本信息：
- 触发类型: {trigger_type} ({'情绪变化触发' if trigger_type == 'mood' else '随机触发'})
- 目标用户: {target}
- 当前时间: {current_time} ({time_note})
- 时间是否合适: {'是' if time_suitable else '否'}
"""
        
        if context and trigger_type == "mood":
            mood_state = context.get('mood', '未知')
            intensity = context.get('intensity', 0)
            prompt += f"""
情绪信息：
- 检测到的情绪: {mood_state}
- 情绪强度: {intensity:.2f}/1.0
- 情绪触发原因: 用户情绪发生了显著变化"""
        
        # 添加判断原则
        prompt += f"""

判断原则：
1. 时间合理性: 避免在睡觉时间(23:00-7:00)打扰用户
2. 频率控制: 不要过于频繁主动发言，保持适度
3. 情绪适宜性: 如果是情绪触发，考虑情绪状态是否适合聊天
4. 自然性: 主动发言应该感觉自然，不突兀
5. 用户体验: 优先考虑不打扰用户的正常生活

特殊考虑：
- 随机触发要更加谨慎，降低频率
- 情绪触发可以稍微宽松，但要考虑情绪类型
- 深夜和早晨时间要特别谨慎
- 饭点时间要适度谨慎

请基于以上信息判断是否应该主动发起对话。
只输出 yes 或 no，不要任何解释。
"""
        
        return prompt
    
    async def _generate_content(self, target: str, context: Optional[Dict], trigger_type: str) -> Optional[str]:
        """生成主动发言内容 - 个性化版本"""
        try:
            # 获取用户信息
            user_info = await self._get_user_persona_info(target)
            
            # 使用LLM生成个性化内容
            content = await self._generate_personalized_content(user_info, context, trigger_type)
            
            if content:
                logger.info(f"[内容生成] {trigger_type}触发生成个性化内容: {content[:50]}...")
                return content
            else:
                # 降级到基于用户信息的模板内容
                content = self._generate_template_content(user_info, context, trigger_type)
                logger.info(f"[内容生成] 降级到模板内容: {content}")
                return content
                
        except Exception as e:
            logger.error(f"[内容生成] 生成异常: {e}")
            return self._generate_fallback_content()
    
    async def _generate_personalized_content(self, user_info: Dict[str, Any], context: Optional[Dict], trigger_type: str) -> Optional[str]:
        """使用LLM生成个性化内容"""
        try:
            # 导入LLM API
            from src.plugin_system.apis import llm_api
            
            # 获取内容生成模型
            models = llm_api.get_available_models()
            model_name = self.config.get("content_generation", {}).get("model", "chat")
            model = models.get(model_name) or models.get("chat") or models.get("utils")
            
            if not model:
                logger.warning(f"[内容生成] 未找到可用模型，使用模板内容")
                return None
            
            # 构建内容生成提示词
            prompt = await self._build_content_prompt(user_info, context, trigger_type)
            
            # 调用LLM生成内容
            logger.debug(f"[内容生成] 使用模型 {model_name} 生成个性化内容...")
            ok, response, _, _ = await llm_api.generate_with_model(
                prompt,
                model,
                request_type=f"proactive.content.{trigger_type}"
            )
            
            if not ok or not response:
                logger.warning(f"[内容生成] LLM生成失败")
                return None
            
            # 清理和验证生成的内容
            content = response.strip().replace("\n", " ")
            # 简短模式剪裁 & 去模板化短语
            try:
                cg_conf = self.config.get("content_generation", {})
                short_mode = bool(cg_conf.get("short_mode", True))
                target_len = int(cg_conf.get("target_length", 20))
                avoid_phrases = cg_conf.get("avoid_phrases", []) or []
                if short_mode and len(content) > max(8, target_len * 2):
                    content = content[: target_len + 10]
                for phrase in avoid_phrases:
                    if phrase and phrase in content:
                        content = content.replace(phrase, "")
                content = content.strip()
            except Exception:
                pass
            # 从配置读取长度限制
            cg_conf = self.config.get("content_generation", {})
            min_len = int(cg_conf.get("min_length", 10))
            max_len = int(cg_conf.get("max_length", 60))
            if len(content) < min_len or len(content) > max_len:
                logger.warning(f"[内容生成] 生成内容长度异常: {len(content)} (期望{min_len}-{max_len})")
                return None
            
            # 过滤不合适的内容
            if any(word in content.lower() for word in ['抱歉', 'sorry', '无法', '不能', '错误']):
                logger.warning(f"[内容生成] 生成内容包含拒绝词汇")
                return None
                
            return content
            
        except ImportError as e:
            logger.error(f"[内容生成] 无法导入llm_api: {e}")
            return None
        except Exception as e:
            logger.error(f"[内容生成] LLM生成异常: {e}")
            return None
    
    async def _build_content_prompt(self, user_info: Dict[str, Any], context: Optional[Dict], trigger_type: str) -> str:
        """构建内容生成提示词"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        current_hour = datetime.now().hour
        
        # 时间段描述
        if 5 <= current_hour < 11:
            time_period = "早上"
        elif 11 <= current_hour < 13:
            time_period = "中午"
        elif 13 <= current_hour < 18:
            time_period = "下午"
        elif 18 <= current_hour < 22:
            time_period = "晚上"
        else:
            time_period = "深夜"
        
        # 读取内容生成配置
        cg_conf = self.config.get("content_generation", {})
        tone = cg_conf.get("tone", "warm_natural")
        use_recent = bool(cg_conf.get("use_recent_context", True))
        recent_n = int(cg_conf.get("recent_context_messages", 3))
        max_snip = int(cg_conf.get("max_snippet_chars", 24))
        avoid_phrases = cg_conf.get("avoid_phrases", []) or []
        ask_prob = float(cg_conf.get("ask_follow_up_probability", 0.6))
        short_mode = bool(cg_conf.get("short_mode", True))
        target_len = int(cg_conf.get("target_length", 20))
        variety_styles = cg_conf.get("variety_styles", ["question","observation","context","emoji","teaser"]) or []
        style_weights_kv = cg_conf.get("style_weights", ["question:1.0","observation:1.0","context:1.0","emoji:0.8","teaser:0.8"]) or []

        # 解析权重
        style_weight_map = {}
        for item in style_weights_kv:
            try:
                k, v = str(item).split(":", 1)
                style_weight_map[k.strip()] = float(v)
            except Exception:
                continue

        # 随机事件式开场（仅用于 random 触发）
        re_conf = self.config.get("random_event", {})
        re_enabled = bool(re_conf.get("enabled", True))
        re_prob = float(re_conf.get("probability", 0.55))
        themes = re_conf.get("themes", ["anime","campus","daily","work","games","travel","food"]) or []
        bored_ok = bool(re_conf.get("allow_bored", True))
        bored_p = float(re_conf.get("bored_probability", 0.35))

        use_random_event = False
        chosen_random_event: Optional[str] = None
        if trigger_type == "random" and re_enabled:
            if random.random() < re_prob:
                use_random_event = True
                if bored_ok and random.random() < bored_p:
                    chosen_random_event = "bored"
                else:
                    chosen_random_event = random.choice(themes) if themes else "daily"

        # 获取最近上下文片段（尽量来自最近对话）
        context_lines = []
        if use_recent:
            try:
                from src.plugin_system.apis import message_api
                from src.chat.message_receive.chat_stream import get_chat_manager
                target = (user_info.get("user_id") or "")
                if target:
                    chat_id = get_chat_manager().get_stream_id("qq", target, is_group=(user_info.get("chat_style")=="group"))
                else:
                    chat_id = None
                if chat_id:
                    recents = message_api.get_recent_messages(chat_id, hours=24, limit=max(5, recent_n))
                    for msg in recents[-recent_n:]:
                        text = getattr(msg, 'content', None) or getattr(msg, 'raw_text', None) or ""
                        if isinstance(text, str) and text.strip():
                            snippet = text.strip().replace("\n", " ")[:max_snip]
                            if snippet and not snippet.startswith('/'):
                                context_lines.append(f"- {snippet}")
            except Exception:
                pass

        avoid_lines = [f"- {p}" for p in avoid_phrases if isinstance(p, str) and p]

        prompt = f"""你是一个智能聊天机器人，需要主动向用户发起自然的对话。

用户信息：
- 昵称: {user_info['nickname']}
- 关系: {user_info['relationship']}
- 个人印象: {user_info['impression'] or '暂无特殊印象'}
- 聊天风格: {user_info['chat_style']}

当前环境：
- 时间: {current_time} ({time_period})
- 触发原因: {trigger_type} ({'情绪变化' if trigger_type == 'mood' else '随机触发'})
"""
        
        if context and trigger_type == "mood":
            mood = context.get('mood', '未知')
            intensity = context.get('intensity', 0)
            prompt += f"- 检测到的情绪: {mood} (强度: {intensity:.2f})\n"
        
        if user_info['recent_topics']:
            prompt += f"- 最近聊过的话题: {', '.join(user_info['recent_topics'][:3])}\n"
        if context_lines:
            prompt += "- 最近几条对话片段：\n" + "\n".join(context_lines) + "\n"
        if use_random_event:
            prompt += "\n随机事件式开场设置：\n"
            if chosen_random_event == "bored":
                prompt += (
                    "- 开场类型: bored (轻松自嘲/想找你聊聊)\n"
                    "- 要求: 直接、自然、短句；不必解释原因；可以加一个合适的 emoji；避免连续标点\n"
                )
            else:
                prompt += (
                    f"- 开场类型: random_event (主题: {chosen_random_event})\\n"
                    "- 要求: 以一件很小的日常事件为切口（不杜撰具体校名/公司名/人名）；\n"
                    "        可提到‘社团里/昨晚刷番/今天路上/午休/实验课/打完一把/食堂/下课铃’等泛化表达；\n"
                    "        语气轻松自然，适度生动，但控制在一两句内；可收尾一个轻量问题承接对话。\n"
                )
        
        prompt += f"""
生成要求：
1. 内容要自然、友好，符合{user_info['relationship']}的关系定位
2. 考虑当前是{time_period}，用词要贴合时间
3. 根据用户印象调整语气和话题
4. 内容控制在10-50字之间
5. 不要提及"主动发起"、"系统"等技术词汇
6. 要感觉像是自然想起对方而发送的消息
7. 可以关联最近的话题，但不要重复
8. 语气风格: {tone}（保持轻松自然、避免官腔）
9. 避免使用以下模板化短语：
{chr(10).join(avoid_lines) if avoid_lines else '- （无）'}
10. 如果合适，结尾可以带一个轻量的问题来承接对话（概率 {ask_prob:.0%}）。
11. 输出尽量简短、精炼{ '，目标长度约' + str(target_len) + '字' if short_mode else '' }。
12. 从以下风格中随机选择其一，并遵循权重倾向：{', '.join(variety_styles)}；权重：{', '.join([f"{k}:{style_weight_map.get(k,1.0)}" for k in variety_styles])}。
   - question: 提一个轻量而具体的小问题
   - observation: 先给出一个贴近环境/日程的观察后接话
   - context: 借用最近上下文的一小段延续
   - emoji: 含一个合适的表情符号，但避免堆叠
   - teaser: 先抛出一个轻松的悬念式开头

生成风格：
- 如果关系是朋友/好友：轻松随意
- 如果关系未知：礼貌适度
- 如果是群聊：简洁有趣

请直接输出一条合适的开场消息，不要任何解释或格式标记。
"""
        
        return prompt
    
    def _generate_template_content(self, user_info: Dict[str, Any], context: Optional[Dict], trigger_type: str) -> str:
        """基于用户信息的模板内容生成（LLM降级方案）"""
        nickname = user_info['nickname']
        relationship = user_info['relationship']
        current_hour = datetime.now().hour
        
        # 根据关系选择内容风格
        if relationship in ['friend', 'close_friend']:
            if trigger_type == "mood" and context:
                templates = [
                    f"{nickname}，突然想起你了~",
                    f"嘿{nickname}，最近怎么样？",
                    f"{nickname}，在忙什么呢？"
                ]
            else:
                templates = [
                    f"{nickname}，有空聊天吗？",
                    f"想起{nickname}了，最近好吗？",
                    f"{nickname}，今天过得怎么样？"
                ]
        elif relationship == 'group_member':
            templates = [
                "大家好，来聊聊天吧~",
                "群里好安静，有人在吗？",
                "忽然想和大家聊聊"
            ]
        else:
            # 未知关系，更礼貌
            if trigger_type == "mood" and context:
                templates = [
                    f"{nickname}您好，想和您聊聊",
                    f"{nickname}，最近还好吗？",
                    f"想起{nickname}了，一切都好吧？"
                ]
            else:
                templates = [
                    f"{nickname}您好，有空聊聊吗？",
                    f"{nickname}，最近怎么样？",
                    f"想和{nickname}聊聊天"
                ]
        
        # 根据时间调整
        if 23 <= current_hour or current_hour < 7:
            # 深夜/早晨更温和
            if relationship in ['friend', 'close_friend']:
                templates = [f"{nickname}，还没睡吗？", f"{nickname}，也是夜猫子呀~"]
            else:
                templates = [f"{nickname}，不好意思这么晚打扰"]
        
        return random.choice(templates)
    
    def _generate_fallback_content(self) -> str:
        """最终降级内容"""
        fallback_contents = [
            "嗨！最近怎么样？",
            "想起你了，在做什么呢？",
            "有空聊聊天吗？",
            "忽然想和你聊聊~"
        ]
        return random.choice(fallback_contents)
    

    async def _send_proactive_message(self, target: str, content: str) -> bool:
        """发送主动消息 - 真实发送版本"""
        try:
            # 解析目标格式：private:123456 或 group:789012
            if ":" not in target:
                logger.error(f"[真实发送] 目标格式错误: {target}")
                return False
            
            target_type, target_id = target.split(":", 1)
            logger.info(f"[真实发送] 准备发送到 {target_type}:{target_id} - {content}")
            
            # 导入发送API
            from src.plugin_system.apis import send_api
            
            success = False
            if target_type == "private":
                # 私聊发送
                success = await send_api.text_to_user(
                    content,
                    target_id,
                    platform="qq",  # 默认QQ平台
                    typing=True,    # 显示输入状态
                    storage_message=True  # 存储消息记录
                )
            elif target_type == "group":
                # 群聊发送  
                success = await send_api.text_to_group(
                    content,
                    target_id,
                    platform="qq",
                    typing=True,
                    storage_message=True
                )
            else:
                logger.error(f"[真实发送] 不支持的目标类型: {target_type}")
                return False
            
            if success:
                logger.info(f"[真实发送] ✅ 成功向 {target} 发送: {content[:50]}...")
                # 记录发送成功，用于后续优化
                await self._track_send_success(target, content)
            else:
                logger.warning(f"[真实发送] ❌ 向 {target} 发送失败: {content}")
                
            return success
            
        except ImportError as e:
            logger.error(f"[真实发送] 无法导入send_api: {e}")
            return False
        except Exception as e:
            logger.error(f"[真实发送] 发送异常: {e}")
            return False
    
    async def _track_send_success(self, target: str, content: str):
        """记录发送成功，用于优化触发策略"""
        try:
            # 这里可以记录用户反馈、发送时间等信息
            # 用于后续优化触发频率和内容质量
            logger.debug(f"[发送追踪] 记录成功发送: {target} - {len(content)}字符")
            # TODO: 可以添加到数据库或文件中，用于机器学习优化
            # 记录到跟进加权缓存
            try:
                from .followup_boost_handler import ProactiveFollowupBoostHandler
                # 构造 stream_id
                stream_id = None
                if ":" in target:
                    target_type, target_id = target.split(":", 1)
                    if target_type == "private":
                        stream_id = f"qq:{target_id}:private"
                    elif target_type == "group":
                        stream_id = f"qq:{target_id}:group"
                if stream_id:
                    ProactiveFollowupBoostHandler.record_proactive_sent(stream_id)
            except Exception as _:
                pass
        except Exception as e:
            logger.warning(f"[发送追踪] 记录失败: {e}")
    
    async def stop_all_triggers(self):
        """停止所有触发器"""
        logger.info(f"[主动管理器] 停止所有触发器")
        self.is_running = False
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统运行状态报告"""
        status = {
            "running": self.is_running,
            "healthy": self._is_system_healthy(),
            "in_cooldown": self.is_in_cooldown,
            "consecutive_failures": self.consecutive_failures,
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "success_rate": self.total_successes / max(self.total_attempts, 1),
            "error_types": dict(self.error_types),
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
        }
        
        if self.is_in_cooldown and self.last_error_time:
            cooldown_end = self.last_error_time + timedelta(minutes=self.error_cooldown_minutes)
            remaining = max(0, (cooldown_end - datetime.now()).total_seconds() / 60)
            status["cooldown_remaining_minutes"] = remaining
            
        return status
    
    def reset_error_state(self):
        """重置错误状态（管理员操作）"""
        logger.info("[系统管理] 手动重置错误状态")
        self.consecutive_failures = 0
        self.is_in_cooldown = False
        self.last_error_time = None
        self.error_types.clear()
        logger.info("[系统管理] 错误状态已重置")
        
        if self.mood_trigger_task:
            self.mood_trigger_task.cancel()
        if self.random_trigger_task:
            self.random_trigger_task.cancel()
    
    def get_status(self) -> dict:
        """获取管理器状态"""
        daily_summary = self.controller.get_daily_summary()
        
        return {
            "is_running": self.is_running,
            "mood_trigger_enabled": self.config.get("mood_trigger", {}).get("enabled", True),
            "random_trigger_enabled": self.config.get("random_trigger", {}).get("enabled", True),
            "daily_summary": daily_summary,
            "targets": {
                "private_users": len(self.target_users),
                "groups": len(self.target_groups)
            }
        }
