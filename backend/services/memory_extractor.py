"""
Automated Memory Extraction and Storage for Rorak AI.

Automatically extracts durable user attributes (name, role, location),
user preferences (tech stack, formatting, favorite tools),
and user directives from user chat messages,
validating against sensitive information leakage and deduplicating
against existing memory entries.
"""
import json
import logging
import re
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.core.config import GROQ_API_KEY, GROQ_MODEL
from backend.models.db.memory import Memory
from backend.repositories.memory_repository import MemoryRepository
from backend.services.memory_service import detect_sensitive_information

logger = logging.getLogger(__name__)

# Trigger keywords indicating a user might be sharing durable info
MEMORY_TRIGGER_KEYWORDS = (
    "name is",
    "call me",
    "i am called",
    "i'm called",
    "i am a",
    "i'm a",
    "i work as",
    "i work in",
    "i live in",
    "i'm based in",
    "i am based in",
    "i'm from",
    "i am from",
    "my location is",
    "my timezone is",
    "i prefer",
    "my preference",
    "my favorite",
    "my favourite",
    "always format",
    "always use",
    "always write",
    "always explain",
    "never use",
    "never format",
    "remember that",
    "remember this",
    "keep in mind",
    "note that",
    "don't forget",
    "do not forget",
    "our project is",
    "the project name is",
    "our tech stack",
    "our stack is",
    "we use",
    "we are using",
)

# Common words to ignore when extracting roles or adjectives after "I am"
NON_ROLE_WORDS = {
    "a", "an", "the", "not", "just", "so", "very", "really", "happy",
    "glad", "sorry", "tired", "sad", "good", "fine", "ready", "here",
    "back", "done", "trying", "wondering", "asking", "thinking", "looking",
    "curious", "confused", "sure", "unsure", "new", "interested",
}


def has_memory_indicators(text: str) -> bool:
    """Fast check whether text might contain durable memory information."""
    if not text or len(text.strip()) < 5:
        return False
    lower_text = text.lower()
    if any(trigger in lower_text for trigger in MEMORY_TRIGGER_KEYWORDS):
        return True
    if re.search(r"\b(?:I['’]m|I am|i['’]m|i am)\s+[A-Z][a-zA-Z]{1,25}\b", text):
        return True
    return False


def extract_memories_heuristic(text: str) -> list[dict]:
    """
    Fast rule-based memory extraction using regex patterns.
    Zero-latency and completely offline.
    Returns list of dicts: {"content": str, "memory_type": str}
    """
    extracted = []
    clean_text = text.strip()

    # 1. Name / Identity Extraction
    name_match = re.search(
        r"\b(?:my name is|i am called|call me|i'm called)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})\b",
        clean_text,
        re.IGNORECASE,
    )
    if name_match:
        name = name_match.group(1).strip()
        if name.lower() not in {"a", "an", "the", "rorak", "user", "human", "assistant"}:
            extracted.append({
                "content": f"User's name is {name}",
                "memory_type": "fact",
            })

    # Short form "I am Alice" / "I'm Bob"
    if not any("name is" in item["content"].lower() for item in extracted):
        short_name_match = re.search(
            r"\b(?:I['’]m|I am)\s+([A-Z][a-z]{1,20})\b",
            clean_text,
        )
        if short_name_match:
            candidate = short_name_match.group(1).strip()
            if candidate.lower() not in NON_ROLE_WORDS:
                extracted.append({
                    "content": f"User's name is {candidate}",
                    "memory_type": "fact",
                })

    # 2. Profession / Role
    role_match = re.search(
        r"\b(?:i work as|i am a|i'm a)\s+(?:an?\s+)?([a-zA-Z0-9_\-\s]{3,40}?)(?:[.,;]|\band\b|$)",
        clean_text,
        re.IGNORECASE,
    )
    if role_match:
        role = role_match.group(1).strip()
        role_first_word = role.split()[0].lower() if role else ""
        if role and role_first_word not in NON_ROLE_WORDS and len(role.split()) <= 4:
            extracted.append({
                "content": f"User works as a {role}",
                "memory_type": "fact",
            })

    # 3. Location / Residence
    location_match = re.search(
        r"\b(?:i live in|i am based in|i'm based in|i'm from|i am from|my location is)\s+([A-Z][a-zA-Z\s,]{2,40}?)(?:[.;]|\band\b|$)",
        clean_text,
        re.IGNORECASE,
    )
    if location_match:
        location = location_match.group(1).strip()
        if location:
            extracted.append({
                "content": f"User is located in {location}",
                "memory_type": "fact",
            })

    # 4. User Preferences
    pref_match = re.search(
        r"\b(?:i prefer|my preference is|my favorite\s+\w+\s+is|my favourite\s+\w+\s+is)\s+(.+?)(?:[.;]|$)",
        clean_text,
        re.IGNORECASE,
    )
    if pref_match:
        pref = pref_match.group(1).strip()
        if pref and len(pref) < 150:
            extracted.append({
                "content": f"User prefers {pref}",
                "memory_type": "preference",
            })

    # 5. Directives (Always / Never)
    directive_match = re.search(
        r"\b((?:always|never)\s+(?:use|format|write|explain|include|provide)\s+.+?)(?:[.;]|$)",
        clean_text,
        re.IGNORECASE,
    )
    if directive_match:
        directive = directive_match.group(1).strip()
        if directive and len(directive) < 150:
            directive = directive[0].upper() + directive[1:]
            extracted.append({
                "content": directive,
                "memory_type": "directive",
            })

    # 6. Explicit Memory Requests
    remember_match = re.search(
        r"\b(?:please remember that|remember that|keep in mind that|note that|don't forget that|do not forget that)\s+(.+?)(?:[.;]|$)",
        clean_text,
        re.IGNORECASE,
    )
    if remember_match:
        fact = remember_match.group(1).strip()
        if fact and len(fact) > 5:
            fact = fact[0].upper() + fact[1:]
            extracted.append({
                "content": fact,
                "memory_type": "directive",
            })

    # 7. Project facts
    project_match = re.search(
        r"\b(?:our project is called|the project name is|our project is)\s+([a-zA-Z0-9_\-\s]{2,40}?)(?:[.,!?;]|$)",
        clean_text,
        re.IGNORECASE,
    )
    if project_match:
        p_name = project_match.group(1).strip()
        if p_name and p_name.lower() not in {"new", "big", "great", "ready", "open"}:
            extracted.append({
                "content": f"Project name is {p_name}",
                "memory_type": "fact",
            })

    return extracted


def extract_memories_llm(text: str) -> list[dict]:
    """
    Call Groq LLM to intelligently extract non-trivial durable facts or preferences.
    """
    if not GROQ_API_KEY:
        return []

    from groq import Groq
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = (
            "You are an expert AI memory extractor. "
            "Examine the user message below and extract durable facts, personal attributes, "
            "or persistent user preferences that should be remembered in future conversations.\n\n"
            "Rules:\n"
            "- Extract: Name, profession, location, tech preferences, project facts, explicit constraints.\n"
            "- Do NOT extract: transient questions, greetings, temporary tasks, or chit-chat.\n"
            "- Do NOT extract passwords, API keys, secrets, or financial information.\n"
            "- Output MUST be a strictly valid JSON array of objects with keys:\n"
            '  "content": clear, factual summary statement\n'
            '  "memory_type": "preference" | "fact" | "directive"\n'
            "- If no durable information is present, output: []\n\n"
            f'User message: "{text}"\n\n'
            "JSON:"
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            timeout=4.0,
        )

        content = response.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                valid = []
                for item in parsed:
                    if isinstance(item, dict) and "content" in item:
                        c = str(item["content"]).strip()
                        m_type = item.get("memory_type", "preference")
                        if c and len(c) <= 255:
                            valid.append({
                                "content": c,
                                "memory_type": m_type if m_type in {"preference", "fact", "directive"} else "preference",
                            })
                return valid
    except Exception as e:
        logger.debug("LLM memory extraction skipped or timed out: %s", e)

    return []


def extract_durable_memories(text: str) -> list[dict]:
    """
    Hybrid memory extraction pipeline:
    1. Gating check for trigger keywords.
    2. Fast heuristic extraction.
    3. LLM fallback if heuristic found nothing but strong memory cues were present.
    """
    if not has_memory_indicators(text):
        return []

    candidates = extract_memories_heuristic(text)
    if candidates:
        return candidates

    return extract_memories_llm(text)


def auto_extract_and_save_memories(
    db: Session,
    user_content: str,
    user_id: UUID,
    memory_repo: Optional[MemoryRepository] = None,
) -> list[Memory]:
    """
    Extracts durable memories from user_content, validates them,
    deduplicates against existing memories, and persists them into the database.
    Returns the list of newly created Memory instances.
    """
    if not user_content or not user_id:
        return []

    candidates = extract_durable_memories(user_content)
    if not candidates:
        return []

    repo = memory_repo or MemoryRepository(db)

    # Fetch existing memories for this user to prevent duplicates
    existing_memories = repo.list_scoped_memories(
        user_id=user_id,
        limit=100,
    )
    existing_contents = {m.content.lower().strip() for m in existing_memories}

    saved_memories = []

    for item in candidates:
        content = item.get("content", "").strip()
        if not content:
            continue

        # 1. Sensitive information filter
        sensitive_findings = detect_sensitive_information(content)
        if sensitive_findings:
            logger.warning(
                "Skipping auto-memory extraction due to sensitive content: %s",
                sensitive_findings,
            )
            continue

        # 2. Deduplication check
        if content.lower() in existing_contents:
            logger.debug("Memory already stored for user %s: '%s'", user_id, content)
            continue

        # 3. Create Memory record
        memory = Memory(
            id=uuid4(),
            user_id=user_id,
            content=content,
            memory_type=item.get("memory_type", "preference"),
        )
        try:
            repo.create(memory)
            db.commit()
            db.refresh(memory)
            saved_memories.append(memory)
            existing_contents.add(content.lower())
            logger.info(
                "Auto-saved memory for user %s: '%s' (type: %s)",
                user_id,
                content,
                memory.memory_type,
            )
        except Exception as e:
            db.rollback()
            logger.warning("Failed to auto-save memory '%s': %s", content, e)

    return saved_memories
