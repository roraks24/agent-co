import logging
import time
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder

from backend.core.config import RERANKER_MODEL


logger = logging.getLogger(__name__)

# Initialize reranker cross-encoder once at module load
logger.info("Initializing CrossEncoder reranker model (%s)...", RERANKER_MODEL)
_start_time = time.perf_counter()
reranker = CrossEncoder(RERANKER_MODEL)
logger.info("CrossEncoder reranker loaded in %.2f seconds.", time.perf_counter() - _start_time)


def rerank_func(documents: list, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Rerank candidate documents against the query using CrossEncoder.
    """
    if not documents:
        logger.info("No documents provided for reranking.")
        return []

    pairs = [
        (query, document.page_content)
        for document in documents
    ]

    t0 = time.perf_counter()
    scores = reranker.predict(pairs)
    duration_ms = (time.perf_counter() - t0) * 1000

    ranked_documents = sorted(
        zip(documents, scores),
        key=lambda x: x[1],
        reverse=True
    )

    top_results = [
        {
            "document": doc,
            "score": float(score)
        }
        for doc, score in ranked_documents[:top_k]
    ]

    logger.info(
        "Reranked %d candidates to top %d in %.2f ms (top score: %.4f)",
        len(documents), len(top_results), duration_ms,
        top_results[0]["score"] if top_results else 0.0
    )

    return top_results