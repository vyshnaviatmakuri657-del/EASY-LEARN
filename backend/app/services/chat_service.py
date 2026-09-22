from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
import re

from app.services.pdf_service import pdf_service
from app.services.ai_service import ai_service
from app.services.rag_service import rag_service


class ChatService:
    """Conversational study assistant with strict document grounding."""

    COMMON_CHAT = {
        "hi": "Hi! 👋 What are we learning today?",
        "hello": "Hello! 👋 What can I help you learn today?",
        "hey": "Hey! 👋 What would you like to study?",
        "good morning": "Good morning! ☀️ Ready to learn something new?",
        "good afternoon": "Good afternoon! What are we studying today?",
        "good evening": "Good evening! 🌙 What would you like to learn?",
        "thanks": "You're welcome! 😊",
        "thank you": "You're welcome! 😊",
        "bye": "Bye! 👋 Good luck with your studies!",
    }

    def _common_reply(self, message: str) -> Optional[str]:
        q = re.sub(r"[^a-z0-9 ]", "", message.lower()).strip()
        if q in self.COMMON_CHAT:
            return self.COMMON_CHAT[q]
        if re.search(r"\b(what|tell me)\b.*\b(time|current time)\b|\btime\s*now\b", q):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return f"The current time is **{now.strftime('%I:%M %p')}** (IST)."
        if re.search(r"\bwhat\b.*\b(day|today)\b|\bwhich day\b", q):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return f"Today is **{now.strftime('%A')}**."
        if re.search(r"\b(what is|what's|tell me)\b.*\b(date|today's date)\b", q):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return f"Today's date is **{now.strftime('%d %B %Y')}**."
        if re.search(r"\b(what can you do|what do you do|how can you help|your capabilities)\b", q):
            return ("I can chat normally, explain study concepts, use your uploaded PDF as study context, "
                    "turn an answer into 2-mark, 5-mark, or 10-mark exam format, simplify or expand explanations, "
                    "give examples, and continue the topic across follow-up questions.")
        return None

    def _answer_mode(self, message: str) -> str:
        q = message.lower()
        if re.search(r"\b(10|ten)\s*[- ]?marks?\b|\b(long|detailed|elaborate|comprehensive)\b", q):
            return "10-mark"
        if re.search(r"\b(5|five)\s*[- ]?marks?\b|\b(medium|explain in detail)\b", q):
            return "5-mark"
        if re.search(r"\b(2|two)\s*[- ]?marks?\b|\b(short|brief|in one or two lines)\b", q):
            return "2-mark"
        return "normal"

    def _topic_from_history(self, message: str, history: List[Dict[str, str]]) -> str:
        if self._answer_mode(message) != "normal":
            for item in reversed(history):
                if item.get("role") == "user":
                    previous = item.get("content", "").strip()
                    if previous and self._answer_mode(previous) == "normal":
                        return previous
        return message.strip()

    def _format_instruction(self, mode: str) -> str:
        if mode == "2-mark":
            return "Write a concise exam-ready answer: a direct definition/answer plus one important supporting point. Do not add unsupported examples."
        if mode == "5-mark":
            return "Write a medium exam-ready answer with a short introduction and 3-5 clear points or headings. Include examples only when the material supports them."
        if mode == "10-mark":
            return "Write a complete 10-mark exam answer with an introduction, logically ordered headings/points, detailed explanation, relevant examples/applications only when supported, and a conclusion when supported. Do not pad the answer with generic facts."
        return "Write a clear, natural explanation at the depth requested by the user."

    def _clean_answer(self, answer: str) -> str:
        if not answer:
            return answer
        text = answer.replace("\r\n", "\n").strip()
        text = re.split(r"\n\s*(?:\*\*?Sources?\*\*?|Sources?|References?|Citations?)\s*:?.*\n", text, flags=re.I)[0]
        text = re.sub(r"^\s*(?:Based on .*?|According to .*?)\s*:\s*", "", text, flags=re.I)
        text = re.sub(r"\[?\s*Page\s*\d+[^\]]*\]?", "", text, flags=re.I)
        text = re.sub(r"\bPage\s*\d+\b", "", text, flags=re.I)
        text = re.sub(r"\bSection\s*:?[^\n]+", "", text, flags=re.I)
        lines = []
        for line in text.split("\n"):
            if re.match(r"^\s*[-*•]?\s*(?:📄\s*)?Page\s*\d+\b", line, flags=re.I):
                continue
            if re.match(r"^\s*(?:Sources?|References?|Citations?)\s*:??\s*$", line, flags=re.I):
                continue
            lines.append(line.rstrip())
        text = "\n".join(lines)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    async def _generate_general(self, message: str, history: List[Dict[str, str]], mode: str) -> Dict[str, Any]:
        history_text = "\n".join(f"{h.get('role', 'user').upper()}: {h.get('content', '')}" for h in history[-8:])
        system = (
            "You are EASY-LEARN, a friendly AI study assistant. Handle normal conversation naturally and "
            "answer questions for any subject. Preserve conversation context. " + self._format_instruction(mode) + " "
            "If the user asks to shorten, simplify, expand, or change marks, transform the previous topic/answer."
        )
        prompt = f"CONVERSATION HISTORY:\n{history_text or '(none)'}\n\nUSER MESSAGE:\n{message}\n\nReturn JSON with exactly these keys: {{\"reply\": \"answer\", \"suggested_followups\": [\"...\", \"...\"]}}"
        ai_res = await ai_service.generate_json(prompt, system_prompt=system)
        if ai_res and ai_res.get("reply"):
            return {"reply": self._clean_answer(ai_res["reply"]), "sources": [], "suggested_followups": ai_res.get("suggested_followups", [])}
        return {
            "reply": "I can answer general questions, but accurate AI-generated explanations require an AI API key in the backend settings.",
            "sources": [],
            "suggested_followups": ["Explain it simply", "Give an example", "Give a 2-mark answer"]
        }

    @staticmethod
    def _question_focus(message: str, resolved_query: str) -> str:
        q = resolved_query.strip() or message.strip()
        q = re.sub(r"\b(explain|define|describe|tell me about|what is|what are|how does|how do|give me|please|in \d+ marks?|\d+ marks?|point of view|short|brief|detailed|long)\b", " ", q, flags=re.I)
        q = re.sub(r"\s+", " ", q).strip(" ?.!,-")
        return q or message.strip()

    @staticmethod
    def _is_comparison_request(message: str) -> bool:
        return bool(re.search(r"\b(difference|differences|differentiate|compare|comparison|versus|vs\.?|distinguish|distinction)\b", message.lower()))

    def _build_grounded_prompt(self, message: str, mode: str, resolved_query: str, history: List[Dict[str, str]], chunks: List[Dict[str, Any]]) -> str:
        # Only study text is sent; metadata such as page numbers is excluded.
        context = "\n\n".join(f"STUDY PASSAGE {i + 1}:\n{c['text']}" for i, c in enumerate(chunks))
        history_text = "\n".join(f"{h.get('role', 'user').upper()}: {h.get('content', '')}" for h in history[-8:])
        focus = self._question_focus(message, resolved_query)
        comparison = self._is_comparison_request(message)
        scope_rule = (
            "The user explicitly requested a comparison, so compare only the concepts named in the question."
            if comparison else
            "The user asked about ONE concept only. Answer that concept only. Do NOT turn the answer into a comparison with another concept merely because the study material discusses both nearby. Do not copy or answer a different question that appears in the study material."
        )
        return f"""CONVERSATION HISTORY:\n{history_text or '(none)'}\n\nUSER QUESTION:\n{message}\n\nPRIMARY QUESTION FOCUS:\n{focus}\n\nRESOLVED TOPIC:\n{resolved_query}\n\nSTUDY MATERIAL:\n{context}\n\nTASK:\n{self._format_instruction(mode)}\n\nQUESTION SCOPE RULE:\n{scope_rule}\n\nGROUNDING RULES:
1. The STUDY MATERIAL is the authority for document-based facts.
2. Use only facts, terminology, definitions, steps, examples and relationships supported by the STUDY MATERIAL.
3. Combine passages only when they are relevant to the PRIMARY QUESTION FOCUS.
4. Never answer a different question just because that question appears inside the study material.
5. Do not invent missing details or fill gaps with generic textbook knowledge.
6. If the material does not contain enough information for a requested claim, explicitly say so.
7. Do not mention retrieval, passages, pages, sections, sources, or context.
8. Answer the student's actual question directly.

Return JSON with exactly: {{"reply": "complete answer", "suggested_followups": ["...", "..."]}}"""

    async def _verify_answer(self, draft: str, question: str, chunks: List[Dict[str, Any]], mode: str) -> str:
        """Second-pass factual check. It removes unsupported claims before the answer reaches the student."""
        context = "\n\n".join(c["text"] for c in chunks)
        system = (
            "You are a strict academic fact checker. Revise the draft so every factual statement is supported "
            "by the supplied study material. Preserve the student's requested answer length and useful structure. "
            "Remove unsupported claims rather than replacing them with outside knowledge. If an essential part is "
            "not supported, state that the material does not provide enough information. Never mention pages, "
            "sources, retrieval, or this verification process. Return only valid JSON."
        )
        comparison = self._is_comparison_request(question)
        scope = (
            "Keep the requested comparison limited to the named concepts."
            if comparison else
            "The question asks for one concept. Remove discussion of unrelated or contrasting concepts unless strictly necessary to explain that concept."
        )
        prompt = f"QUESTION: {question}\n\nREQUESTED FORMAT: {mode}\n\nSCOPE RULE: {scope}\n\nSTUDY MATERIAL:\n{context}\n\nDRAFT ANSWER:\n{draft}\n\nReturn JSON: {{\"reply\": \"verified answer\"}}"
        checked = await ai_service.generate_json(prompt, system_prompt=system)
        return self._clean_answer(checked.get("reply", draft)) if checked and checked.get("reply") else self._clean_answer(draft)

    @staticmethod
    def _clean_source_sentence(sentence: str) -> str:
        """Remove source-only question/metadata lines without changing factual content."""
        s = re.sub(r"\s+", " ", sentence.replace("\n", " ")).strip(" -•")
        if not s:
            return ""
        # Do not let exam-question headings from the PDF become the student's answer.
        question_like = re.match(
            r"^(?:what|why|how|when|where|which|who|explain|describe|define|discuss|differentiate|compare|list|state|mention|give)\b",
            s,
            re.I,
        )
        if s.endswith("?") or question_like:
            return ""
        # Remove obvious document labels, while keeping ordinary academic prose.
        if re.match(r"^(?:question|q\.?\s*\d+|answer|unit|chapter|section)\b", s, re.I):
            return ""
        return s

    def _extractive_fallback(self, query: str, chunks: List[Dict[str, Any]], mode: str) -> str:
        """Create a faithful answer from retrieved study text when no LLM is configured.

        It never invents facts. It removes source question headings and organizes the
        remaining source-supported sentences into an exam-friendly response.
        """
        if not chunks:
            return "The uploaded material does not contain enough information to answer this question accurately."

        focus_words = [
            w.lower() for w in re.findall(r"[A-Za-z0-9]+", query)
            if len(w) > 2 and w.lower() not in {
                "what", "what's", "is", "are", "the", "a", "an", "how", "why", "where", "when",
                "which", "who", "tell", "me", "about", "explain", "define", "describe", "discuss",
                "give", "please", "marks", "mark", "short", "brief", "long", "detailed", "simply",
            }
        ]

        candidates = []
        seen = set()
        for chunk in chunks:
            # A chunk can contain several textbook blocks. Split them before scoring.
            raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", chunk.get("text", ""))
            for raw in raw_sentences:
                s = self._clean_source_sentence(raw)
                if len(s) < 35 or len(s) > 500:
                    continue
                low = s.lower()
                if re.search(r"\b(page|figure|fig\.?|table)\s*\d+", low):
                    continue
                key = re.sub(r"\W+", " ", low).strip()
                if not key or key in seen:
                    continue
                seen.add(key)

                overlap = sum(1 for w in focus_words if re.search(rf"\b{re.escape(w)}\b", low))
                # Prefer sentences that actually discuss the requested concept.
                score = overlap / max(len(focus_words), 1)
                candidates.append((score, chunk.get("_score", 0.0), s))

        if not candidates:
            return "The uploaded material does not contain enough information to answer this question accurately."

        # Preserve source order for coherent reading, but prioritize concept-relevant text.
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if focus_words:
            relevant = [c for c in candidates if c[0] > 0]
            if relevant:
                candidates = relevant

        # Re-rank by source relevance first, then keep unique sentences.
        candidates.sort(key=lambda x: x[1], reverse=True)
        limit = {"2-mark": 2, "5-mark": 7, "10-mark": 14, "normal": 7}[mode]
        selected = [c[2] for c in candidates[:limit]]

        if mode == "2-mark":
            return " ".join(selected[:2])

        if mode in {"5-mark", "10-mark"}:
            return "\n\n".join(f"• {s}" for s in selected)

        return "\n\n".join(selected)

    async def process_chat(self, file_id: Optional[str], message: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        message = message.strip()
        if not message:
            return {"reply": "Tell me what you'd like to learn. 😊", "sources": [], "suggested_followups": []}

        common = self._common_reply(message)
        if common:
            return {"reply": common, "sources": [], "suggested_followups": []}

        mode = self._answer_mode(message)
        resolved_topic = self._topic_from_history(message, history)

        if not file_id:
            return await self._generate_general(message, history, mode)

        doc = pdf_service.get_document(file_id)
        if file_id not in rag_service.indexes:
            rag_service.build_index(file_id, doc.get("page_texts", []))

        relevant, resolved_query, found = rag_service.search(
            file_id=file_id,
            query=resolved_topic if mode != "normal" else message,
            history=history,
            top_k=8,
            min_threshold=0.08,
        )

        if not found or not relevant:
            return {
                "reply": "The uploaded material does not contain enough information to answer this question accurately.",
                "sources": [],
                "suggested_followups": ["Ask about a topic in the document", "Explain the previous topic simply"]
            }

        prompt = self._build_grounded_prompt(message, mode, resolved_query, history, relevant)
        system = (
            "You are EASY-LEARN, a highly reliable academic study assistant. "
            "Produce an accurate student-supporting answer strictly grounded in the supplied study material. "
            "Never invent or embellish facts. Do not output page numbers, source lists, retrieval labels, or metadata."
        )
        ai_res = await ai_service.generate_json(prompt, system_prompt=system)
        if ai_res and ai_res.get("reply"):
            draft = self._clean_answer(ai_res["reply"])
            # A second pass is used only when an AI provider is configured.
            verified = await self._verify_answer(draft, message, relevant, mode)
            return {
                "reply": verified,
                "sources": [],
                "suggested_followups": ai_res.get("suggested_followups", ["Explain this simply", "Give a 2-mark answer", "Expand to 10 marks"])
            }

        return {
            "reply": self._extractive_fallback(resolved_query, relevant, mode),
            "sources": [],
            "suggested_followups": ["Explain this simply", "Give a 2-mark answer", "Expand to 10 marks"]
        }


chat_service = ChatService()
