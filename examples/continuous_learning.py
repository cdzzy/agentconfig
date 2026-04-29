"""
agentconfig examples: Hermite-Style Continuous Learning Integration
参考 hermes-agent 的持续学习模式，为 agentconfig 增加动态配置演进能力。
hermes-agent 强调 AI Agent 与用户共同成长，配置需要具备自我调整能力。
"""

from agentconfig import AgentConfig


class ContinuousLearner:
    """
    持续学习配置管理器。
    模仿 hermes-agent 的成长型 Agent 理念，配置参数会随交互历史动态优化。
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.interaction_history: list[dict] = []

    def record_interaction(self, input_text: str, output_quality: float):
        """
        记录一次交互，用于后续配置调优。
        input_text: 自然语言配置输入
        output_quality: 输出质量评分 [0, 1]
        """
        self.interaction_history.append({
            "input": input_text,
            "quality": output_quality,
        })

    def suggest_improvement(self) -> str:
        """
        基于历史交互，生成配置改进建议。
        模仿 hermes-agent 的自我演进能力。
        """
        if not self.interaction_history:
            return "需要更多交互数据才能生成改进建议"

        low_quality = [h for h in self.interaction_history if h["quality"] < 0.6]
        if low_quality:
            # 分析低质量交互的共同特征
            inputs = [h["input"] for h in low_quality]
            return (
                f"检测到 {len(low_quality)} 次低质量交互。"
                "建议增强 temperature 控制或添加领域特定约束。"
            )
        return "当前配置运行良好，无需调整"


def evolve_config(initial_config: str) -> str:
    """
    演示配置从初始状态到演进状态的完整流程。
    类似于 hermes-agent 的 "The agent that grows with you" 理念。
    """
    config = AgentConfig.parse(initial_config)
    learner = ContinuousLearner(config)

    # 模拟交互序列
    interactions = [
        ("a helpful coding assistant", 0.85),
        ("a strict code reviewer", 0.72),
        ("a creative writer", 0.91),
        ("a precise data analyst", 0.68),  # 配置不完全匹配
    ]

    for text, quality in interactions:
        learner.record_interaction(text, quality)

    suggestion = learner.suggest_improvement()
    print(f"动态建议: {suggestion}")

    # 生成改进后的配置
    evolved = config.evolve(
        temperature=0.75,  # 调高中位数温度以改善分析类任务
        max_tokens=4096,
    )
    return evolved.to_natural_language()


if __name__ == "__main__":
    evolved = evolve_config("a helpful AI assistant")
    print(f"演进配置:\n{evolved}")
