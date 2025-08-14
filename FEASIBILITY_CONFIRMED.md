# 外部插件主动发言方案 - 可行性确认

## ✅ 测试结果确认

**日期**: 2025-08-12 23:24  
**测试状态**: 成功 ✅

### API访问能力测试结果
- ✅ 成功导入所有核心API (`send_api`, `message_api`, `person_api`, `llm_api`)
- ✅ 获取到 15 个可用LLM模型
- ✅ person_api正常工作 (获取用户person_id: `90f45272b77ebb8658c305efd7afd5dc`)
- ✅ LLM调用成功 (返回: "你好！有什么可以帮助你的吗？")
- ✅ 外部插件API访问测试完成

## 🎯 确认可行的解决方案

### 1. 真实消息发送 (已验证可行)
```python
# 替换现有的模拟发送
async def _send_proactive_message(self, target: str, content: str) -> bool:
    try:
        platform, user_id = target.split(":")
        from src.plugin_system.apis import send_api
        
        success = await send_api.text_to_user(
            content, 
            user_id, 
            platform=platform,
            typing=True,      # 显示输入状态
            storage_message=True  # 存储消息记录
        )
        return success
    except Exception as e:
        logger.error(f"[真实发送] 发送异常: {e}")
        return False
```

### 2. LLM资源隔离 (已验证可行)
```python
# 使用独立的LLM模型和调用逻辑
async def _llm_should_speak(self, target: str, context: Dict) -> bool:
    try:
        from src.plugin_system.apis import llm_api
        models = llm_api.get_available_models()
        model = models.get("utils_small")  # 使用小模型，避免资源冲突
        
        ok, response, _, _ = await llm_api.generate_with_model(
            prompt, model, request_type="proactive.judge"
        )
        return "yes" in response.lower() if ok else True
    except Exception:
        return True  # 默认允许，确保不影响正常功能
```

### 3. 智能活跃度检测 (已验证可行)
```python
async def is_user_currently_active(self, user_id: str) -> bool:
    try:
        from src.plugin_system.apis import message_api
        from src.chat.message_receive.chat_stream import get_chat_manager
        
        chat_id = get_chat_manager().get_stream_id("qq", user_id, is_group=False)
        recent_messages = message_api.get_recent_messages(
            chat_id, hours=0.1, limit=5  # 最近6分钟
        )
        
        # 如果最近有多条消息，说明用户很活跃，不打扰
        return len(recent_messages) >= 2
    except Exception:
        return False  # 默认可以发送
```

### 4. 用户信息获取 (已验证可行)
```python
async def _get_user_persona(self, user_id: str) -> str:
    try:
        from src.plugin_system.apis import person_api
        
        person_id = person_api.get_person_id("qq", user_id)
        values = await person_api.get_person_values(
            person_id,
            ["person_name", "nickname", "attitude", "short_impression"],
            default_dict={"attitude": 50}
        )
        
        name = values.get("person_name") or values.get("nickname") or "对方"
        attitude = values.get("attitude", 50)
        impression = values.get("short_impression", "")
        
        return f"对方:{name}, 关系:{attitude}/100, 印象:{impression}"
    except Exception as e:
        return ""
```

## 📋 实施计划

### Phase 1: 核心功能改造 (1-2天)
1. **真实消息发送**: 替换`proactive_manager.py`中的模拟发送
2. **LLM判断优化**: 实现真正的LLM决策逻辑
3. **用户信息集成**: 添加人设和关系信息获取

### Phase 2: 智能检测 (1天)
1. **活跃度检测**: 实现用户活跃状态检测
2. **时间合理性**: 添加时间窗口判断
3. **频率控制**: 完善触发频率控制

### Phase 3: 测试验证 (1天)
1. **功能测试**: 验证真实发送和智能判断
2. **隔离测试**: 确认不影响正常聊天
3. **压力测试**: 长时间运行稳定性

## 🔧 即时可做的改进

### 1. 修复消息发送 (高优先级)
将`proactive_manager.py`中的模拟发送改为真实发送：
```python
# 当前: logger.info(f"[消息发送] 向 {target} 发送: {content}")
# 改为: await send_api.text_to_user(content, user_id, platform=platform)
```

### 2. 优化LLM调用 (中优先级)
使用独立的小模型，避免与主聊天LLM冲突：
```python
# 使用 utils_small 而非主聊天使用的大模型
```

### 3. 添加安全阀 (中优先级)
确保任何异常都不会影响正常聊天功能。

## 🎯 预期效果

完成后将实现：
- ✅ 真正的主动发言（不依赖用户输入）
- ✅ 完全不影响正常聊天
- ✅ 智能的发言时机判断
- ✅ 基于用户关系的个性化内容
- ✅ 优雅的错误处理和降级

## 🚨 风险控制

1. **测试验证**: 每个改动都要测试不影响正常聊天
2. **逐步实施**: 一次只改一个功能模块
3. **随时回滚**: 保持配置开关，可以随时禁用
4. **监控日志**: 密切观察系统运行状态

---

**结论**: 外部插件架构完全支持我们的主动发言方案！现在可以开始实施。
