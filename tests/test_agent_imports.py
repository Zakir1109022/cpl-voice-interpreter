"""Import smoke test for the agent wiring modules.

``agent.session`` and ``agent.translation`` depend on the full LiveKit runtime
(room context, rtc types) and are not unit-tested here, but a plain import
catches syntax errors, bad relative imports, and missing plugin dependencies
introduced while wiring dynamic voice preservation.
"""

from __future__ import annotations


def test_agent_runtime_modules_import() -> None:
    import agent.dynamic_tts
    import agent.session
    import agent.translation
    import agent.voice_enroll

    assert callable(agent.translation.build_session)
    assert agent.session.InterpreterManager is not None
    assert agent.dynamic_tts.DynamicVoiceTTS is not None
    assert agent.voice_enroll.VoiceEnroller is not None
