# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Tuple, Optional

from src.common.logger import get_logger
from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.plugin_system.base.component_types import EventType, MaiMessages

logger = get_logger(__name__)


class ProactiveFollowupBoostHandler(BaseEventHandler):
    """在主动发言后的一段时间窗口内，提高该会话的回复意愿。

    实现策略：
    - 插件的主动发送会在 additional_data 中打标: {"proactive_sent_at": epoch_ms}
      或由发送成功回调写入（当前版本先在 handler 里兼容两种标记）
    - 本处理器监听 ON_MESSAGE，将标记转移/合并到消息 additional_data 中，
      并注入 `maimcore_reply_probability_gain`。
    - 如果发送端未写标记，也支持根据 stream_id 最近一次标记缓存判断。
    """

    event_type: EventType = EventType.ON_MESSAGE
    handler_name: str = "proactive_followup_boost_handler"
    handler_description: str = "主动后跟进窗口内提高回复意愿"
    intercept_message: bool = True
    weight: int = 5

    # 进程内简单缓存：按 stream_id 记录最近一次主动发送时间
    _last_proactive_sent_at: dict[str, float] = {}

    async def execute(self, message: MaiMessages) -> Tuple[bool, bool, Optional[str]]:
        try:
            if not self.plugin_config:
                return True, True, None

            conf = self.plugin_config.get("followup_boost", {})
            if not conf.get("enabled", True):
                return True, True, None

            window_seconds = int(conf.get("window_seconds", 300))
            willing_value = float(conf.get("willing_value", 0.85))

            stream_id = message.stream_id or ""
            now = time.time()

            # 来源1：消息附带额外数据（若上游传入）
            additional = message.additional_data or {}
            sent_at = None
            if isinstance(additional, dict):
                ts = additional.get("proactive_sent_at")
                if ts:
                    # 兼容秒/毫秒
                    sent_at = float(ts) / (1000.0 if ts > 1e12 else 1.0)

            # 来源2：缓存（由 _record_proactive_sent 调用）
            if not sent_at:
                sent_at = self._last_proactive_sent_at.get(stream_id)

            if not sent_at:
                return True, True, None

            if now - sent_at > window_seconds:
                return True, True, None

            # 在窗口内：提升会话意愿与概率
            gain = max(0.0, min(1.0, willing_value))  # 保护边界

            # 方式A：直接设置会话意愿（优先，影响 get_reply_probability 的初值）
            try:
                from src.chat.willing.willing_manager import get_willing_manager
                wm = get_willing_manager()
                await wm.set_willing(stream_id, gain)
            except Exception as _:
                # 忽略失败，继续尝试方式B
                pass

            # 方式B：注入 additional_config 增益（兜底）
            try:
                additional["maimcore_reply_probability_gain"] = max(
                    float(additional.get("maimcore_reply_probability_gain", 0.0)), gain
                )
                message.additional_data = additional
            except Exception:
                pass

            logger.info(f"[跟进加权] {stream_id} 窗口内加权，设定意愿≈{gain:.2f}")
            return True, True, None
        except Exception as e:
            logger.error(f"[跟进加权] 处理异常: {e}")
            return False, True, str(e)

    @classmethod
    def record_proactive_sent(cls, stream_id: str):
        """由插件发送路径调用，记录最近主动发送时间。"""
        try:
            cls._last_proactive_sent_at[stream_id] = time.time()
        except Exception:
            pass


