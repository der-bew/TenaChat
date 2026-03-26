"""
Medical triage layer for TenaChat.

Classifies user prompts for urgent or high-risk medical situations and returns
safe escalation messages when red flags are detected.

This is an intentionally deterministic, keyword-based triage layer.  It is
designed to be fast, predictable, and maintainable without an ML classifier.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TriageLevel(str, Enum):
    EMERGENCY = "emergency"  # Immediate life-threatening: seek emergency care now
    ROUTINE = "routine"  # Normal health question


@dataclass
class TriageResult:
    level: TriageLevel
    escalation_message: Optional[str]  # None when level is ROUTINE


# ---------------------------------------------------------------------------
# Emergency patterns (English – compiled regex for efficiency)
# ---------------------------------------------------------------------------
_EMERGENCY_PATTERNS_EN: list[str] = [
    # Obstetric / maternal emergencies
    r"heavy bleeding",
    r"severe bleeding",
    r"can.?t stop bleeding",
    r"bleeding heavily",
    r"hemorrhage",
    r"haemorrhage",
    r"eclampsia",
    r"pre.?eclampsia",
    r"seizure",
    r"convulsion",
    r"not breathing",
    r"stopped breathing",
    r"can.?t breathe",
    r"difficulty breathing",
    r"shortness of breath",
    r"chest pain",
    r"severe abdominal pain",
    r"severe stomach pain",
    r"severe pelvic pain",
    r"baby (is )?not moving",
    r"no fetal movement",
    r"fetus (is )?not moving",
    r"cord prolapse",
    r"placenta previa",
    r"placental abruption",
    r"ectopic pregnancy",
    r"miscarriage.*bleed",
    # General emergencies
    r"unconscious",
    r"unresponsive",
    r"collapsed",
    r"loss of consciousness",
    r"stroke",
    r"heart attack",
    r"very high (fever|temperature)",
    r"high fever",
    r"sepsis",
    r"severe infection",
    # Mental health emergencies
    r"suicid",  # suicide / suicidal
    r"want to (kill|harm|hurt) (my)?self",
    r"kill myself",
    r"self.?harm",
    r"overdos(e|ed)",
]

# Non-English emergency terms (simple substring match)
_EMERGENCY_SUBSTRINGS_AM = [
    "ከባድ ደም",
    "ብዙ ደም",
    "ደም ማቆም",
    "ከባድ ህመም",
    "ኩላሊት ቁርጥማት",
    "ልጅ አልተንቀሳቀሰም",
    "ንቃቱ አጥቷል",
    "ራሴን ለማጥፋት",
    "ከፍተኛ ትኩሳት",
    "ሰውነቴ ተናወጠ",
]

_EMERGENCY_SUBSTRINGS_OM = [
    "dhiiga baay'ee",
    "dhiiga hamaa",
    "dhukkubbii hamaa",
    "daa'imni hin sochoone",
    "of wallaaluu",
    "of-ajjeesuu",
    "ho'a qaamaa oliiti",
]

_EMERGENCY_SUBSTRINGS_TI = [
    "ብዙሕ ደም",
    "ከቢድ ደም",
    "ከቢድ ቃንዛ",
    "ህጻን ኣይሓዘን",
    "ርእሰይ ክቐትል",
    "ርእሰይ ክጎድእ",
    "ለዓቲ ረስኒ",
]

_ALL_EMERGENCY_SUBSTRINGS: tuple[str, ...] = tuple(
    _EMERGENCY_SUBSTRINGS_AM + _EMERGENCY_SUBSTRINGS_OM + _EMERGENCY_SUBSTRINGS_TI
)

_COMPILED_EMERGENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in _EMERGENCY_PATTERNS_EN
]

# ---------------------------------------------------------------------------
# Escalation messages (per language)
# ---------------------------------------------------------------------------
EMERGENCY_ESCALATION: dict[str, str] = {
    "en": (
        "⚠️ **This sounds like a medical emergency.**\n\n"
        "Please call your local emergency number or go to the nearest hospital or "
        "health center immediately.\n\n"
        "**In Ethiopia:** Call **911** or visit the nearest health center or "
        "referral hospital.\n\n"
        "I am an information assistant only — I cannot provide emergency diagnosis "
        "or treatment. Please seek professional care right away."
    ),
    "am": (
        "⚠️ **ይህ የህክምና አደጋ ሊሆን ይችላል።**\n\n"
        "እባክዎ አሁኑኑ ወደ ቅርቡ ሆስፒታል ወይም የጤና ጣቢያ ይሂዱ ወይም አደጋ ጊዜ ስልክ ይደውሉ።\n\n"
        "**በኢትዮጵያ:** **911** ይደውሉ ወይም ወደ ቅርቡ ጤና ጣቢያ ወይም ሪፈራል ሆስፒታል ይሂዱ።\n\n"
        "እኔ የመረጃ ረዳት ብቻ ነኝ — የህክምና ምርመራ ወይም ሕክምና ልሰጥ አልችልም። "
        "እባክዎ ወዲያው ሙያዊ ዕርዳታ ይፈልጉ።"
    ),
    "om": (
        "⚠️ **Kun yeroo hatattamaa fayyaa ta'uu mala.**\n\n"
        "Maaloo hospitaala ykn giddugala fayyaa dhiyoo jiru amma dafii deemi ykn "
        "lakkoofsa hatattamaa bilbili.\n\n"
        "**Itoophiyaatti:** **911** bilbili ykn giddugala fayyaa dhiyoo deemi.\n\n"
        "Ani qofa gargaaraa odeeffannoo dha — qorannoo ykn yaala fayyaa kenna "
        "hin danda'u. Maaloo gargaarsa oggeessa amma barbaadi."
    ),
    "ti": (
        "⚠️ **እዚ ድንገተኛ ህክምናዊ ሃልዮ ክኸውን ይኽእል እዩ።**\n\n"
        "በጃኻ ሕጂ ናብ ቀረባ ሆስፒታል ወይ ናብ ናይ ጥዕና ማእከል ኪዳ ወይ ናይ ህጹጽ ቁጽሪ ደውል።\n\n"
        "**ኣብ ኢትዮጵያ:** **911** ደውል ወይ ናብ ቀረባ ናይ ጥዕና ማእከል ኪዳ።\n\n"
        "ኣነ ናይ ሓበሬታ ሓጋዚ ጥራይ ኢየ — ናይ ህክምና ምርመራ ወይ ሕክምና ክህብ ኣይክእልን። "
        "በጃኻ ቅልጡፍ ሙያዊ ሓገዝ ደሊ።"
    ),
}

# Fallback message when retrieved evidence is insufficient
INSUFFICIENT_EVIDENCE_RESPONSES: dict[str, str] = {
    "en": (
        "I don't have enough reliable information in my knowledge base to answer "
        "that question confidently.\n\n"
        "Please consult a qualified healthcare provider for accurate guidance on "
        "this topic. If this is urgent, seek care immediately."
    ),
    "am": (
        "ስለዚህ ጥያቄ በዕምነት ለመመለስ በዕውቀት መሠረቴ ውስጥ በቂ አስተማማኝ መረጃ የለኝም።\n\n"
        "ለዚህ ርዕስ ትክክለኛ መመሪያ ለማግኘት ብቁ የጤና ባለሙያ ያማክሩ። "
        "ሁኔታው አስቸኳይ ከሆነ ወዲያው እርዳታ ይፈልጉ።"
    ),
    "om": (
        "Gaaffii kana amantiidhaan deebisuuf odeeffannoo gahaa beekumsa "
        "kiyyaa keessa hin arganne.\n\n"
        "Qajeelfama sirrii argachuuf ogeessa fayyaa gahaa ta'e mariisiisi. "
        "Yeroo hatattamaa ta'e, gargaarsa hatattamaa barbaadi."
    ),
    "ti": (
        "ነዚ ሕቶ ብእምነት ንምምላስ ኣብ ናይ ሓበሬታ መሰረተይ ዘሎ ሓበሬታ ኣይኣኽልን።\n\n"
        "ናይ ክኢላ ሕክምና ኣቅርቦ ንዝርዝር ምኽሪ ርኸቦ። "
        "ህጹጽ እንተኾይኑ ቅልጡፍ ሓገዝ ደሊ።"
    ),
}


def classify_triage(query: str, language: str = "en") -> TriageResult:
    """
    Classify a user query for medical urgency.

    Returns a TriageResult with level and optional escalation message.
    This is intentionally deterministic and keyword-based for reliability and
    auditability.
    """
    if not query or not query.strip():
        return TriageResult(level=TriageLevel.ROUTINE, escalation_message=None)

    # Check English patterns (compiled regex, case-insensitive)
    for pattern in _COMPILED_EMERGENCY_PATTERNS:
        if pattern.search(query):
            msg = EMERGENCY_ESCALATION.get(language, EMERGENCY_ESCALATION["en"])
            return TriageResult(level=TriageLevel.EMERGENCY, escalation_message=msg)

    # Check non-English substrings (exact Unicode substring match)
    for substring in _ALL_EMERGENCY_SUBSTRINGS:
        if substring in query:
            msg = EMERGENCY_ESCALATION.get(language, EMERGENCY_ESCALATION["en"])
            return TriageResult(level=TriageLevel.EMERGENCY, escalation_message=msg)

    return TriageResult(level=TriageLevel.ROUTINE, escalation_message=None)


def get_insufficient_evidence_response(language: str = "en") -> str:
    """Return an appropriate uncertainty/fallback message when retrieval confidence is low."""
    return INSUFFICIENT_EVIDENCE_RESPONSES.get(
        language, INSUFFICIENT_EVIDENCE_RESPONSES["en"]
    )
