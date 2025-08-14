# Proactive Talk 外部插件使用说明

本插件提供“情绪触发 + 随机触发”的主动发言能力，完全外置，支持 Docker 热更新与通过 schema 自动生成配置。

- 不干扰主聊天：独立触发链路 + 活跃度检测 + 频率控制
- LLM 最终判断：可配置更积极的放行率与正向偏置
- 真实消息发送：通过 `send_api` 向私聊/群聊发送
- 个性化内容生成：融合最近上下文、关系与印象，短句优先、风格随机
- 跟进加权：主动后短时间内提升该会话的回复意愿，便于承接对话
- 随机事件式开场：动漫/校园/日常/工作/游戏/旅行/美食，或“无聊想聊聊”模式

---

## 部署（Docker）
- 宿主机路径：`./plugins/proactive_talk/`
- 容器挂载：`./plugins:/MaiMBot/plugins`
- 禁止手动创建 `config.toml`；由插件 `config_schema` 自动生成

---

## 触发与生成流程（包含“随机无聊”）
1) 触发（其一）：
   - 情绪触发：检测情绪变化 + 概率命中 + 频控
   - 随机触发：随机间隔 + 频控
2) 活跃度检测：目标最近活跃则避免打扰
3) LLM 最终判断（llm_judge）：决定是否现在主动
4) 选题（仅随机触发时）：
   - 按 `random_event.probability` 进入“随机事件式开场”；
   - 从 `themes` 随机选主题，或按 `bored_probability` 进入“无聊想聊聊”模式；
5) LLM 内容生成：融合用户画像、最近上下文片段、时间段和随机风格（短句优先）；
6) 真实发送：`send_api.text_to_user | text_to_group`；
7) 跟进加权：在窗口内提升该会话回复意愿以承接对话。

> 说明：即便是“随机无聊”，也同样走 LLM 生成，而非固定模板，确保自然与多样性。

---

## 目标来源（白名单）
- 两个开关：
  - `targeting.enable_private` 启用私聊主动触发
  - `targeting.enable_group` 启用群聊主动触发
- 每类（私聊/群聊）按如下优先级独立决定候选：
  1) 若“插件该类白名单为空 且 适配器该类白名单(whitelist)非空”，使用适配器白名单
  2) 若“插件该类白名单非空”，使用插件白名单
  3) 否则（两者皆空），该类不启用
- 最终将两类候选合并作为可选目标
- 生产建议：以适配器白名单为准，插件白名单仅用于临时调试

---

## 关键配置（新增与常用）
- plugin
  - enabled: 是否启用（关闭则不注册事件处理器）
  - debug_mode: 调试模式（缩短随机触发间隔，仅测试）
- frequency_control
  - max_daily_triggers: 每日允许的主动发言总次数（0 表示关闭）
  - mood_max_daily: 情绪触发的每日上限
  - random_max_daily: 随机触发的每日上限
  - min_interval_hours: 两次主动发言之间的最小间隔（小时）
- mood_trigger
  - enabled: 开启情绪触发
  - trigger_probability: 情绪变化被识别后命中概率
  - mood_threshold: 触发阈值（占位，供未来细化）
- random_trigger
  - enabled: 开启随机触发
  - min_interval_hours, max_interval_hours: 随机等待的区间（小时）
- random_event（随机事件式开场）
  - enabled: 开启随机事件式开场
  - probability: 在随机触发中采用事件式开场的概率
  - themes: ["anime","campus","daily","work","games","travel","food"] 主题池
  - allow_bored: 允许“无聊想聊聊”模式
  - bored_probability: 选择“无聊”模式的概率
- llm_judge（LLM 最终判断）
  - use_llm_final_decision: 是否由 LLM 最终裁决（推荐开启）
  - judge_model: 判定模型（默认 utils_small）
  - ambiguous_allow_rate_random/mood: LLM 响应不明确时的放行率（按触发类型区分）
  - failure_allow_rate: LLM 失败/超时时的放行率
  - positive_bias: 正向偏置：对“也许/可能/试试”等语气倾向放行
- content_generation（内容生成）
  - model: 生成模型
  - min_length, max_length: 长度边界（短句也会校验）
  - tone: 语气风格（如 warm_natural）
  - use_recent_context, recent_context_messages, max_snippet_chars: 上下文融合
  - avoid_phrases: 需避免的模板化词句
  - ask_follow_up_probability: 轻量问题式收尾倾向
  - short_mode: 精简开场白模式（推荐 true）
  - target_length: 目标字数（默认 20）
  - variety_styles: 风格集合（question/observation/context/emoji/teaser）
  - style_weights: 风格权重（如 "question:1.0"）
- targeting（目标对象）
  - enable_private: 是否对私聊启用（默认 true）
  - enable_group: 是否对群聊启用（默认 false）
  - target_private_whitelist: 插件级私聊白名单；为空时遵循适配器私聊白名单(whitelist)
  - target_groups: 插件级群聊白名单；为空时遵循适配器群聊白名单(whitelist)
- followup_boost（主动后跟进加权）
  - enabled, window_seconds, willing_value
- error_handling
  - max_retry_attempts, retry_delay_seconds, fallback_enabled,
    stop_on_consecutive_failures, error_cooldown_minutes, safe_mode

---

## 群聊支持与建议
- 支持：将群号加入 `targeting.target_groups` 即可，发送走 `text_to_group`；
- 提示词会使用 `group` 风格，强调“简洁有趣、不过度打扰”；
- 建议：
  - 严控频率（适度降低 `random_max_daily`、提高 `min_interval_hours`）；
  - 适度降低 `random_event.probability`，必要时关闭 `allow_bored`；
  - 可限定主题（如仅 anime/games）减少噪音。

---

## 调试与观察
```bash
docker compose logs core --since=1h | \
  grep -E "(proactive_talk|启动处理器|情绪触发|随机触发|LLM判断|内容生成|真实发送|跟进加权)"
```

---

## 版本
- v2.0.0：LLM 判定 / 真实发送 / 活跃检测 / 个性化生成 / 跟进加权 / 随机事件式开场 / 短句风格


