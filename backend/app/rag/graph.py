"""
Backend for the Ethiopian Women Health Chatbot
version: 2.1.0
Author: Derbew Felasman
"""

import logging
import re
from typing import TYPE_CHECKING, Annotated, Any, List, TypedDict, cast

from app.config import OPENAI_API_KEY, SERPER_API_KEY
from app.db.supabase_client import supabase
from langchain_community.utilities.google_serper import GoogleSerperAPIWrapper
from langchain_community.vectorstores import FAISS
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

EMBEDDING_MODEL = "text-embedding-3-large"
AGENT_MODEL = "gpt-4o-mini"
SHORT_TERM_MEMORY_LIMIT = 8
LONG_TERM_MEMORY_LIMIT = 10

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
                    "knowledge_base",
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

llm = ChatOpenAI(
    model=AGENT_MODEL,
    temperature=0.7,
    api_key=SecretStr(OPENAI_API_KEY) if OPENAI_API_KEY else None,
)


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    context: str
    user_id: str
    conversation_id: str
    short_term_memory: str
    long_term_memory: str
    is_health_query: bool
    language: str
    requested_language: str


@tool(description="Search the web for up-to-date information")
def web_search(query: str) -> str:
    """Search the web using Serper."""
    if not serper or not serper_available:
        return "Web search not available."
    try:
        results = serper.results(query)
        organic_results = results.get("organic", [])
        formatted = "\n".join(
            [
                f"Title: {item.get('title', 'N/A')}\nSnippet: {item.get('snippet', 'N/A')}\nURL: {item.get('link', 'N/A')}"
                for item in organic_results[:5]
            ]
        )
        return formatted if formatted else "No relevant web results found."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return "Error during web search."


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


def _load_long_term_memory(conversation_id: str) -> str:
    if not conversation_id:
        return "No long-term memory available."
    try:
        result = (
            supabase.table("messages")
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
    Multilingual health guard.
    1) fast keyword check across supported languages
    2) fallback intent classification via LLM (allows non-keyword phrasing)
    """
    if _looks_like_health_query(query):
        return True

    try:
        classifier_prompt = (
            "You are a strict intent classifier.\n"
            "Task: Decide whether the user query is health/medical-related.\n"
            "The user may write in English, Amharic, Afaan Oromo, or Tigrinya.\n"
            "Return exactly one token: YES or NO.\n"
            "Mark YES for questions about symptoms, disease, pregnancy, maternal care, "
            "reproductive health, cancer, treatment, prevention, clinics/hospitals, tests, medicines.\n"
            "Mark NO for unrelated topics like coding, politics, finance, sports, entertainment."
        )
        result = llm.invoke(
            [
                SystemMessage(content=classifier_prompt),
                HumanMessage(
                    content=f"Language hint: {detected_language}\nUser query: {query}"
                ),
            ]
        )
        text = (
            result.content.strip().upper()
            if isinstance(result.content, str)
            else str(result.content).strip().upper()
        )
        return text.startswith("YES")
    except Exception as e:
        logger.warning(
            f"Health intent classification failed, using keyword fallback only: {e}"
        )
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
        docs = vs.similarity_search(query, k=5)
        return (
            "\n".join([doc.page_content for doc in docs])
            if docs
            else "No matching knowledge found."
        )
    except Exception as e:
        logger.error(f"Error retrieving from vector DB: {e}")
        return "Error retrieving from knowledge base."


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

    is_health_query = _is_health_related_query(user_query, detected_language)
    state["is_health_query"] = is_health_query

    if not is_health_query:
        state["short_term_memory"] = "Not used for non-health queries."
        state["long_term_memory"] = "Not used for non-health queries."
        state["context"] = _refusal_message_for_language(language)
        return state

    short_term_memory = _format_short_term_memory(messages[:-1])
    long_term_memory = _load_long_term_memory(state["conversation_id"])
    vector_context = vector_retriever.invoke(user_query)

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
    web_results = (
        web_search.invoke(user_query) if needs_web_search else "Web search not needed."
    )

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

    if not state.get("is_health_query", False):
        return {
            "messages": [AIMessage(content=_refusal_message_for_language(language))]
        }

    system_prompt = (
        "You are a helpful, empathetic health chatbot for Ethiopian women. "
        "You must only answer health-related questions. "
        "If a user asks about non-health topics, refuse briefly and redirect them to ask a health question. "
        "Provide accurate, culturally relevant info on maternal health, obstetric fistula, and cancers. "
        "Use simple language, acknowledge emotions, and suggest local resources when appropriate. "
        "Use the provided short-term memory, long-term memory, knowledge retrieval, and web search context. "
        "Prefer the knowledge base for domain facts, and use web search only for current or time-sensitive information. "
        "Keep responses concise, supportive, and actionable. "
        "Language policy: detect the user's language and respond in the same language whenever possible. "
        "Supported languages: English, Amharic, Afaan Oromo, Tigrinya. "
        "If the user language is one of these, answer in that language. "
        "Always format the response in clean Markdown. "
        "Use a short opening sentence, then bullet points or numbered lists when helpful. "
        "Use short sections with Markdown headings only when they improve clarity. "
        "For Amharic, Afaan Oromo, and Tigrinya, use natural, fluent phrasing and avoid literal translation from English. "
        "Do not invent awkward category labels. "
        "If giving a list of tests, symptoms, or steps, use one item per bullet or number with a brief explanation. "
        "When the answer is uncertain or depends on a clinician, say so clearly and briefly. "
        "Use these style references as guidance only, not as fixed templates: "
        "English example: 'During pregnancy, these checkups are important:' followed by a numbered list with short explanations. "
        "Amharic example: 'በእርግዝና ወቅት እነዚህ ምርመራዎች አስፈላጊ ናቸው፦' followed by a natural numbered list. "
        "Afaan Oromo example: 'Yeroo ulfaa qorannoowwan armaan gadii barbaachisoo dha:' followed by a clear numbered list. "
        "Tigrinya example: 'ኣብ እዋን ጥንሲ እዞም ምርመራታት ኣገደስቲ እዮም፦' followed by a natural numbered list. "
        "For Amharic, avoid awkward phrases like 'መነሻ ገጽታ' unless the user explicitly asks for definitions. "
        "For Afaan Oromo, prefer common health wording such as 'qorannoo', 'mallattoo', 'yaala', and 'ittisa'. "
        "For Tigrinya, prefer clear everyday medical wording over overly literal translations. "
        "If the user asks for recommended tests during pregnancy, mention practical items like blood tests, urine tests, blood pressure checks, ultrasound, infection screening, and gestational diabetes screening when supported by context."
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
                "Treat the selected response language as authoritative when it is one of the supported languages.\n"
                "Only fall back to auto-detected language when no supported language was selected.\n"
                "Return a well-structured Markdown answer.\n"
                "If the query asks for multiple items, prefer a numbered list.\n"
                "If the response language is Amharic, Afaan Oromo, or Tigrinya, make the wording natural and locally understandable.\n"
                "Use concrete, medically relevant examples when appropriate instead of vague category labels.\n"
                "For multilingual answers, prioritize fluency, clarity, and usefulness over literal translation."
            )
        ),
    ]

    response = llm.invoke(messages)
    response_content = (
        response.content if isinstance(response.content, str) else str(response.content)
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
