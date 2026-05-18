# TenaChat Research App Overview

TenaChat is an AI health information chatbot focused on Ethiopian women health.
It is designed as a research prototype for studying retrieval-augmented,
multilingual health information support in a low-resource and safety-sensitive
context.

---

## Research Motivation

Access to reliable women health information can be limited by language,
location, health literacy, and availability of trained professionals. TenaChat
explores whether a retrieval-augmented chatbot can provide concise, localized,
and safety-aware health information while refusing unrelated questions and
escalating emergency symptoms.

The app is not a diagnostic system. It is an information assistant that should
encourage professional care when a question is urgent, personalized, or not
supported by the knowledge base.

---

## Target Use Case

The intended user asks questions about Ethiopian women health topics such as:

- pregnancy and antenatal care
- postnatal care
- family planning
- maternal nutrition
- breast and cervical cancer
- HIV prevention and PMTCT
- obstetric fistula
- emergency warning signs

The app supports text chat and speech input. Image input is intentionally out of
scope in the current version.

---

## System Architecture

TenaChat has a web frontend and a Python backend:

| Layer | Technology | Role |
|---|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS | Chat interface, authentication UI, language selection, speech capture. |
| Backend API | FastAPI | Chat, speech transcription, text-to-speech, conversation APIs. |
| RAG orchestration | LangGraph, LangChain | Retrieval and generation workflow. |
| Knowledge index | FAISS | Local vector search over curated health documents. |
| Embeddings | OpenAI `text-embedding-3-large` | Multilingual semantic retrieval. |
| Text generation | OpenRouter primary model with Gemini 2.5 Flash fallback | Produces final grounded responses. |
| Speech | OpenAI transcription model | Converts user audio to text. |
| Persistence | Supabase | Authenticated users and conversation history. |
| Cache/session | Redis | Response caching and anonymous session support. |

The current user experience centers the chat interface on the main page and
keeps navigation minimal. Authenticated users see their name and a logout
control in the header.

---

## RAG Method

The knowledge base is built from local PDF and JSON resources under
`knowledge_base/`. The indexing pipeline extracts text, chunks the content,
embeds each chunk, and stores the vectors in FAISS.

At runtime, the backend:

1. Receives the user message and selected language.
2. Detects emergency red flags with deterministic triage rules.
3. Rejects clearly unrelated non-health prompts.
4. Retrieves relevant knowledge-base context from FAISS.
5. Optionally uses current-information search when configured.
6. Returns an insufficient-evidence message when no reliable context is found.
7. Sends retrieved context and the user question to the generation model.
8. Returns the answer, triage level, conversation id, and source metadata.

This design separates safety decisions from the generative model. Emergency
prompts are escalated before generation.

---

## Safety Design

TenaChat uses three main safety controls:

| Control | Purpose |
|---|---|
| Health-domain guard | Refuses unrelated prompts and redirects users to health topics. |
| Emergency triage | Detects red-flag symptoms and returns immediate emergency guidance. |
| Insufficient-evidence fallback | Avoids speculation when retrieval does not provide enough support. |

The assistant should not diagnose, prescribe medication, provide personalized
dosage instructions, or replace professional care. Emergency messages direct
users in Ethiopia to seek immediate help, including calling 911 or going to the
nearest health facility.

---

## Multilingual Design

The app supports English, Amharic, Afaan Oromo, and Tigrinya. The selected
language is passed from the frontend to the backend and treated as authoritative
when supported. The navigation title remains `TenaChat` in all languages to
preserve product identity.

The evaluation dataset includes multilingual prompts, but coverage should be
expanded before making strong claims about low-resource language quality.

---

## Evaluation Approach

The project includes a health evaluation dataset at
`evals/health_eval_dataset.json`. It covers:

- grounded health-information questions
- emergency safety prompts
- insufficient-context prompts
- out-of-scope prompts

The live evaluation runner at `evals/run_ragas_eval.py` executes the dataset
against the RAG pipeline and applies an LLM-as-judge rubric. The judge scores
behavior match, groundedness, safety, and language quality. Results are stored
under `evals/results/`.

This evaluation is appropriate for measuring whether the system follows its
intended behavior on representative prompts. It is not a substitute for clinical
expert review.

---

## Research Limitations

- The knowledge base is limited to the documents included in the local index.
- Retrieval quality depends on chunking, embedding quality, and FAISS similarity
  ranking.
- The dataset is small and should be expanded for statistically meaningful
  claims.
- LLM-as-judge evaluation can be inconsistent and should be complemented with
  human expert review.
- The assistant does not verify user identity, clinical history, pregnancy
  status, age, medications, or local facility availability.
- Speech transcription quality may vary by accent, background noise, and
  language.

---

## Ethical And Privacy Considerations

TenaChat should be presented as a health information support tool, not a medical
provider. Research use should make the following clear to participants:

- The app may be wrong or incomplete.
- Emergency symptoms require immediate professional help.
- Users should avoid entering unnecessary personal identifiers.
- Conversation history for authenticated users may be stored in Supabase.
- Evaluation results should not include personally identifying user data.

Any deployment beyond research demonstration should include medical expert
review, privacy review, stronger monitoring, and a larger safety evaluation.

---

## Suggested Research Framing

TenaChat can be described as:

> A multilingual retrieval-augmented health information chatbot for Ethiopian
> women health topics, combining a curated local knowledge base, deterministic
> safety triage, and LLM generation with source-aware fallback behavior.

Potential research questions include:

- How well does RAG support grounded health responses in a multilingual setting?
- How reliably can deterministic triage protect emergency health interactions?
- What are the limitations of LLM-as-judge evaluation for health chatbots?
- How does language coverage affect answer quality and safety behavior?
