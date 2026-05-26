"""core.signals enum 단위 테스트."""

from core.signals import AGENT_TO_SIGNAL, ALL_AGENT_SIGNALS, AgentSignal


class TestAgentSignal:
    def test_all_signals_unique(self):
        values = [s.value for s in AgentSignal]
        assert len(values) == len(set(values)), "신호 값에 중복이 있다"

    def test_agent_to_signal_covers_nine_agents(self):
        assert len(AGENT_TO_SIGNAL) == 9

    def test_signal_format(self):
        for signal in AgentSignal:
            assert signal.value.endswith("_COMPLETE"), f"{signal.name} 신호는 _COMPLETE로 끝나야 함"

    def test_supervisor_signal_excluded_from_agent_signals(self):
        assert AgentSignal.SUPERVISOR.value not in ALL_AGENT_SIGNALS

    def test_agent_to_signal_keys_match_expected(self):
        expected = {
            "context_expert",
            "sentiment_expert",
            "financial_expert",
            "advanced_technical_expert",
            "institutional_trading_expert",
            "comparative_expert",
            "esg_expert",
            "community_expert",
            "global_market_expert",
        }
        assert set(AGENT_TO_SIGNAL.keys()) == expected
