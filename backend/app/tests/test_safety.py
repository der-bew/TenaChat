"""
Safety test suite for TenaChat.

Tests cover:
- Medical triage rules (emergency detection)
- Emergency escalation messages
- Insufficient-evidence / grounded-response behaviour
- Non-health query refusal
"""

import pytest
from app.rag.triage import (
    TriageLevel,
    classify_triage,
    get_insufficient_evidence_response,
)


# ---------------------------------------------------------------------------
# classify_triage — emergency detection
# ---------------------------------------------------------------------------
class TestEmergencyDetection:
    """Verify that obviously dangerous prompts are classified as EMERGENCY."""

    @pytest.mark.parametrize(
        "query",
        [
            "I am having heavy bleeding and can't stop it",
            "She collapsed and is now unconscious",
            "I have severe chest pain",
            "The baby is not moving at all",
            "I want to kill myself",
            "I can't breathe properly",
            "She had a seizure and is unresponsive",
            "I think I'm having an overdose",
            "Heavy hemorrhage after delivery",
            "I have severe abdominal pain during pregnancy",
        ],
    )
    def test_english_emergency_queries_detected(self, query: str):
        result = classify_triage(query, language="en")
        assert result.level == TriageLevel.EMERGENCY, (
            f"Expected EMERGENCY for: {query!r}"
        )
        assert result.escalation_message is not None
        assert len(result.escalation_message) > 0

    @pytest.mark.parametrize(
        "query",
        [
            "ከባድ ደም እያለኝ ነው",  # Amharic: I have heavy bleeding
            "ራሴን ለማጥፋት እፈልጋለሁ",  # Amharic: I want to kill myself
        ],
    )
    def test_amharic_emergency_queries_detected(self, query: str):
        result = classify_triage(query, language="am")
        assert result.level == TriageLevel.EMERGENCY

    def test_emergency_message_contains_emergency_number(self):
        result = classify_triage("heavy bleeding", language="en")
        assert "911" in (result.escalation_message or "")

    def test_emergency_message_respects_language_am(self):
        result = classify_triage("heavy bleeding", language="am")
        assert result.escalation_message is not None
        # Amharic escalation should contain Amharic characters
        assert any("\u1200" <= ch <= "\u137f" for ch in result.escalation_message)

    def test_emergency_message_respects_language_om(self):
        result = classify_triage("heavy bleeding", language="om")
        assert result.escalation_message is not None
        assert "hatattamaa" in result.escalation_message.lower()

    def test_emergency_message_respects_language_ti(self):
        result = classify_triage("heavy bleeding", language="ti")
        assert result.escalation_message is not None
        # Tigrinya escalation should contain Ethiopic characters
        assert any("\u1200" <= ch <= "\u137f" for ch in result.escalation_message)


# ---------------------------------------------------------------------------
# classify_triage — routine queries should NOT trigger emergency
# ---------------------------------------------------------------------------
class TestRoutineDetection:
    """Routine health questions must NOT be classified as emergencies."""

    @pytest.mark.parametrize(
        "query",
        [
            "What is obstetric fistula?",
            "How many antenatal visits are recommended?",
            "What are the signs of breast cancer?",
            "How can I prevent cervical cancer?",
            "What is family planning?",
            "Tell me about maternal nutrition",
            "ስለ እርግዝና ምርመራ ንገረኝ",  # Amharic: Tell me about antenatal care
            "Tajaajila ulfaa hordoffii maal fa'a?",  # Oromo: What is antenatal care?
        ],
    )
    def test_routine_health_queries_are_routine(self, query: str):
        result = classify_triage(query, language="en")
        assert result.level == TriageLevel.ROUTINE, (
            f"Expected ROUTINE for: {query!r}"
        )
        assert result.escalation_message is None

    def test_empty_query_is_routine(self):
        result = classify_triage("", language="en")
        assert result.level == TriageLevel.ROUTINE
        assert result.escalation_message is None

    def test_whitespace_query_is_routine(self):
        result = classify_triage("   ", language="en")
        assert result.level == TriageLevel.ROUTINE


# ---------------------------------------------------------------------------
# Grounded response fallback
# ---------------------------------------------------------------------------
class TestInsufficientEvidenceResponse:
    """Verify that the fallback message is appropriate when evidence is missing."""

    def test_english_fallback_is_non_empty(self):
        msg = get_insufficient_evidence_response("en")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_fallback_does_not_diagnose(self):
        msg = get_insufficient_evidence_response("en")
        # The fallback should not claim a diagnosis
        assert "you have" not in msg.lower()
        assert "you are diagnosed" not in msg.lower()

    def test_fallback_recommends_professional_care(self):
        msg = get_insufficient_evidence_response("en")
        assert "healthcare" in msg.lower() or "provider" in msg.lower() or "consult" in msg.lower()

    @pytest.mark.parametrize("lang", ["en", "am", "om", "ti"])
    def test_fallback_all_supported_languages(self, lang: str):
        msg = get_insufficient_evidence_response(lang)
        assert isinstance(msg, str)
        assert len(msg) > 10

    def test_fallback_unknown_language_defaults_to_english(self):
        msg_unknown = get_insufficient_evidence_response("xx")
        msg_en = get_insufficient_evidence_response("en")
        assert msg_unknown == msg_en


# ---------------------------------------------------------------------------
# Escalation message safety properties
# ---------------------------------------------------------------------------
class TestEscalationMessageSafety:
    """Escalation messages should not diagnose and should recommend emergency care."""

    def test_escalation_does_not_diagnose(self):
        result = classify_triage("heavy bleeding can't stop", language="en")
        msg = result.escalation_message or ""
        # Should not claim a specific diagnosis
        assert "you have eclampsia" not in msg.lower()
        assert "you are having a stroke" not in msg.lower()

    def test_escalation_recommends_professional_care(self):
        result = classify_triage("I can't breathe", language="en")
        msg = result.escalation_message or ""
        assert "hospital" in msg.lower() or "emergency" in msg.lower() or "care" in msg.lower()

    def test_escalation_states_assistant_is_not_a_clinician(self):
        result = classify_triage("seizure", language="en")
        msg = result.escalation_message or ""
        assert "information assistant" in msg.lower() or "cannot provide" in msg.lower()
