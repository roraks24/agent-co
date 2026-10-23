import logging
import time
from typing import Optional

from groq import Groq

from backend.core.config import GROQ_API_KEY, GROQ_MODEL, RERANK_TOP_K
from backend.rag.prompts import general_prompt_func, prompt_func, stateful_prompt_func
from backend.services.reranker import rerank_func
from backend.services.retriever import context_func, retriev_func


logger = logging.getLogger(__name__)

# Fallback response for ungrounded queries
NO_CONTEXT_FALLBACK_ANSWER = "I couldn't find this information in the uploaded document."

# Initialize Groq client
client: Optional[Groq] = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
else:
    logger.warning("Groq client not initialized (GROQ_API_KEY is missing).")


def _call_groq_completion(prompt: str, custom_keys: Optional[dict] = None) -> Optional[str]:
    """Execute chat completion with dynamic support for custom API keys and providers."""
    import groq
    import openai

    active_client = client
    selected_model = GROQ_MODEL
    is_openai_compatible = False

    if isinstance(custom_keys, dict) and any(custom_keys.values()):
        provider = (custom_keys.get("provider") or "").lower().strip()
        custom_key = (
            custom_keys.get(f"{provider}_api_key")
            or custom_keys.get("api_key")
            or custom_keys.get("groq_api_key")
            or custom_keys.get("openai_api_key")
            or custom_keys.get("custom_api_key")
        )
        custom_base_url = custom_keys.get("base_url") or custom_keys.get("custom_base_url")
        custom_model = custom_keys.get("model") or custom_keys.get("custom_model")

        if provider in ("custom", "openai_compatible", "ollama", "openrouter", "deepseek", "local") or custom_base_url:
            is_openai_compatible = True
            active_client = openai.OpenAI(
                base_url=custom_base_url or "http://localhost:11434/v1",
                api_key=custom_key or "custom-key",
            )
            selected_model = custom_model or "default"
        elif provider == "openai" or (custom_key and custom_key.startswith("sk-") and not custom_key.startswith("gsk_")):
            is_openai_compatible = True
            active_client = openai.OpenAI(api_key=custom_key)
            selected_model = custom_model or "gpt-4o"
        elif custom_key:
            active_client = Groq(api_key=custom_key)
            selected_model = custom_model or GROQ_MODEL

    if active_client is None:
        raise RuntimeError("No AI API key configured. Provide a custom API key or set GROQ_API_KEY.")

    max_retries = 2
    backoff = 1.0

    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        logger.info("Calling LLM API (model: %s, attempt: %d)...", selected_model, attempt + 1)
        try:
            response = active_client.chat.completions.create(
                model=selected_model,
                temperature=0.2,
                timeout=30.0,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info("LLM API call completed in %.2f ms", duration_ms)

            if not response.choices or not response.choices[0].message:
                return None

            return response.choices[0].message.content

        except Exception as e:
            err_type = type(e).__name__
            if attempt < max_retries and any(t in err_type.lower() for t in ("rate", "timeout", "server")):
                logger.warning("LLM transient error (%s). Retrying in %.1fs...", err_type, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("LLM API failed after %d attempts: %s", attempt + 1, e)
                raise RuntimeError(f"AI provider error: {e}")


def chat_func(
    query: str,
    conversation_history: Optional[list] = None,
    memory_context: Optional[list] = None,
    conversation_id: Optional[object] = None,
    user_id: Optional[object] = None,
    custom_keys: Optional[dict] = None,
    **kwargs,
) -> str:
    """
    Execute AI generation with stateful context assembly:
    1. Retrieve and rerank document context from vector store (conversation/user-scoped).
    2. Incorporate bounded conversation history and durable memories when provided.
    3. Separate system instructions, memory, history, context, and query.
    4. Call LLM (using server or user-inputted custom key) with retry on empty response.
    """
    if not GROQ_API_KEY and not custom_keys:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Please add a custom key or configure GROQ_API_KEY in the backend environment."
        )

    t_total_start = time.perf_counter()

    # Step 1: Retrieval
    t0 = time.perf_counter()
    try:
        user_str = str(user_id) if user_id else None
        conv_str = str(conversation_id) if conversation_id else None
        results = retriev_func(query, user_id=user_str, conversation_id=conv_str)
    except Exception:
        logger.exception("Retrieval failed for query (length %d chars)", len(query))
        results = []
    t_retrieval_ms = (time.perf_counter() - t0) * 1000

    # Step 2: Extract document context if grounded
    context = None
    t_rerank_ms = 0.0
    if results:
        t0 = time.perf_counter()
        try:
            reranked_results = rerank_func(
                results,
                query,
                top_k=RERANK_TOP_K
            )
            reranked_documents = [item["document"] for item in reranked_results]
            context = context_func(reranked_documents)
        except Exception:
            logger.exception("Reranking failed. Falling back to raw retrieval results.")
            reranked_documents = results[:RERANK_TOP_K]
            context = context_func(reranked_documents)
        t_rerank_ms = (time.perf_counter() - t0) * 1000

    # Step 3: Format conversation history and memory if provided
    formatted_history = None
    if conversation_history:
        formatted_history = []
        for turn in conversation_history:
            if isinstance(turn, dict):
                formatted_history.append(turn)
            else:
                formatted_history.append({
                    "role": getattr(turn, "role", "user"),
                    "content": getattr(turn, "content", str(turn)),
                })

    formatted_memories = None
    if memory_context:
        formatted_memories = []
        for mem in memory_context:
            if isinstance(mem, str):
                formatted_memories.append(mem)
            else:
                formatted_memories.append(getattr(mem, "content", str(mem)))

    # Step 4: Prompt assembly
    if formatted_history or formatted_memories:
        # Stateful Chat Context Assembly (V2.3)
        prompt = stateful_prompt_func(
            query=query,
            context=context,
            history=formatted_history,
            memories=formatted_memories,
        )
    elif context and context.strip():
        # Document-grounded single query prompt
        prompt = prompt_func(query, context)
    else:
        # General Assistant mode
        prompt = general_prompt_func(query)

    # Step 5: LLM Generation with 1 retry on empty response
    answer = None
    try:
        raw_answer = _call_groq_completion(prompt, custom_keys=custom_keys)
        if raw_answer and raw_answer.strip():
            answer = raw_answer.strip()
        else:
            logger.warning("LLM returned empty content on first attempt. Retrying once...")
            time.sleep(0.5)
            retry_raw = _call_groq_completion(prompt, custom_keys=custom_keys)
            if retry_raw and retry_raw.strip():
                answer = retry_raw.strip()
                logger.info("LLM retry succeeded with valid content.")
            else:
                logger.error("LLM returned empty content after retry.")
                raise RuntimeError("LLM returned an empty response. Please try again.")

    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        logger.exception("Groq API request failed.")
        raise RuntimeError("Failed to generate response from AI provider. Please try again.")

    total_duration_ms = (time.perf_counter() - t_total_start) * 1000
    llm_duration_ms = max(0.0, total_duration_ms - t_retrieval_ms - t_rerank_ms)
    logger.info(
        "Chat request completed in %.2f ms (Retrieval: %.2f ms, Rerank: %.2f ms, LLM: %.2f ms)",
        total_duration_ms, t_retrieval_ms, t_rerank_ms, llm_duration_ms
    )

    return answer
