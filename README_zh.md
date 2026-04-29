# agentconfig 🔧

**用自然语言配置 AI 智能体 —— 业务用户与 AI 智能体之间缺失的那一层。**

不再需要手写复杂的 prompt 工程。用普通语言描述你想要的智能体行为，agentconfig 自动生成结构化配置、约束规则和护栏策略。

[![Python](https://img.shields.io/badge/Python-3.9+-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-47%20passing-brightgreen)](tests/)

[English](./README.md) | **中文**

---

## 问题背景

配置 AI 智能体很痛苦。你需要：

- 手工调试提示词直到得到稳定输出
- 用硬编码字符串拼接约束条件
- 在代码各处分散维护护栏逻辑
- 每次业务需求变化都要重写配置

**agentconfig 让配置智能体像写需求文档一样简单。** 三层架构——语义层、运行时层、UI层——将业务意图自动转化为可执行的智能体配置。

---

## 功能特性

- 🗣️ **自然语言配置** — 用中文/英文描述智能体行为，自动生成结构化配置
- 🛡️ **约束与护栏** — 内置关键词过滤、主题限制、输出格式验证
- 🔄 **LiteLLM 兼容** — 支持 `provider/model` 格式，一行切换100+种 LLM
- 🎛️ **Web UI** — 内置 Flask 管理界面，可视化编辑配置
- 📦 **版本控制** — 追踪配置变更，支持 diff 对比
- 🔌 **框架适配器** — 支持 LangChain、CrewAI、AutoGen 直接集成

---

## 安装

```bash
pip install agentconfig
```

---

## 快速上手

```python
from agentconfig import ConfigGenerator, AgentConfig

# 用自然语言描述你的智能体
gen = ConfigGenerator(llm="openai/gpt-4o")  # 支持 LiteLLM 格式

config = gen.generate("""
    创建一个客服智能体：
    - 只回答产品相关问题
    - 不得透露竞争对手信息
    - 回答保持友好专业
    - 遇到投诉自动升级到人工
""")

# 直接使用生成的配置
print(config.system_prompt)       # 自动生成的系统提示词
print(config.constraints)         # 提取的约束规则列表
print(config.guardrails)          # 护栏策略

# 应用到智能体
agent = MyAgent(config=config)
response = agent.run("你们的退款政策是什么？")
```

---

## 三层架构

### 语义层（Semantic Layer）

将自然语言意图转化为结构化配置：

```python
from agentconfig.semantic import IntentParser

parser = IntentParser()
intent = parser.parse("帮助用户排查技术问题，禁止分享账户密码")

print(intent.role)          # "技术支持"
print(intent.restrictions)  # ["不分享密码", "不访问用户账户"]
print(intent.tone)          # "专业耐心"
```

### 运行时层（Runtime Layer）

在实际执行时验证和过滤智能体行为：

```python
from agentconfig.runtime import RuntimeGuard

guard = RuntimeGuard(config)

# 输出检查
result = await guard.check_output(agent_response)
if result.violated:
    print(f"护栏触发: {result.rule} — {result.reason}")

# 工具调用过滤
allowed = guard.filter_tools(available_tools)
```

### LLM 语义约束

将简单关键词过滤升级为语义级别验证：

```python
from agentconfig import SemanticConstraint

constraint = SemanticConstraint(
    rule="不得向用户推荐竞争对手产品",
    judge_model="gpt-4o-mini",
    threshold=0.85
)

result = constraint.check("你可以试试 XX 竞品，他们功能更全面")
# → ConstraintResult(violated=True, reason="提及了竞争对手品牌")
```

---

## LiteLLM 格式支持

```python
# 支持任意 provider/model 格式
config = AgentConfig(model="openai/gpt-4o")
config = AgentConfig(model="anthropic/claude-3-5-sonnet")
config = AgentConfig(model="ollama/qwen2.5:7b")    # 本地模型
config = AgentConfig(model="azure/gpt-4o-deploy")   # Azure
config = AgentConfig(model="gpt-4o")               # 向后兼容（无前缀）
```

---

## 框架集成

### LangChain

```python
from agentconfig.adapters.langchain import to_langchain_config
from langchain.agents import AgentExecutor

lc_config = to_langchain_config(config)
executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=tools,
    **lc_config
)
```

### CrewAI

```python
from agentconfig.adapters.crewai import to_crew_agent

crew_agent = to_crew_agent(config, tools=[web_search, calculator])
```

---

## 配置版本控制

```python
config_v1 = gen.generate("客服机器人，语气友好")
config_v2 = gen.generate("客服机器人，语气友好，自动分类工单")

diff = config_v1.diff(config_v2)
print(diff.added_constraints)    # 新增约束
print(diff.changed_prompts)      # 变更的提示词部分
```

---

## Web UI

```bash
python -m agentconfig.ui
# 访问 http://localhost:5000 进行可视化配置管理
```

---

## 典型使用场景

| 场景 | 配置关键词 | 应用效果 |
|------|-----------|---------|
| 客服机器人 | 合规约束、升级策略 | 自动过滤违规输出 |
| 销售智能体 | 竞品屏蔽、话术规范 | 保持品牌一致性 |
| 代码审查 | 安全策略、格式规范 | 符合企业安全标准 |
| 内容审核 | 违规词库、语义护栏 | 多层内容过滤 |

---

## 对比同类方案

| 功能 | agentconfig | 手写 Prompt | LangChain | Guardrails AI |
|------|------------|------------|-----------|---------------|
| 自然语言配置 | ✅ | ❌ | ❌ | ❌ |
| 语义级约束 | ✅ | ❌ | ❌ | ✅ |
| 多框架适配 | ✅ | ❌ | N/A | ⚠️ |
| 可视化 UI | ✅ | ❌ | ❌ | ❌ |
| 版本 diff | ✅ | ❌ | ❌ | ❌ |
| 零依赖核心 | ✅ | ✅ | ❌ | ❌ |

---

## 路线图

- [x] CLI 工具（serve/create/validate/list-templates/export）
- [x] 研究型智能体模板（research-agent，参考 AI-Scientist 模式）
- [x] LangChain/LangGraph/OpenAI 格式导出
- [x] MCP 工具定义格式导出
- [ ] A2A（Agent2Agent）Card 导出
- [ ] 配置模板市场（社区共享）
- [ ] 自动重要性评分（LLM Judge）

---

## 示例

```
examples/
  01_quickstart.py            # 5分钟上手
  02_customer_service.py      # 客服机器人完整配置
  03_langchain_integration.py # LangChain 集成
  04_semantic_constraints.py  # 语义级约束演示
  05_config_versioning.py     # 版本控制与 diff
```

---

## 许可证

MIT © cdzzy
