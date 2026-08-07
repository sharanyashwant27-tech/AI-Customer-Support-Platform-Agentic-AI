"""Sentiment Agent — Happy, Neutral, Angry, Frustrated, Urgent."""

from __future__ import annotations

import re

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent

LEXICONS: dict[str, set[str]] = {
    "happy": {
        "thanks",
        "thank",
        "great",
        "love",
        "excellent",
        "happy",
        "awesome",
        "good",
        "helpful",
        "perfect",
        "appreciate",
    },
    "angry": {
        "angry",
        "furious",
        "outrageous",
        "unacceptable",
        "hate",
        "worst",
        "ridiculous",
        "scam",
    },
    "frustrated": {
        "frustrated",
        "annoying",
        "annoyed",
        "tired of",
        "fed up",
        "again",
        "still waiting",
        "useless",
        "terrible",
        "awful",
    },
    "urgent": {
        "urgent",
        "immediately",
        "asap",
        "right now",
        "emergency",
        "lawsuit",
        "lawyer",
        "today",
    },
}


class SentimentAnalysisAgent(BaseAgent):
    """Detects: Happy, Neutral, Angry, Frustrated, Urgent."""

    name = AgentName.SENTIMENT

    async def run(self, state: AgentState) -> AgentResult:
        text = (state.get("user_message") or "").lower()
        scores = {
            label: sum(1 for w in words if w in text) for label, words in LEXICONS.items()
        }

        # Priority: urgent > angry > frustrated > happy > neutral
        if scores["urgent"] > 0:
            sentiment, confidence = "urgent", min(0.95, 0.7 + scores["urgent"] * 0.1)
        elif scores["angry"] > 0:
            sentiment, confidence = "angry", min(0.95, 0.7 + scores["angry"] * 0.1)
        elif scores["frustrated"] > 0:
            sentiment, confidence = "frustrated", min(0.92, 0.65 + scores["frustrated"] * 0.1)
        elif scores["happy"] > 0:
            sentiment, confidence = "happy", min(0.9, 0.65 + scores["happy"] * 0.1)
        else:
            sentiment, confidence = "neutral", 0.6

        # Emphasizers
        if re.search(r"!{2,}|\b(never|worst|immediately)\b", text):
            confidence = min(0.98, confidence + 0.05)
            if sentiment == "neutral":
                sentiment = "frustrated"

        # Backward-compatible polarity for handoff heuristics
        polarity = {
            "happy": "positive",
            "neutral": "neutral",
            "angry": "negative",
            "frustrated": "negative",
            "urgent": "negative",
        }[sentiment]

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=sentiment,
            confidence=confidence,
            data={
                "sentiment": sentiment,
                "polarity": polarity,
                "urgent": sentiment == "urgent" or scores["urgent"] > 0,
                "scores": scores,
                "labels": ["happy", "neutral", "angry", "frustrated", "urgent"],
            },
        )
