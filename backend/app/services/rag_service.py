import re
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RAGService:
    """Grounded retrieval for uploaded study material."""

    def __init__(self):
        self.indexes: Dict[str, Dict[str, Any]] = {}

    def build_index(self, file_id: str, page_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create paragraph-aware chunks while preserving local context."""
        chunks: List[Dict[str, Any]] = []
        counter = 1
        section = "General Overview"

        for p_info in page_texts:
            page_num = p_info["page"]
            raw = (p_info.get("text") or "").replace("\r", "\n")
            lines = [re.sub(r"\s+", " ", x).strip() for x in raw.splitlines() if x.strip()]
            paragraphs: List[str] = []
            buf: List[str] = []

            for line in lines:
                # Preserve likely headings but do not depend on them for retrieval.
                if len(line) <= 100 and (
                    line.isupper()
                    or re.match(r"^(chapter|module|unit|section)\b", line, re.I)
                    or re.match(r"^\d+(?:\.\d+)*[.)]?\s+[A-Za-z]", line)
                ):
                    if buf:
                        paragraphs.append(" ".join(buf))
                        buf = []
                    section = line
                    paragraphs.append(line)
                else:
                    buf.append(line)

            if buf:
                paragraphs.append(" ".join(buf))

            # Build chunks from whole paragraphs. This prevents an answer from being
            # split in the middle of a definition/list merely because 600 chars elapsed.
            current: List[str] = []
            current_len = 0
            for paragraph in paragraphs:
                if not paragraph:
                    continue
                if current and current_len + len(paragraph) + 1 > 1100:
                    text = " ".join(current).strip()
                    if len(text) >= 40:
                        chunks.append({
                            "chunk_id": f"c-{page_num}-{counter}",
                            "page": page_num,
                            "section": section,
                            "text": text,
                        })
                        counter += 1
                    # Keep the last paragraph as local overlap.
                    current = current[-1:]
                    current_len = len(current[0]) if current else 0
                current.append(paragraph)
                current_len += len(paragraph) + 1

            if current:
                text = " ".join(current).strip()
                if len(text) >= 40:
                    chunks.append({
                        "chunk_id": f"c-{page_num}-{counter}",
                        "page": page_num,
                        "section": section,
                        "text": text,
                    })
                    counter += 1

        if not chunks:
            chunks = [{"chunk_id": "c-1-1", "page": 1, "section": "General Notes", "text": "No text content available."}]

        texts = [c["text"] for c in chunks]
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            stop_words="english",
            max_df=0.98,
        )
        try:
            matrix = vectorizer.fit_transform(texts)
        except Exception:
            vectorizer = TfidfVectorizer(ngram_range=(1, 1), stop_words=None)
            matrix = vectorizer.fit_transform(texts)

        self.indexes[file_id] = {"vectorizer": vectorizer, "matrix": matrix, "chunks": chunks}
        print(f"[RAGService] Indexed {len(chunks)} grounded chunks for {file_id}.")
        return chunks

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 2]

    @staticmethod
    def _expand_query_terms(tokens: List[str]) -> List[str]:
        # Generic academic expansions improve retrieval without hardcoding any subject.
        expansions = {
            "pipeline": ["steps", "stages", "process", "workflow"],
            "stage": ["stages", "steps", "process"],
            "stages": ["stage", "steps", "process"],
            "step": ["steps", "stage", "process"],
            "steps": ["step", "stages", "process"],
            "application": ["applications", "uses", "used"],
            "applications": ["application", "uses", "used"],
            "advantage": ["advantages", "benefits"],
            "advantages": ["advantage", "benefits"],
            "disadvantage": ["disadvantages", "limitations"],
            "disadvantages": ["disadvantage", "limitations"],
            "definition": ["define", "meaning"],
            "meaning": ["definition", "define"],
            "types": ["type", "categories", "classification"],
        }
        out = list(tokens)
        for token in tokens:
            out.extend(expansions.get(token, []))
        return list(dict.fromkeys(out))

    @staticmethod
    def _is_comparison_query(query: str) -> bool:
        q = query.lower()
        return bool(re.search(r"\b(difference|differences|differentiate|differentiate between|compare|comparison|versus|vs\.?|distinguish|distinction|similarities|similarity)\b", q))

    @staticmethod
    def _focus_tokens(query: str) -> List[str]:
        stop = {
            "what", "what's", "is", "are", "the", "a", "an", "how", "why", "where", "when",
            "which", "who", "tell", "me", "about", "explain", "define", "from", "notes", "pdf",
            "give", "show", "can", "could", "would", "should", "please", "and", "for", "with",
            "this", "that", "these", "those", "it", "its", "into", "your", "my", "point", "points",
            "view", "marks", "mark", "short", "brief", "long", "detailed", "detail", "simple", "simply",
        }
        return [t for t in RAGService._tokens(query) if t not in stop and not t.isdigit()]

    def resolve_query_intent(self, query: str, history: List[Dict[str, str]]) -> str:
        """Resolve short follow-ups without replacing the user's actual topic."""
        q = query.strip()
        if len(q.split()) <= 6 and history:
            lowered = q.lower()
            followup = bool(re.search(r"\b(it|its|this|that|they|them|these|those)\b", lowered))
            followup = followup or bool(re.search(r"\b(explain|example|simplify|shorter|expand|detail)\b", lowered))
            if followup:
                previous = [h.get("content", "") for h in reversed(history) if h.get("role") == "user"]
                for prev in previous[:3]:
                    if prev.strip():
                        return f"{prev.strip()} {q}"
        return q

    def search(
        self,
        file_id: str,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 8,
        min_threshold: float = 0.08,
    ) -> Tuple[List[Dict[str, Any]], str, bool]:
        if file_id not in self.indexes:
            return [], query, False

        data = self.indexes[file_id]
        chunks = data["chunks"]
        resolved = self.resolve_query_intent(query, history or [])
        vectorizer = data["vectorizer"]

        try:
            sims = cosine_similarity(vectorizer.transform([resolved]), data["matrix"]).flatten()
        except Exception:
            sims = np.zeros(len(chunks))

        stop = {
            "what", "what's", "is", "are", "the", "a", "an", "how", "why", "where", "when",
            "which", "who", "tell", "me", "about", "explain", "define", "from", "notes", "pdf",
            "give", "show", "can", "could", "would", "should", "please", "and", "for", "with",
            "this", "that", "these", "those", "it", "its", "into", "your", "my"
        }
        original_tokens = [t for t in self._tokens(resolved) if t not in stop]
        focus_tokens = self._focus_tokens(resolved)
        query_tokens = self._expand_query_terms(original_tokens)
        phrase = " ".join(original_tokens)
        focus_phrase = " ".join(focus_tokens)
        comparison_query = self._is_comparison_query(resolved)

        scored = []
        for i, chunk in enumerate(chunks):
            text = chunk["text"].lower()
            words = set(self._tokens(text))
            if query_tokens:
                exact = sum(1 for t in query_tokens if t in words) / len(query_tokens)
                stem = sum(1 for t in query_tokens if any(w.startswith(t[:5]) for w in words if len(t) >= 5)) / len(query_tokens)
                all_terms = 1.0 if original_tokens and all(t in words for t in original_tokens) else 0.0
            else:
                exact = stem = all_terms = 0.0

            focus_coverage = (sum(1 for t in focus_tokens if t in words) / len(focus_tokens)) if focus_tokens else 0.0
            focus_phrase_boost = 1.0 if focus_phrase and focus_phrase in text else 0.0
            phrase_boost = 1.0 if phrase and phrase in text else 0.0

            # If the student asks for one concept, comparison material is a weaker
            # match unless the student explicitly asks for a comparison. This prevents
            # a source passage titled "Differentiate X and Y" from turning a question
            # about X alone into an answer about X vs Y.
            comparison_penalty = 0.0
            if not comparison_query and re.search(r"\b(differentiate|difference|compare|comparison|versus|vs\.?)\b", text):
                comparison_penalty = 0.12

            score = (
                0.28 * float(sims[i])
                + 0.18 * exact
                + 0.08 * stem
                + 0.16 * all_terms
                + 0.12 * focus_coverage
                + 0.14 * focus_phrase_boost
                + 0.04 * phrase_boost
                - comparison_penalty
            )
            scored.append((max(score, 0.0), i, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored or scored[0][0] < min_threshold:
            return [], resolved, False

        selected_indices = {i for score, i, _chunk in scored[:top_k] if score > 0}
        # Add immediate neighbours of strong hits so definitions followed by their
        # explanation/examples are not separated by chunk boundaries.
        strong = [i for score, i, _ in scored[:top_k] if score >= max(scored[0][0] * 0.45, min_threshold)]
        for i in strong:
            if i > 0:
                selected_indices.add(i - 1)
            if i + 1 < len(chunks):
                selected_indices.add(i + 1)

        selected = []
        for i in selected_indices:
            score = next(s for s, idx, _ch in scored if idx == i)
            item = dict(chunks[i])
            item["_score"] = score
            selected.append(item)
        # Keep the strongest material first for the LLM while retaining neighbours.
        selected.sort(key=lambda c: c["_score"], reverse=True)
        return selected[: min(len(selected), 12)], resolved, True

    def get_document_chunks_sample(self, file_id: str, count: int = 10) -> List[Dict[str, Any]]:
        if file_id not in self.indexes:
            return []
        chunks = self.indexes[file_id]["chunks"]
        if len(chunks) <= count:
            return chunks
        indices = np.linspace(0, len(chunks) - 1, count, dtype=int)
        return [chunks[i] for i in indices]


rag_service = RAGService()
