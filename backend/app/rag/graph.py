"""
Backend for the Ethiopian Women Health Chatbot
version: 3.0.0
Author: Derbew Felasman
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, List, TypedDict, cast

from app.config import (
    OPENAI_API_KEY,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SERPER_API_KEY,
)
from app.db.supabase_client import get_supabase_client, supabase
from app.rag.triage import TriageLevel, classify_triage, get_insufficient_evidence_response
from langchain_community.utilities.google_serper import GoogleSerperAPIWrapper
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import SecretStr

if TYPE_CHECKING:
    from langchain_openai import OpenAIEmbeddings
else:
    OpenAIEmbeddings = Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

EMBEDDING_MODEL = "text-embedding-3-large"
LEGACY_OPENAI_AGENT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENROUTER_PRIMARY_MODEL = os.getenv(
    "OPENROUTER_PRIMARY_MODEL", "google/gemma-4-31b-it:free"
)
OPENROUTER_FALLBACK_MODEL = os.getenv(
    "OPENROUTER_FALLBACK_MODEL", "google/gemini-2.5-flash"
)
SHORT_TERM_MEMORY_LIMIT = 8
LONG_TERM_MEMORY_LIMIT = 10
RETRIEVAL_TOP_K = 3  # Number of documents to retrieve per query
LLM_TIMEOUT_SECONDS = 25

SUPPORTED_LANGUAGES = ("en", "am", "om", "ti")

# English + Amharic + Afaan Oromo + Tigrinya health terms.
# This is a practical first-pass detector (keyword-based), now multilingual.
HEALTH_DOMAIN_KEYWORDS = [
    # English
    "health",
    "medical",
    "medicine",
    "doctor",
    "nurse",
    "hospital",
    "clinic",
    "symptom",
    "symptoms",
    "disease",
    "illness",
    "diagnosis",
    "treatment",
    "prevention",
    "pregnancy",
    "maternal",
    "neonatal",
    "breast",
    "cervical",
    "cancer",
    "menstruation",
    "menstrual",
    "period",
    "contraception",
    "family planning",
    "fertility",
    "infertility",
    "ovulation",
    "breastfeeding",
    "nutrition",
    "mental health",
    "depression",
    "anxiety",
    "obstetric",
    "fistula",
    "hiv",
    "sti",
    "std",
    "infection",
    "fever",
    "pain",
    "vaccine",
    "vaccination",
    "blood pressure",
    "diabetes",
    "ultrasound",
    "antenatal",
    "postnatal",
    "labor",
    "delivery",
    # Amharic
    "ጤና",
    "ሕክምና",
    "ሆስፒታል",
    "ክሊኒክ",
    "ዶክተር",
    "ነርስ",
    "እርግዝና",
    "እርጉዝ",
    "ወሊድ",
    "ምርመራ",
    "የደም ግፊት",
    "የስኳር በሽታ",
    "ካንሰር",
    "የማህፀን",
    "የጡት",
    "ቤተሰብ ዕቅድ",
    "የወር አበባ",
    "መድሃኒት",
    "ህመም",
    "ትኩሳት",
    "ክትባት",
    "ኤችአይቪ",
    "ኢንፌክሽን",
    # Afaan Oromo
    "fayyaa",
    "yaala",
    "hospitaala",
    "kilinika",
    "dooktara",
    "narsi",
    "ulfaa",
    "ulfa",
    "da'umsa",
    "qorannoo",
    "dhiibbaa dhiigaa",
    "sukkaar",
    "kaansarii",
    "maatii karoora",
    "laguu",
    "dhukkuba",
    "dhukkubbii",
    "ho'a qaamaa",
    "talaallii",
    "hiv",
    "infekshinii",
    # Tigrinya
    "ጥዕና",
    "ሕክምና",
    "ሆስፒታል",
    "ክሊኒክ",
    "ሓኪም",
    "ነርስ",
    "ጥንሲ",
    "ሕርሲ",
    "ምርመራ",
    "ጸቕጢ ደም",
    "ሽኮርያ",
    "ካንሰር",
    "ማህጸን",
    "ጡብ",
    "ውጥን ስድራ",
    "ወርሓዊ ርግደት",
    "መድሃኒት",
    "ሕመም",
    "ረስኒ",
    "ክታበት",
    "ኤችኣይቪ",
    "ረኽሲ",
]

NON_HEALTH_REFUSAL_MESSAGES = {
    "en": (
        "I can only help with health-related questions. Please ask about health, "
        "maternal care, reproductive health, cancer, symptoms, prevention, treatment, "
        "or other medical concerns."
    ),
    "am": (
        "እኔ ልረዳ የምችለው ከጤና ጋር በተያያዙ ጥያቄዎች ብቻ ነው። "
        "እባክዎ ስለ ጤና፣ የእናቶች እንክብካቤ፣ የመራቢያ ጤና፣ ካንሰር፣ "
        "ምልክቶች፣ መከላከል ወይም ሕክምና ይጠይቁ።"
    ),
    "om": (
        "Gaaffiiwwan fayyaa waliin walqabatan qofaan si gargaaruu danda'a. "
        "Maaloo waa'ee fayyaa, kunuunsa haadholii, fayyaa hormaataa, kaansarii, "
        "mallattoo dhukkubaa, ittisa yookaan yaalaa gaafadhaa."
    ),
    "ti": (
        "ኣነ ክሕግዘኪ/ክሕግዘካ ዝኽእል ብጉዳያት ጥዕና ጥራይ እዩ። "
        "በጃኺ/በጃኻ ብዛዕባ ጥዕና፣ ክንክን ኣዴታት፣ ናይ ምውላድ ጥዕና፣ "
        "ካንሰር፣ ምልክታት፣ ምክልኻል ወይ ሕክምና ሕተት።"
    ),
}

# Initialize embeddings with OpenAI multilingual-capable model (lazy loading)
embeddings = None
vectorstore = None
serper = None


def _init_embeddings() -> Embeddings | bool:
    global embeddings
    if embeddings is None:
        try:
            from langchain_openai import OpenAIEmbeddings as RuntimeOpenAIEmbeddings

            embeddings = RuntimeOpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                api_key=SecretStr(OPENAI_API_KEY) if OPENAI_API_KEY else None,
            )
            logger.info(f"Using {EMBEDDING_MODEL} for embeddings")
        except Exception as e:
            logger.warning(f"OpenAI embeddings not available: {e}")
            embeddings = False
    return cast(Embeddings | bool, embeddings)


def _load_vectorstore():
    global vectorstore
    if vectorstore is None:
        emb = _init_embeddings()
        if emb is not False:
            embedding_model = cast(Embeddings, emb)
            try:
                vectorstore = FAISS.load_local(
                    str(KNOWLEDGE_BASE_DIR),
                    embedding_model,
                    allow_dangerous_deserialization=True,
                )
                logger.info("FAISS vector store loaded successfully")
            except FileNotFoundError:
                logger.warning(
                    "Warning: FAISS index not found—run python backend/app/rag/indexer.py to build it"
                )
            except Exception as e:
                logger.error(f"Error loading FAISS index: {e}")
    return vectorstore


serper_available = bool(SERPER_API_KEY and SERPER_API_KEY != "your_serper_api_key_here")
if serper_available:
    try:
        serper = GoogleSerperAPIWrapper(serper_api_key=SERPER_API_KEY, k=5)
    except Exception as e:
        logger.error(f"Failed to initialize Serper: {e}")
        serper_available = False

def _build_chat_llm(
    model: str, api_key: str | None, base_url: str | None = None
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=0.3,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
        max_tokens=220,
        api_key=SecretStr(api_key) if api_key else None,
        base_url=base_url,
    )


def _build_generation_llms() -> tuple[str, ChatOpenAI, str | None, ChatOpenAI | None]:
    if OPENROUTER_API_KEY:
        logger.info(
            "Using OpenRouter chat models primary=%s fallback=%s",
            OPENROUTER_PRIMARY_MODEL,
            OPENROUTER_FALLBACK_MODEL,
        )
        return (
            OPENROUTER_PRIMARY_MODEL,
            _build_chat_llm(
                model=OPENROUTER_PRIMARY_MODEL,
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            OPENROUTER_FALLBACK_MODEL,
            _build_chat_llm(
                model=OPENROUTER_FALLBACK_MODEL,
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
        )

    logger.warning(
        "OPENROUTER_API_KEY not configured; using legacy OpenAI chat model %s",
        LEGACY_OPENAI_AGENT_MODEL,
    )
    return (
        LEGACY_OPENAI_AGENT_MODEL,
        _build_chat_llm(model=LEGACY_OPENAI_AGENT_MODEL, api_key=OPENAI_API_KEY),
        None,
        None,
    )


ACTIVE_PRIMARY_AGENT_MODEL, llm, ACTIVE_FALLBACK_AGENT_MODEL, fallback_llm = (
    _build_generation_llms()
)


def _invoke_generation_llm(messages: List[BaseMessage]):
    try:
        return llm.invoke(messages)
    except Exception as primary_error:
        if fallback_llm is None or ACTIVE_FALLBACK_AGENT_MODEL is None:
            raise
        logger.warning(
            "Primary chat model %s failed; retrying with fallback %s: %s",
            ACTIVE_PRIMARY_AGENT_MODEL,
            ACTIVE_FALLBACK_AGENT_MODEL,
            primary_error,
        )
        return fallback_llm.invoke(messages)


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    context: str
    user_id: str
    conversation_id: str
    auth_token: str | None
    has_existing_conversation: bool
    is_anonymous: bool
    short_term_memory: str
    long_term_memory: str
    is_health_query: bool
    language: str
    requested_language: str
    # Triage result: "routine" or "emergency"
    triage_level: str
    # Retrieved source documents for citation
    sources: List[dict]
    # Whether retrieved evidence was sufficient to ground a response
    has_evidence: bool


@tool(description="Search the web for up-to-date information")
def web_search(query: str) -> str:
    """Search the web using Serper."""
    web_context, _, has_evidence = _search_web_with_sources(query)
    if not has_evidence:
        return "Web search not available."
    return web_context


def _search_web_with_sources(query: str) -> tuple[str, List[dict], bool]:
    if not serper or not serper_available:
        return "Web search not available.", [], False
    try:
        results = serper.results(query)
        organic_results = results.get("organic", [])
        if not organic_results:
            return "No relevant web results found.", [], False

        sources: List[dict] = []
        formatted_results: List[str] = []

        for item in organic_results[:5]:
            title = item.get("title", "N/A")
            snippet = item.get("snippet", "N/A")
            link = item.get("link", "N/A")
            formatted_results.append(
                f"Title: {title}\nSnippet: {snippet}\nURL: {link}"
            )
            if link and link != "N/A":
                sources.append(
                    {
                        "source": link,
                        "file_type": "web",
                        "title": title,
                    }
                )

        return "\n".join(formatted_results), sources, True
    except Exception as e:
        logger.warning("Web search unavailable for query: %s", e)
        return "Web search not available.", [], False


def _format_short_term_memory(messages: List[BaseMessage]) -> str:
    if not messages:
        return "No short-term memory available."

    recent_messages = messages[-SHORT_TERM_MEMORY_LIMIT:]
    lines = []
    for msg in recent_messages:
        role = "assistant"
        if isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            role = msg.type
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)


def _load_long_term_memory(conversation_id: str, auth_token: str | None = None) -> str:
    if not conversation_id:
        return "No long-term memory available."
    try:
        db_client = get_supabase_client(auth_token) if auth_token else supabase
        result = (
            db_client.table("messages")
            .select("role, content")
            .eq("conversation_id", conversation_id)
            .order("timestamp")
            .limit(LONG_TERM_MEMORY_LIMIT)
            .execute()
        )
        if not result.data:
            return "No long-term memory available."
        return "\n".join(
            [
                f"{msg['role']}: {msg['content']}"
                for msg in result.data[-LONG_TERM_MEMORY_LIMIT:]
            ]
        )
    except Exception as e:
        logger.error(f"Error retrieving long-term memory: {e}")
        return "Error retrieving long-term memory."


def _detect_language(query: str) -> str:
    """Lightweight language detection for en/am/om/ti with script + keyword heuristics."""
    text = (query or "").strip()
    if not text:
        return "en"

    lowered = text.lower()

    # Ethiopic script detection (Amharic/Tigrinya likely)
    if re.search(r"[\u1200-\u137F]", text):
        am_markers = ["እርግዝና", "ጤና", "የ", "እንዴት", "እባክ", "ሕክምና"]
        ti_markers = ["ኣብ", "እዋን", "እንታይ", "ጥንሲ", "ጥዕና", "ክ", "ዘለዎም"]
        am_score = sum(1 for m in am_markers if m in text)
        ti_score = sum(1 for m in ti_markers if m in text)
        return "ti" if ti_score > am_score else "am"

    # Afaan Oromo heuristic
    om_markers = [
        "akka",
        "maal",
        "maali",
        "gaaffii",
        "fayyaa",
        "ulfaa",
        "yeroo",
        "qorannoo",
        "taasifamuu",
        "danda",
        "godhu",
        "dha",
    ]
    if sum(1 for m in om_markers if m in lowered) >= 2:
        return "om"

    return "en"


def _looks_like_health_query(query: str) -> bool:
    normalized_query = query.lower()
    return any(keyword in normalized_query for keyword in HEALTH_DOMAIN_KEYWORDS)


def _is_health_related_query(query: str, detected_language: str) -> bool:
    """
    Fast multilingual health guard.

    This intentionally avoids an additional LLM classification call, which adds
    a full model round-trip to every request and significantly increases latency.
    """
    if _looks_like_health_query(query):
        return True

    short_query = (query or "").strip().lower()
    if not short_query:
        return False

    # Supported-language queries in this app are overwhelmingly health-related.
    # Treat short question patterns as in-domain unless they clearly look like
    # generic chit-chat or unrelated requests.
    non_health_starters = (
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "who are you",
        "what can you do",
    )
    if any(short_query.startswith(starter) for starter in non_health_starters):
        return False

    if detected_language in SUPPORTED_LANGUAGES and len(short_query) >= 8:
        return True

    return False


def _refusal_message_for_language(language: str) -> str:
    return NON_HEALTH_REFUSAL_MESSAGES.get(language, NON_HEALTH_REFUSAL_MESSAGES["en"])


@tool(description="Search the vector knowledge base for relevant health information")
def vector_retriever(query: str) -> str:
    """Retrieve from FAISS vector DB."""
    vs = _load_vectorstore()
    if vs is None:
        return "Knowledge base not available—using general info."
    try:
        docs = vs.similarity_search(query, k=RETRIEVAL_TOP_K)
        return (
            "\n".join([doc.page_content for doc in docs])
            if docs
            else "No matching knowledge found."
        )
    except Exception as e:
        logger.error(f"Error retrieving from vector DB: {e}")
        return "Error retrieving from knowledge base."


def _retrieve_with_sources(query: str) -> tuple[str, List[dict], bool]:
    """
    Retrieve from FAISS vector DB and return (context_text, sources, has_evidence).

    ``has_evidence`` is True only when at least one relevant document was found.
    Sources are deduplicated metadata dicts with at least a 'source' key.
    """
    vs = _load_vectorstore()
    if vs is None:
        return "Knowledge base not available—using general info.", [], False
    try:
        docs: list[Document] = vs.similarity_search(query, k=RETRIEVAL_TOP_K)
        if not docs:
            return "No matching knowledge found.", [], False

        context_text = "\n".join([doc.page_content for doc in docs])

        # Deduplicate sources preserving order
        seen: set[str] = set()
        sources: List[dict] = []
        for doc in docs:
            meta = doc.metadata or {}
            src_name = meta.get("source", "")
            if src_name and src_name not in seen:
                seen.add(src_name)
                sources.append(
                    {
                        "source": src_name,
                        "file_type": meta.get("file_type", ""),
                    }
                )
        return context_text, sources, True
    except Exception as e:
        logger.error(f"Error retrieving from vector DB: {e}")
        return "Error retrieving from knowledge base.", [], False


tools = [vector_retriever, web_search]


def retrieve(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    user_query = (
        last_message.content
        if isinstance(last_message, HumanMessage)
        and isinstance(last_message.content, str)
        else str(last_message)
    )

    requested_language = state.get("requested_language", "").strip().lower()
    detected_language = _detect_language(user_query)
    language = (
        requested_language
        if requested_language in SUPPORTED_LANGUAGES
        else detected_language
    )
    state["requested_language"] = requested_language
    state["language"] = language

    # --- Triage: check for medical emergencies before any other processing ---
    triage = classify_triage(user_query, language)
    state["triage_level"] = triage.level.value
    logger.info(
        "Triage result for conversation %s: %s",
        state.get("conversation_id", "unknown"),
        triage.level.value,
    )

    if triage.level == TriageLevel.EMERGENCY:
        state["is_health_query"] = True
        state["has_evidence"] = True  # escalation message is self-contained
        state["sources"] = []
        state["short_term_memory"] = "Not used for emergency escalation."
        state["long_term_memory"] = "Not used for emergency escalation."
        state["context"] = triage.escalation_message or ""
        return state

    # --- Health domain check ---
    is_health_query = _is_health_related_query(user_query, detected_language)
    state["is_health_query"] = is_health_query

    if not is_health_query:
        state["has_evidence"] = False
        state["sources"] = []
        state["short_term_memory"] = "Not used for non-health queries."
        state["long_term_memory"] = "Not used for non-health queries."
        state["context"] = _refusal_message_for_language(language)
        return state

    # --- Retrieval with metrics ---
    retrieval_start = time.monotonic()
    short_term_memory = _format_short_term_memory(messages[:-1])
    if state.get("has_existing_conversation") and not state.get("is_anonymous"):
        long_term_memory = _load_long_term_memory(
            state["conversation_id"], state.get("auth_token")
        )
    else:
        long_term_memory = "No long-term memory available."
    vector_context, sources, has_evidence = _retrieve_with_sources(user_query)
    retrieval_latency_ms = (time.monotonic() - retrieval_start) * 1000

    logger.info(
        "Retrieval metrics — conversation: %s | sources: %d | has_evidence: %s | latency_ms: %.1f",
        state.get("conversation_id", "unknown"),
        len(sources),
        has_evidence,
        retrieval_latency_ms,
    )

    needs_web_search = any(
        keyword in user_query.lower()
        for keyword in [
            "latest",
            "current",
            "today",
            "recent",
            "news",
            "update",
            "search",
            "ዛሬ",
            "አዲስ",
            "haaraa",
            "amma",
            "ሎሚ",
            "ሓድሽ",
        ]
    )

    web_results = "Web search not needed."
    web_sources: List[dict] = []
    web_has_evidence = False
    if needs_web_search:
        web_start = time.monotonic()
        web_results, web_sources, web_has_evidence = _search_web_with_sources(
            user_query
        )
        logger.info(
            "Web search metrics — conversation: %s | used: %s | sources: %d | has_evidence: %s | latency_ms: %.1f",
            state.get("conversation_id", "unknown"),
            needs_web_search,
            len(web_sources),
            web_has_evidence,
            (time.monotonic() - web_start) * 1000,
        )

    combined_sources: List[dict] = list(sources)
    seen_sources = {source.get("source", "") for source in combined_sources}
    for source in web_sources:
        source_name = source.get("source", "")
        if source_name and source_name not in seen_sources:
            seen_sources.add(source_name)
            combined_sources.append(source)

    state["has_evidence"] = has_evidence or (needs_web_search and web_has_evidence)
    state["sources"] = combined_sources

    state["short_term_memory"] = short_term_memory
    state["long_term_memory"] = long_term_memory
    state["context"] = (
        f"Short-term memory:\n{short_term_memory}\n\n"
        f"Long-term memory:\n{long_term_memory}\n\n"
        f"Knowledge base:\n{vector_context}\n\n"
        f"Web search:\n{web_results}"
    )
    return state


def generate(state: AgentState):
    language = state.get("language", "en")

    # Emergency: return escalation message directly (already set in context by retrieve)
    if state.get("triage_level") == TriageLevel.EMERGENCY.value:
        escalation_msg = state.get("context", "")
        return {"messages": [AIMessage(content=escalation_msg)]}

    if not state.get("is_health_query", False):
        return {
            "messages": [AIMessage(content=_refusal_message_for_language(language))]
        }

    # Grounding policy: if no evidence was retrieved, return an uncertainty response
    # instead of speculative guidance.
    if not state.get("has_evidence", False):
        logger.info(
            "Insufficient evidence for conversation %s — returning fallback response",
            state.get("conversation_id", "unknown"),
        )
        fallback = get_insufficient_evidence_response(language)
        return {"messages": [AIMessage(content=fallback)]}

    system_prompt = (
        "You are a helpful health chatbot for Ethiopian women. "
        "Answer only health-related questions. "
        "Use the provided knowledge-base context as the main source of truth. "
        "Respond in the selected language. "
        "Keep the answer concise, natural, and actionable. "
        "Prefer one short intro sentence followed by 3 to 5 bullets. "
        "Avoid long explanations, repetition, and unnecessary headings. "
        "If the answer is uncertain or depends on a clinician, say so briefly."
    )
    last_message = state["messages"][-1]
    user_prompt = (
        last_message.content
        if isinstance(last_message, HumanMessage)
        and isinstance(last_message.content, str)
        else str(last_message)
    )
    context = state["context"]

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Selected response language: {language}\n\n"
                f"Context:\n{context}\n\n"
                f"Current user query:\n{user_prompt}\n\n"
                f"Respond in language code '{language}'.\n"
                "Treat the selected response language as authoritative when it is supported.\n"
                "Return concise Markdown.\n"
                "Target about 80 to 140 words total.\n"
                "Use at most 5 bullets.\n"
                "For Amharic, Afaan Oromo, and Tigrinya, prioritize natural local phrasing."
            )
        ),
    ]

    generation_start = time.monotonic()
    response = _invoke_generation_llm(messages)
    response_content = (
        response.content if isinstance(response.content, str) else str(response.content)
    )
    logger.info(
        "Generation metrics — conversation: %s | language: %s | latency_ms: %.1f",
        state.get("conversation_id", "unknown"),
        language,
        (time.monotonic() - generation_start) * 1000,
    )
    return {"messages": [AIMessage(content=response_content)]}


workflow = StateGraph(state_schema=AgentState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("generate", generate)
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)
workflow.set_entry_point("retrieve")

memory = InMemorySaver()
agent_graph = workflow.compile(checkpointer=memory)
