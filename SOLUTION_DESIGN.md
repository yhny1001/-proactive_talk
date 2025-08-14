# 主动发言系统解决方案设计文档

## 问题分析

### 核心问题
1. **资源冲突**：主动发言的LLM调用与正常回复LLM调用产生竞争
2. **架构混乱**：Action机制与Manager后台任务机制混用
3. **假消息发送**：只有日志记录，没有真正发送消息
4. **缺乏隔离**：后台任务影响主聊天流程性能

### 设计目标
- ✅ 真正的主动发言（不依赖用户触发）
- ✅ 完全不影响正常聊天功能
- ✅ 智能的触发判断机制
- ✅ 优雅的错误处理和降级

## 解决方案架构

### 整体架构图
```
正常聊天流程：用户消息 → Planner → Action → LLM(主模型) → 回复
                ↓ (完全隔离)
主动发言流程：定时器/情绪 → 判断器 → LLM(辅助模型) → 消息发送API
```

### 核心组件设计

#### 1. 资源隔离层 (ResourceIsolator)
**职责**：确保主动发言不影响正常聊天
```python
class ResourceIsolator:
    def __init__(self):
        self.proactive_llm_semaphore = asyncio.Semaphore(1)  # 限制并发
        self.main_chat_priority = True  # 主聊天优先
        
    async def can_use_llm(self) -> bool:
        # 检查当前是否有正在进行的主聊天LLM调用
        # 如果有，延迟主动发言
        pass
```

#### 2. 活跃状态检测器 (ActivityDetector)
**职责**：检测用户当前是否在活跃聊天，避免打扰
```python
class ActivityDetector:
    async def is_user_currently_chatting(self, user_id: str) -> bool:
        # 检查最近5分钟内是否有消息往来
        # 检查用户是否在线
        # 检查是否正在输入
        pass
```

#### 3. 真实消息发送器 (RealMessageSender)
**职责**：实现真正的消息发送，而非模拟
```python
class RealMessageSender:
    async def send_proactive_message(self, target: str, content: str) -> bool:
        # 使用真正的 send_api.text_to_user
        # 处理发送失败情况
        # 记录发送状态和用户反馈
        pass
```

#### 4. 智能触发调度器 (SmartScheduler)
**职责**：更智能的触发时机控制
```python
class SmartScheduler:
    async def should_trigger_now(self, trigger_type: str) -> bool:
        # 综合考虑：时间、用户状态、历史互动、情绪状态
        # 避免在用户忙碌时打扰
        # 基于用户反馈调整策略
        pass
```

## 关键技术解决方案

### 1. LLM资源冲突解决
**问题**：主动发言LLM调用与正常回复冲突

**解决方案**：
- 使用独立的LLM模型池（如`utils_small`专用于主动发言）
- 实现调用队列和优先级机制
- 限制主动发言的并发LLM调用数量为1
- 检测主聊天LLM繁忙时自动延迟主动发言

**配置示例**：
```toml
[resource_isolation]
proactive_llm_model = "utils_small"  # 专用模型
max_concurrent_calls = 1             # 最大并发数
priority_to_main_chat = true         # 主聊天优先
defer_when_main_busy = true          # 主聊天忙时延迟
```

### 2. 消息发送真实化
**问题**：当前只是日志记录，没有真正发送

**解决方案**：
```python
# 替换现有的模拟发送
async def _send_proactive_message(self, target: str, content: str) -> bool:
    try:
        # 解析目标格式：private:123456 或 group:789012
        platform, user_id = target.split(":")
        
        # 使用真正的发送API
        from src.plugin_system.apis import send_api
        success = await send_api.text_to_user(
            content, 
            user_id, 
            platform=platform,
            typing=True,      # 显示输入状态
            storage_message=True  # 存储消息记录
        )
        
        if success:
            logger.info(f"[真实发送] ✅ 向 {target} 成功发送: {content}")
            # 记录用户反馈以优化未来触发
            await self._track_user_response(target, content)
        else:
            logger.warning(f"[真实发送] ❌ 向 {target} 发送失败")
            
        return success
        
    except Exception as e:
        logger.error(f"[真实发送] 发送异常: {e}")
        return False
```

### 3. 活跃状态智能检测
**问题**：可能在用户正在聊天时打扰

**解决方案**：
```python
async def is_user_currently_active(self, user_id: str) -> bool:
    # 1. 检查最近消息时间
    recent_messages = message_api.get_recent_messages(
        chat_id, hours=0.1, limit=5  # 最近6分钟
    )
    
    # 2. 检查消息频率
    if len(recent_messages) >= 2:
        return True  # 用户很活跃，不打扰
    
    # 3. 检查最后消息时间
    if recent_messages and recent_messages[0].timestamp > (now - 5*60):
        return True  # 5分钟内有消息，可能在聊天
        
    # 4. 检查时间合理性
    current_hour = datetime.now().hour
    if current_hour < 7 or current_hour > 23:
        return False  # 太早或太晚，不发送
        
    return False  # 可以发送
```

### 4. 错误处理和优雅降级
### 5. 随机事件式开场（Random Event + Bored 模式）

目的：即便是“纯随机无聊”，也走完整 LLM 流程，生成更自然的短句开场。

流程（随机触发路径）：
1) 触发随机 → 频控通过 → 活跃度通过
2) LLM 判断是否适合主动（`llm_judge`）
3) 选题：
   - 按 `random_event.probability` 选择“事件式开场”分支；
   - 在 `themes` 中随机选主题，或按 `bored_probability` 选择“bored”（无聊想聊聊）分支；
4) 构建内容提示词：合并用户画像、最近上下文片段、时间段、风格随机（`variety_styles` & 权重），并注入“事件式/无聊式”要求；
5) 调用 `content_generation.model` 生成短句内容（`short_mode` + `target_length` 控制长度）；
6) 发送 → `followup_boost` 在窗口内提升该会话的回复意愿。

新增/相关配置：
- `[random_event] enabled|probability|themes|allow_bored|bored_probability`
- `[content_generation] short_mode|target_length|variety_styles|style_weights|use_recent_context|recent_context_messages|max_snippet_chars|tone|avoid_phrases|ask_follow_up_probability`
- `[llm_judge] ambiguous_allow_rate_*|failure_allow_rate|positive_bias|judge_model`

提示词要点：
- 主题化但“泛化表达”，避免杜撰具体人名/校名/公司名；
- 控制在一两句内，可带一个轻量问题接话；
- 如选 bored，则更直接自然、可带一个合适 emoji，但避免堆叠。

群聊支持：
- 通过 `targeting.target_groups` 指定群；
- 内容生成自动切换 `chat_style=group`，提示词强调“简洁有趣、不过度打扰”；
- 建议下调 `random_event.probability` 与禁用 `allow_bored` 以降低噪音。

风控建议：
- 群聊严控频率（`frequency_control`）、限定时段；
- 必要时仅在指定群、或与固定主题（例如 anime/games）开启。

**问题**：主动发言出错时不能影响正常功能

**解决方案**：
```python
class GracefulDegradation:
    def __init__(self):
        self.error_count = 0
        self.max_errors = 3
        self.cooldown_time = 3600  # 1小时冷却
        
    async def handle_error(self, error: Exception):
        self.error_count += 1
        logger.error(f"[主动发言] 错误 {self.error_count}/{self.max_errors}: {error}")
        
        if self.error_count >= self.max_errors:
            logger.warning(f"[主动发言] 错误过多，进入冷却期 {self.cooldown_time}秒")
            await asyncio.sleep(self.cooldown_time)
            self.error_count = 0  # 重置计数
```

## 实施方案

### Phase 1: 基础设施改造
1. **资源隔离器实现**
   - 创建`ResourceIsolator`类
   - 配置独立的LLM模型池
   - 实现调用优先级机制

2. **真实消息发送**
   - 替换模拟发送为真实API调用
   - 实现发送状态跟踪
   - 添加错误处理

### Phase 2: 智能检测机制
1. **活跃状态检测**
   - 实现用户活跃度检测
   - 添加时间合理性判断
   - 集成到触发判断流程

2. **优雅降级机制**
   - 实现错误计数和冷却
   - 添加系统健康检查
   - 确保主功能不受影响

### Phase 3: 测试和优化
1. **隔离测试**
   - 测试主动发言不影响正常聊天
   - 验证LLM资源隔离效果
   - 确认消息真实发送

2. **压力测试**
   - 模拟高频聊天场景
   - 测试并发LLM调用
   - 验证系统稳定性

## 风险控制

### 风险识别
1. **LLM API费用风险**：主动发言可能增加API调用成本
2. **用户打扰风险**：不合适的主动发言可能惹恼用户
3. **系统性能风险**：后台任务可能影响响应速度
4. **消息风暴风险**：逻辑错误可能导致大量消息发送

### 风险缓解措施
1. **费用控制**：
   - 严格的每日触发次数限制
   - 使用较小的LLM模型
   - 实时费用监控

2. **用户体验保护**：
   - 智能活跃度检测
   - 用户反馈收集和学习
   - 一键禁用功能

3. **性能保护**：
   - 资源隔离和限流
   - 异步执行和队列管理
   - 系统健康监控

4. **安全阀机制**：
   - 错误次数限制和自动冷却
   - 异常情况自动禁用
   - 管理员手动干预接口

## 测试验证方法

### 功能测试
1. **基础功能**：
   ```bash
   # 启用主动发言
   # 正常聊天5分钟，确认不受影响
   # 等待主动发言触发
   # 验证消息真实发送
   ```

2. **资源隔离**：
   ```bash
   # 模拟高频聊天
   # 同时触发主动发言
   # 验证正常聊天响应时间不受影响
   ```

### 压力测试
1. **并发测试**：多用户同时聊天+主动发言
2. **长期测试**：24小时运行稳定性测试
3. **异常测试**：模拟LLM API故障场景

### 监控指标
- 正常聊天响应时间
- 主动发言成功率
- LLM API调用分布
- 用户活跃度检测准确率
- 系统资源使用情况

## 实施时间表

### Week 1: 基础设施
- Day 1-2: ResourceIsolator实现
- Day 3-4: 真实消息发送改造
- Day 5: 基础测试

### Week 2: 智能机制
- Day 1-2: ActivityDetector实现  
- Day 3-4: SmartScheduler集成
- Day 5: 功能测试

### Week 3: 测试优化
- Day 1-2: 压力测试
- Day 3-4: 性能优化
- Day 5: 最终验证

## 成功标准

1. **功能完整性**：✅ 真正的主动发言功能
2. **隔离性**：✅ 正常聊天完全不受影响
3. **智能性**：✅ 合适的时机和内容
4. **稳定性**：✅ 7x24小时稳定运行
5. **可控性**：✅ 随时可以安全禁用

---

**下一步**：请review此方案，如果认可，我们按此方案逐步实施。

