# -*- coding: utf-8 -*-
"""
触发频率控制器
负责管理主动发言的频率限制，防止过度打扰用户

功能：
- 每日触发次数限制
- 最小间隔时间控制
- 分类型触发计数
- 数据持久化存储
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from src.common.logger import get_logger

logger = get_logger(__name__)

class TriggerController:
    """触发频率控制器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.data_file = "plugins/proactive_talk/trigger_state.json"
        
        # 配置参数
        self.max_daily_triggers = config.get("frequency_control", {}).get("max_daily_triggers", 5)
        self.mood_max_daily = config.get("frequency_control", {}).get("mood_max_daily", 2) 
        self.random_max_daily = config.get("frequency_control", {}).get("random_max_daily", 3)
        self.min_interval_hours = config.get("frequency_control", {}).get("min_interval_hours", 2.0)
        
        # 运行时状态
        self._state = self._load_state()
        
        logger.info(f"[触发控制器] 初始化完成")
        logger.info(f"  • 每日最大: {self.max_daily_triggers}次")
        logger.info(f"  • 情绪触发: {self.mood_max_daily}次/天")
        logger.info(f"  • 随机触发: {self.random_max_daily}次/天")
        logger.info(f"  • 最小间隔: {self.min_interval_hours}小时")
    
    def _load_state(self) -> dict:
        """加载状态数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    # 检查是否是新的一天
                    today = datetime.now().strftime("%Y-%m-%d")
                    if state.get("today") != today:
                        logger.info(f"[触发控制器] 新的一天，重置计数器")
                        return self._create_new_day_state(today)
                    return state
        except Exception as e:
            logger.warning(f"[触发控制器] 加载状态失败: {e}")
        
        # 创建新状态
        today = datetime.now().strftime("%Y-%m-%d")
        return self._create_new_day_state(today)
    
    def _create_new_day_state(self, today: str) -> dict:
        """创建新一天的状态"""
        return {
            "today": today,
            "mood_triggers_today": 0,
            "random_triggers_today": 0,
            "total_triggers_today": 0,
            "last_trigger_time": None,
            "last_mood_trigger": None,
            "last_random_trigger": None,
        }
    
    def _save_state(self):
        """保存状态数据"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[触发控制器] 保存状态失败: {e}")
    
    def can_trigger_mood(self) -> bool:
        """检查是否可以进行情绪触发"""
        self._check_new_day()
        
        # 检查情绪触发每日限制
        if self._state["mood_triggers_today"] >= self.mood_max_daily:
            logger.debug(f"[触发控制器] 情绪触发已达每日上限: {self.mood_max_daily}")
            return False
        
        # 检查总触发限制
        if self._state["total_triggers_today"] >= self.max_daily_triggers:
            logger.debug(f"[触发控制器] 总触发已达每日上限: {self.max_daily_triggers}")
            return False
        
        # 检查最小间隔
        if not self._check_min_interval():
            return False
        
        return True
    
    def can_trigger_random(self) -> bool:
        """检查是否可以进行随机触发"""
        self._check_new_day()
        
        # 检查随机触发每日限制
        if self._state["random_triggers_today"] >= self.random_max_daily:
            logger.debug(f"[触发控制器] 随机触发已达每日上限: {self.random_max_daily}")
            return False
        
        # 检查总触发限制
        if self._state["total_triggers_today"] >= self.max_daily_triggers:
            logger.debug(f"[触发控制器] 总触发已达每日上限: {self.max_daily_triggers}")
            return False
        
        # 检查最小间隔
        if not self._check_min_interval():
            return False
        
        return True
    
    def _check_min_interval(self) -> bool:
        """检查最小间隔时间"""
        if not self._state["last_trigger_time"]:
            return True
        
        try:
            last_time = datetime.fromisoformat(self._state["last_trigger_time"])
            now = datetime.now()
            elapsed = (now - last_time).total_seconds() / 3600  # 转换为小时
            
            if elapsed < self.min_interval_hours:
                logger.debug(f"[触发控制器] 距离上次触发时间不足 {self.min_interval_hours}小时 (已过{elapsed:.1f}小时)")
                return False
            
            return True
        except Exception as e:
            logger.warning(f"[触发控制器] 检查间隔时间失败: {e}")
            return True
    
    def _check_new_day(self):
        """检查是否是新的一天，如果是则重置计数器"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._state["today"] != today:
            logger.info(f"[触发控制器] 检测到新的一天，重置计数器")
            self._state = self._create_new_day_state(today)
            self._save_state()
    
    def record_mood_trigger(self):
        """记录情绪触发"""
        self._check_new_day()
        now = datetime.now().isoformat()
        
        self._state["mood_triggers_today"] += 1
        self._state["total_triggers_today"] += 1
        self._state["last_trigger_time"] = now
        self._state["last_mood_trigger"] = now
        
        self._save_state()
        logger.info(f"[触发控制器] 记录情绪触发 - 今日: {self._state['mood_triggers_today']}/{self.mood_max_daily}")
    
    def record_random_trigger(self):
        """记录随机触发"""
        self._check_new_day()
        now = datetime.now().isoformat()
        
        self._state["random_triggers_today"] += 1
        self._state["total_triggers_today"] += 1
        self._state["last_trigger_time"] = now
        self._state["last_random_trigger"] = now
        
        self._save_state()
        logger.info(f"[触发控制器] 记录随机触发 - 今日: {self._state['random_triggers_today']}/{self.random_max_daily}")
    
    def get_daily_summary(self) -> dict:
        """获取每日统计摘要"""
        self._check_new_day()
        return {
            "date": self._state["today"],
            "total_triggers": self._state["total_triggers_today"],
            "mood_triggers": self._state["mood_triggers_today"],
            "random_triggers": self._state["random_triggers_today"],
            "last_trigger": self._state["last_trigger_time"],
            "limits": {
                "total": self.max_daily_triggers,
                "mood": self.mood_max_daily,
                "random": self.random_max_daily
            }
        }
    
    def get_next_possible_trigger_time(self) -> Optional[datetime]:
        """获取下次可能的触发时间"""
        if not self._state["last_trigger_time"]:
            return datetime.now()
        
        try:
            last_time = datetime.fromisoformat(self._state["last_trigger_time"])
            next_time = last_time + timedelta(hours=self.min_interval_hours)
            return next_time if next_time > datetime.now() else datetime.now()
        except:
            return datetime.now()
