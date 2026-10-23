"""
Document ingestion pipeline.

Rorak AI V2.5 Step 1: Format-agnostic ingestion engine consuming canonical ParsedDocument.
"""
import logging
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.core.config import CHUNK_OVERLAP, CHUNK_SIZE
from backend.parsers import (
    DocumentParser,
    ParsedDocument,
    ParserRegistry,
    UnsupportedFormatError,
    default_parser_registry,
)
from backend.parsers.adapters.pdf import PDFDocumentParser


logger = logging.getLogger(__name__)


def _extract_with_pypdf_reader(file_path: Path) -> List[Document]:
    """
    Backwards-compatibility fallback reader delegating to PDFDocumentParser.
    """
    adapter = PDFDocumentParser()
    blocks = adapter._extract_with_pypdf_reader(Path(file_path))
    return [b.to_langchain_document(source_filename=Path(file_path).name, source_type="pdf") for b in blocks]


def ingest_parsed_document(
    parsed_document: ParsedDocument,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Document]:
    """
    Consume a canonical ParsedDocument and split its structured blocks into indexable chunks.
    This function has zero knowledge of the underlying physical file format.
    """
    if not parsed_document.structured_blocks:
        logger.warning(
            "No structured blocks found in ParsedDocument for %s.",
            parsed_document.source_filename,
        )
        return []

    documents = parsed_document.to_langchain_documents()
    if not documents:
        logger.warning(
            "No non-empty text content in ParsedDocument for %s.",
            parsed_document.source_filename,
        )
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks = splitter.split_documents(documents)
    logger.info(
        "Successfully split %s (%d blocks) into %d chunks.",
        parsed_document.source_filename,
        len(documents),
        len(chunks),
    )

    return chunks


def ingest_func(
    file_path: Path | str,
    mime_type: Optional[str] = None,
    parser_registry: Optional[ParserRegistry] = None,
) -> List[Document]:
    """
    Canonical document ingestion entrypoint.
    Resolves the appropriate parser via the ParserRegistry, parses the source file
    into a canonical ParsedDocument, and consumes it through the format-agnostic chunker.
    """
    path_obj = Path(file_path)
    registry = parser_registry or default_parser_registry

    logger.debug("Ingesting document via registry: %s", path_obj.name)
    parsed_doc = registry.parse(path_obj, mime_type=mime_type)

    return ingest_parsed_document(parsed_doc)
