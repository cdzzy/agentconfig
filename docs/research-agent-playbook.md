# agentconfig 研究型 Agent 配置手册

> 对齐今日 Trending 项目中“低代码多 Agent 编排”“技能化能力沉淀”“可复用任务模板”三类最佳实践。

## 适用场景

- 需要把研究任务交给业务同学而不是工程师
- 需要把同一套研究流程导出到不同框架
- 需要在自然语言配置里显式声明事实核查、引用与终止条件

## 推荐配置骨架

建议一个 research-agent 至少包含以下 6 个部分：

1. **目标**：要解决什么问题
2. **输入范围**：允许访问哪些资料或上下文
3. **执行步骤**：检索、比对、归纳、输出
4. **事实约束**：必须引用来源，标注不确定性
5. **交付格式**：摘要、要点、引用列表、后续行动
6. **停止条件**：证据不足时停止并返回缺口

## 推荐自然语言配置模板

```text
Create a research agent for competitive analysis.
The agent should:
- gather signals from multiple sources
- separate facts from assumptions
- cite every important claim
- highlight conflicts between sources
- produce an executive summary and action items
- stop when evidence is insufficient instead of guessing
```

## 推荐工作流

### 1. 创建模板

```bash
agentconfig create --template research-agent
```

### 2. 校验配置

```bash
agentconfig validate path/to/research-agent.yaml
```

### 3. 导出到运行框架

```bash
agentconfig export path/to/research-agent.yaml --format langgraph
agentconfig export path/to/research-agent.yaml --format langchain
agentconfig export path/to/research-agent.yaml --format openai
```

## 设计建议

### 加上“证据门槛”

参考今日 Trending 项目中的研究 Agent 做法，建议在配置中加入：

- 最少引用数
- 冲突来源提示
- 缺证据即停止
- 输出中区分“事实 / 推断 / 待验证”

### 加上“角色切分”

即使最终只落成一个 agent，也建议在配置层拆出这些职责：

- planner：拆解研究问题
- collector：采集资料
- critic：检查冲突与遗漏
- writer：生成最终报告

这样后续更容易导出成多 Agent 执行图。

### 加上“可审计输出”

建议输出中固定保留：

- 来源列表
- 关键结论
- 不确定项
- 建议下一步

## 最小发布清单

发布一个可复用 research-agent 模板时，建议仓库至少同时包含：

- 模板说明
- 一份真实输入示例
- 一份导出结果示例
- 一份校验失败示例

## 今日可继续补强的方向

- 增加 `examples/research_agent.py` 对应示例
- 增加配置 lint 规则说明
- 增加“多来源冲突处理”模板片段
- 增加中文配置示例与常见报错对照表
