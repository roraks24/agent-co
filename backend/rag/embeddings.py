import logging
import time
from langchain_huggingface import HuggingFaceEmbeddings

from backend.core.config import EMBEDDING_MODEL


logger = logging.getLogger(__name__)

logger.info("Initializing HuggingFace embedding model (%s)...", EMBEDDING_MODEL)
_start_time = time.perf_counter()
embedding_model = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL
)
logger.info("HuggingFace embedding model loaded in %.2f seconds.", time.perf_counter() - _start_time)