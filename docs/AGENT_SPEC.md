# agentconfig `.agent/` 目录规范 & SKILL.md 兼容声明

> **版本**: 1.0.0 | **状态**: 正式版 | **维护者**: cdzzy
>
> 本规范定义了 AI Agent 便携式配置目录 `.agent/` 的标准布局、文件格式和跨工具兼容性声明。
> agentconfig 是该规范的主要实现，同时正式兼容 [SKILL.md 格式](https://github.com/yusufkaraaslan/Skill_Seekers)。

---

## 1. 背景与目标

`.agent/` 目录是一个**可移植的 Agent 大脑**。它将 AI Agent 的配置、技能、记忆、权限和协议封装在一个标准化的目录结构中，使得：

- **工具切换不丢失知识**：同一个 `.agent/` 目录可被 Claude Code、Cursor、Windsurf、Cline 等工具直接读取
- **配置即代码**：所有配置均以 YAML/MD/JSONL 等人类可读格式存储，可版本控制、可 code review
- **技能可复用**：SKILL.md 格式的技能可被导入到任意支持此规范的 Agent

本规范参考 [agentic-stack `.agent/` 约定](https://github.com/codejunkie99/agentic-stack)，并做了以下扩展：

- **MCP 工具声明**：在 `config.yaml` 中声明 MCP 服务器
- **SKILL.md 一等支持**：`skills/` 目录原生支持 SKILL.md 格式
- **三层记忆集成**：与 [engram](https://github.com/cdzzy/engram) 的 Episode/Fact/Working Context 接口对齐
- **权限即 Markdown**：`permissions.md` 和 `PREFERENCES.md` 以人类可读格式存储

---

## 2. 目录布局

```
.agent/                          # 根目录（固定名称，不可更改）
├── config.yaml                  # AgentConfig 主配置文件（必需）
├── AGENTS.md                    # 导航/概览文件（自动生成）
│
├── harness/                     # Agent Harness 配置（只读同步）
│   └── hooks/                  # 调度器和钩子
│
├── memory/                     # 记忆层（与 engram Episode/Fact/Working Context 对应）
│   ├── working/               # 工作记忆（短期，volatile）
│   ├── episodic/              # 情景记忆（历史日志，对应 engram Episode）
│   └── semantic/
│       ├── lessons.jsonl      # 毕业的经验教训（JSONL）
│       └── LESSONS.md         # 可读格式的经验教训
│
├── personal/
│   └── PREFERENCES.md         # 个人偏好
│
├── skills/                     # 技能定义（SKILL.md 格式）
│   ├── _index.md              # 技能索引
│   ├── _manifest.jsonl        # 技能清单（轻量，始终加载）
│   └── <skill-name>/
│       └── SKILL.md           # 技能详细定义（按需加载）
│
├── protocols/                  # 协议与权限
│   ├── permissions.md         # 权限定义
│   └── hook_patterns.json     # 自定义高/中风险正则模式
│
├── tools/                      # 宿主 Agent CLI 工具
├── data-layer/                # 本地数据层（可选）
└── flywheel/                  # 数据飞轮
```

---

## 3. 必需文件详解

### 3.1 `config.yaml` — AgentConfig 主配置

**格式**: YAML（支持 fallback 到 `config.json`）

**参考 schema**: `schemas/agent-config.schema.json`

**最小示例**:

```yaml
name: MyAgent
version: "1.0.0"
description: "A helpful research assistant"

model:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.7
  max_tokens: 4096

system_prompt: |
  You are a helpful research assistant.
  Always cite your sources and be precise.

max_turns: 20
stream: false
log_enabled: true
audit_enabled: true
```

**完整示例（含约束、MCP 和元数据）**:

```yaml
name: CustomerSupportBot
version: "1.2.0"
description: "Handles customer inquiries with compliance guardrails"
created_at: "2026-05-07T00:00:00Z"

intent:
  name: CustomerSupportBot
  purpose: "Answer customer questions about products and services"
  audience: "Existing customers"
  domain: customer_service
  tone: [professional, friendly, empathetic]
  language: auto
  actions_forbidden:
    - "Reveal competitor product information"
    - "Process refunds without manager approval"
  topics_forbidden:
    - "Executive compensation"
    - "Internal roadmap"
  escalation_triggers:
    - "Customer explicitly asks for a manager"
    - "Issue involves legal liability"
  max_turns: 10
  require_confirmation:
    - "Issue a full refund"
    - "Share personal customer data"

model:
  provider: anthropic
  model: claude-3-5-sonnet-20241022
  temperature: 0.5
  max_tokens: 2048
  timeout_seconds: 30

system_prompt: |
  You are a customer support agent. Be professional, friendly, and empathetic.
  Always prioritize customer satisfaction within policy guidelines.

constraints:
  - id: no-competitor-mention
    type: forbidden_topic
    description: "Do not mention or recommend competitor products"
    action: block
  - id: no-refund-approval
    type: escalation
    description: "Refunds over $100 require manager approval"
    action: escalate
    fallback_message: "Let me connect you with a manager for this refund."
  - id: no-personal-data
    type: forbidden_keyword
    description: "Do not share internal customer data"
    keywords: [ssn, social_security, password, pin_code]
    action: block

tools_enabled:
  - web_search
  - knowledge_base
  - ticket_create

tools_disabled:
  - file_write
  - email_send

max_turns: 10
stream: false
log_enabled: true
audit_enabled: true

mcp_servers:
  - name: engram-memory
    command: npx
    args: ["-y", "@cdzzy/engram"]
    description: "Long-term memory with forgetting curve"
    tools: [engram_episode_*, engram_fact_*, engram_context_*]

metadata:
  author: cdzzy
  tags: [customer-service, compliance, retail]
  preferences:
    primary_language: zh
    explanation_style: concise
    commit_message_style: conventional commits
```

---

### 3.2 `skills/_manifest.jsonl` — 技能清单

**格式**: JSONL（每行一个 JSON 对象，始终加载）

**用途**: 轻量索引，供 Agent 快速判断哪些技能可能相关

```jsonl
{"name": "research", "description": "Deep web research with citations", "triggers": ["research", "find papers", "academic"], "added_at": "2026-05-07T00:00:00Z"}
{"name": "code-review", "description": "Security-focused code review", "triggers": ["review code", "security audit", "check vulnerability"], "added_at": "2026-05-07T00:00:00Z"}
```

---

### 3.3 `skills/<skill-name>/SKILL.md` — 技能定义

**格式**: Markdown（SKILL.md 标准格式）

**字段**:

| 字段 | 必需 | 说明 |
|------|------|------|
| `# <技能名>` | ✅ | H1 标题作为技能名称 |
| `**Description**:` | ✅ | 一句话描述 |
| `**Author**:` | ❌ | 作者 |
| `**Version**:` | ❌ | 版本号，默认 1.0.0 |
| `**Tags**:` | ❌ | 标签数组 |
| `## Triggers` | ❌ | 触发词/模式列表 |
| `## Examples` | ❌ | 使用示例 |
| `## Guidelines` | ❌ | 详细指南（会转化为 system_prompt） |
| `## Constraints` | ❌ | 技能级约束 |
| `## Tools` | ❌ | 所需工具列表 |

**完整示例** (`skills/research/SKILL.md`):

```markdown
# Deep Research

**Description**: Performs comprehensive web research with source citations and structured findings.

**Author**: cdzzy
**Version**: 1.0.0
**Tags**: [research, academic, citations, web-search]

## Triggers

- "research this topic"
- "find academic papers on"
- "do a deep dive into"
- "investigate this claim"

## Examples

- "Research the latest developments in mRNA vaccine technology"
- "Find papers on transformer architecture efficiency improvements"
- "Investigate the economic impact of renewable energy adoption"

## Guidelines

You are a research assistant specializing in thorough, accurate research.

### Research Process

1. **Scope Definition**: Clarify the research question and expected depth
2. **Source Gathering**: Search for authoritative sources (academic papers, official reports, expert articles)
3. **Claim Verification**: Cross-reference claims against multiple sources
4. **Structure**: Organize findings by theme or chronology
5. **Citation**: Always cite sources with URLs when available

### Quality Standards

- Prefer peer-reviewed academic sources
- Distinguish between facts, theories, and opinions
- Note conflicting evidence transparently
- Flag information older than 3 years for data-heavy topics

### Output Format

```
## Research Findings: [Topic]

### Executive Summary
[2-3 sentence overview]

### Key Findings
[Numbered list of main findings with citations]

### Source Evidence
[Evidence 1](URL) - [Brief note]
[Evidence 2](URL) - [Brief note]

### Limitations & Gaps
[Any limitations or areas needing further research]

### References
[Full source list]
```

## Constraints

- Never fabricate sources or citations
- Do not present opinion as fact
- Always disclose when information is uncertain or outdated

## Tools

- web_search
- knowledge_base
- document_read
```

---

### 3.4 `memory/semantic/lessons.jsonl` — 经验教训

**格式**: JSONL

**用途**: 记录 Agent 从经验中学习的毕业教训，供 engram 等记忆系统使用

```jsonl
{"lesson": "Always verify JSON.parse() results with try/catch — error responses are often plain text", "category": "error-handling", "rationale": "Caught a silent failure in three-layer-interface tests", "graduated_at": "2026-05-06T20:00:00Z"}
{"lesson": "Git push to github.com:443 may timeout — use git -c http.proxy=\"\" -c http.version=HTTP/1.1 push", "category": "devops", "rationale": "Consistent timeout on Windows Git Bash", "graduated_at": "2026-05-06T20:00:00Z"}
```

---

### 3.5 `personal/PREFERENCES.md` — 个人偏好

**格式**: Markdown（键值对列表）

```markdown
# Personal Preferences

- **Preferred Name**: Rober
- **Primary Language**: 中文
- **Explanation Style**: 简练，带编号步骤
- **Testing Strategy**: 先写测试，再用 TDD
- **Commit Message Style**: conventional commits
- **Code Review Depth**: 只关注关键问题，不追求完美
```

---

### 3.6 `protocols/permissions.md` — 权限定义

**格式**: Markdown

```markdown
# Permissions

## Blocked Actions

- Do not reveal competitor product information
- Do not process refunds over $100 without manager approval
- Do not share internal technical architecture details

## Requires Confirmation

- Send email to external addresses
- Create or delete user accounts
- Generate reports containing customer PII
```

---

## 4. SKILL.md 兼容声明

agentconfig 正式支持 [SKILL.md 格式](https://github.com/yusufkaraaslan/Skill_Seekers)作为技能定义的一等格式。

### 4.1 导入 SKILL.md

```python
from agentconfig.importers.skill_seeker import import_skill

# 从文件导入
config_dict = import_skill("skills/my-skill/SKILL.md")

# 从 URL 导入
config_dict = import_skill("https://raw.githubusercontent.com/.../SKILL.md", output="config.json")

# 编程式使用
from agentconfig.importers.skill_seeker import SkillImporter
importer = SkillImporter()
metadata = importer.import_from_file("skills/research/SKILL.md")
config_dict = importer.to_agent_config_dict(metadata)
```

### 4.2 导出为 SKILL.md

```python
from agentconfig.portable import AgentDir

agent_dir = AgentDir(".agent/")
config = agent_dir.load_config()

# 手动导出技能
skill_md = f"""# {config.name}

**Description**: {config.description or 'AI Agent'}

**Author**: {config.metadata.get('author', 'unknown')}
**Version**: {config.version}

## Triggers

{chr(10).join(f'- {t}' for t in config.metadata.get('triggers', []))}

## Guidelines

{config.system_prompt}

## Constraints

{chr(10).join(f'- {c.get('description')}' for c in config.constraints)}

## Tools

{chr(10).join(f'- {t}' for t in config.tools_enabled)}
"""
```

### 4.3 SKILL.md 解析字段映射

| SKILL.md 字段 | → AgentConfig 字段 | 说明 |
|--------------|-------------------|------|
| `# <name>` | `name` | H1 → name |
| `**Description**` | `description` + `system_prompt` | 用于描述和提示词 |
| `## Triggers` | `metadata.triggers` | 元数据，供技能路由 |
| `## Guidelines` | `system_prompt` | 转化为完整系统提示词 |
| `## Constraints` | `constraints` | 逐条转为 constraint 对象 |
| `## Tools` | `tools_enabled` | 白名单工具 |
| `**Tags**` | `metadata.tags` | 元数据标签 |
| `**Author**` | `metadata.author` | 元数据 |

---

## 5. 跨工具兼容性

| 工具 | `.agent/` 读取 | SKILL.md 读取 | config.yaml | engram 集成 |
|------|-------------|--------------|------------|------------|
| **agentconfig** | ✅ 完整支持 | ✅ 完整支持 | ✅ 完整 | ✅ MCP 声明 |
| **Claude Code** | ⚠️ 部分支持 | ✅ 需配置 | ❌ | ❌ |
| **Cursor** | ⚠️ 部分支持 | ✅ 需配置 | ❌ | ❌ |
| **Windsurf** | ⚠️ 部分支持 | ⚠️ 部分 | ❌ | ❌ |
| **Cline** | ⚠️ 部分支持 | ⚠️ 部分 | ❌ | ❌ |
| **engram** | ✅ via config | ✅ via skills | ✅ via mcp_servers | ✅ 原生 |

> "✅ 完整支持" = 直接读取，无需配置
> "⚠️ 部分/需配置" = 可通过 agentconfig CLI 导出为兼容格式

---

## 6. engram 三层记忆集成

`.agent/` 目录通过 `config.yaml` 的 `mcp_servers` 字段与 [engram](https://github.com/cdzzy/engram) 集成：

```yaml
mcp_servers:
  - name: engram-memory
    command: npx
    args: ["-y", "@cdzzy/engram"]
    description: "Long-term memory with Ebbinghaus forgetting curve"
    tools:
      # Layer 1: Episode
      - engram_episode_add
      - engram_episode_search
      - engram_episode_get_session
      # Layer 2: Fact
      - engram_fact_assert
      - engram_fact_query
      - engram_fact_retract
      # Layer 3: Working Context
      - engram_context_set
      - engram_context_get
      - engram_context_clear
      - engram_context_inject
```

同时，`memory/episodic/` 目录作为 engram Episode 的文件系统备份：
`memory/semantic/lessons.jsonl` 对应 engram Fact 的毕业知识。

---

## 7. CLI 命令参考

```bash
# 初始化 .agent/ 目录
agentconfig init --path .agent/

# 从 .agent/ 加载配置
agentconfig serve --config .agent/config.yaml

# 导出配置到 .agent/ 目录
agentconfig export --input config.json --output .agent/

# 导入 SKILL.md
agentconfig import-skill --file ./skills/research/SKILL.md --output config.json

# 验证配置
agentconfig validate --config .agent/config.yaml

# 列出所有技能
agentconfig list-skills --path .agent/
```

---

## 8. 文件格式速查

| 文件路径 | 格式 | 必需 | 编码 |
|---------|------|------|------|
| `config.yaml` | YAML | ✅ | UTF-8 |
| `AGENTS.md` | Markdown | 自动 | UTF-8 |
| `skills/_manifest.jsonl` | JSONL | 自动创建 | UTF-8 |
| `skills/<name>/SKILL.md` | Markdown | 按需 | UTF-8 |
| `skills/_index.md` | Markdown | 自动 | UTF-8 |
| `memory/semantic/lessons.jsonl` | JSONL | 可选 | UTF-8 |
| `memory/semantic/LESSONS.md` | Markdown | 自动渲染 | UTF-8 |
| `personal/PREFERENCES.md` | Markdown | 可选 | UTF-8 |
| `protocols/permissions.md` | Markdown | 可选 | UTF-8 |
| `protocols/hook_patterns.json` | JSON | 可选 | UTF-8 |
| `harness/hooks/*` | 任意 | 可选 | UTF-8 |

---

## 9. 参考实现

- **Python**: [cdzzy/agentconfig](https://github.com/cdzzy/agentconfig) — `agentconfig/portable.py`
- **TypeScript**: [cdzzy/engram](https://github.com/cdzzy/engram) — 三层 MCP Server
- **参考约定**: [agentic-stack/agentic-stack](https://github.com/codejunkie99/agentic-stack)
- **SKILL.md 格式**: [Skill_Seekers](https://github.com/yusufkaraaslan/Skill_Seekers)
