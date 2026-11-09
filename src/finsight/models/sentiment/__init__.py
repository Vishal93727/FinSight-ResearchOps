"""Transparent lexicon financial sentiment baseline (not a pretrained language model)."""
from __future__ import annotations
import re

POSITIVE = {"beat", "beats", "growth", "grew", "profit", "profitable", "strong", "upgrade",
            "upgraded", "bullish", "outperform", "record", "surge", "positive", "improve", "improved"}
NEGATIVE = {"miss", "missed", "loss", "losses", "decline", "declined", "weak", "downgrade",
            "downgraded", "bearish", "underperform", "lawsuit", "default", "negative", "risk", "cut"}
NEGATIONS = {"not", "no", "never", "without", "neither"}


def score_financial_sentiment(text: str) -> dict:
    tokens = re.findall(r"[a-z]+", text.lower())
    positive = negative = 0
    for index, token in enumerate(tokens):
        negated = any(word in NEGATIONS for word in tokens[max(0, index - 3):index])
        if token in POSITIVE:
            if negated: negative += 1
            else: positive += 1
        elif token in NEGATIVE:
            if negated: positive += 1
            else: negative += 1
    total = positive + negative
    score = (positive - negative) / total if total else 0.0
    label = "POSITIVE" if score > 0.15 else "NEGATIVE" if score < -0.15 else "NEUTRAL"
    return {"label": label, "score": round(score, 6), "positive_terms": positive,
            "negative_terms": negative, "token_count": len(tokens),
            "method": "transparent_lexicon_v1", "pretrained_model": False}


from functools import lru_cache
from typing import Any


@lru_cache(maxsize=2)
def _load_finbert(model_name: str):
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("FinBERT requires the optional 'finbert' extra") from exc
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=False)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, trust_remote_code=False)
        model.eval()
        return tokenizer, model
    except Exception as exc:
        raise RuntimeError(f"Could not load FinBERT model {model_name!r}; cache its weights before use") from exc


def score_finbert_sentiment(text: str, model_name: str = "ProsusAI/finbert",
                            tokenizer: Any | None = None, model: Any | None = None) -> dict:
    """Score financial text with FinBERT; model downloads are lazy and never implicit fallback."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Sentiment text cannot be empty")
    if len(cleaned) > 20_000:
        raise ValueError("FinBERT input is limited to 20,000 characters")
    if tokenizer is None or model is None:
        tokenizer, model = _load_finbert(model_name)
    try:
        import torch
        encoded = tokenizer(cleaned, return_tensors="pt", truncation=True, max_length=512)
        with torch.inference_mode():
            logits = model(**encoded).logits[0]
            probabilities = torch.softmax(logits, dim=-1).cpu().tolist()
        raw_labels = model.config.id2label
        labels = {str(key).lower(): str(value).lower() for key, value in raw_labels.items()}
        class_probabilities = {labels.get(str(index), f"label_{index}"): round(float(value), 8)
            for index, value in enumerate(probabilities)}
        if not {"positive", "negative", "neutral"}.issubset(class_probabilities):
            raise ValueError("Configured model does not expose FinBERT positive/negative/neutral classes")
        label = max(class_probabilities, key=class_probabilities.get)
        return {"label": label.upper(), "score": round(class_probabilities["positive"] - class_probabilities["negative"], 8),
                "probabilities": class_probabilities, "method": "finbert_pretrained_v1",
                "model_name": model_name, "pretrained_model": True}
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError("FinBERT inference failed") from exc
