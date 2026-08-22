"""LLM-assisted natural language offer parser supporting Gemini & Anthropic with deterministic regex fallback."""

import os
import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a natural-language offer parser for an agentic commerce gateway.
Your job is to parse the buyer's natural language request and extract commercial parameters into JSON format:
{
  "product_id": string or null,
  "proposed_price_inr": integer or null,
  "quantity": integer or null,
  "terms": object with payment terms (e.g. {"payment": "net_30"}),
  "intent": "purchase" | "renew" | "refund" | "negotiate"
}
CRITICAL RULES:
- Do NOT negotiate, make commercial decisions, or change any terms.
- Output ONLY valid JSON, with no explanation or preamble."""


class LLMOfferParser:
    """Parses natural language buyer offers into structured parameters via Gemini / Anthropic LLM (with regex fallback)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        # If explicitly passed api_key, identify provider
        if api_key:
            if api_key.startswith("AQ.") or api_key.startswith("AIza"):
                self.gemini_api_key = api_key
            else:
                self.anthropic_api_key = api_key

        self.provider = provider or ("gemini" if self.gemini_api_key else ("anthropic" if self.anthropic_api_key else None))
        self.model = model

    def parse(self, raw_text: str, default_product_id: str = "pro_annual") -> Dict[str, Any]:
        """Parse natural language offer into structured dictionary."""
        if not raw_text or not raw_text.strip():
            return {}

        # 1. Try Gemini if configured
        if self.gemini_api_key and (self.provider == "gemini" or not self.anthropic_api_key):
            try:
                import requests
                model_name = self.model or "gemini-1.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": f"{EXTRACTION_SYSTEM_PROMPT}\n\nBuyer request: {raw_text}"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.0
                    }
                }
                resp = requests.post(url, json=payload, timeout=5.0)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        clean_json = re.search(r"\{.*\}", text_content, re.DOTALL)
                        if clean_json:
                            parsed = json.loads(clean_json.group(0))
                            return self._clean_parsed(parsed, default_product_id)
            except Exception as e:
                logger.warning(f"Gemini LLM parsing failed, falling back: {e}")

        # 2. Try Anthropic if configured
        if self.anthropic_api_key:
            try:
                import requests
                headers = {
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": self.model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 512,
                    "system": EXTRACTION_SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": f"Buyer request: {raw_text}"}
                    ]
                }
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=5.0
                )
                if resp.status_code == 200:
                    resp_json = resp.json()
                    content = resp_json.get("content", [{}])[0].get("text", "")
                    clean_json = re.search(r"\{.*\}", content, re.DOTALL)
                    if clean_json:
                        parsed = json.loads(clean_json.group(0))
                        return self._clean_parsed(parsed, default_product_id)
            except Exception as e:
                logger.warning(f"Anthropic LLM parsing failed, using deterministic regex fallback: {e}")

        # 3. Deterministic Regex / Heuristic Fallback (guarantees zero failure in live demos)
        return self._regex_fallback(raw_text, default_product_id)

    def _clean_parsed(self, parsed: Dict[str, Any], default_product_id: str) -> Dict[str, Any]:
        result = {}
        if parsed.get("product_id"):
            result["product_id"] = str(parsed["product_id"])
        if parsed.get("proposed_price_inr") is not None:
            try:
                result["proposed_price_inr"] = int(parsed["proposed_price_inr"])
            except (ValueError, TypeError):
                pass
        if parsed.get("quantity") is not None:
            try:
                result["quantity"] = int(parsed["quantity"])
            except (ValueError, TypeError):
                pass
        if isinstance(parsed.get("terms"), dict):
            result["terms"] = parsed["terms"]
        if parsed.get("intent") in ["purchase", "renew", "refund", "negotiate"]:
            result["intent"] = parsed["intent"]
        return result

    def _regex_fallback(self, text: str, default_product_id: str) -> Dict[str, Any]:
        """Deterministic extraction for common procurement phrases."""
        result: Dict[str, Any] = {"terms": {}}
        clean = text.lower()

        # Product matching
        if "pro" in clean:
            result["product_id"] = "pro_annual"
        elif "enterprise" in clean:
            result["product_id"] = "enterprise_custom"

        # Quantity matching: e.g. "50 seats", "10 units", "100 licenses", "qty: 5"
        qty_match = re.search(r"(\d+)\s*(seats?|units?|licenses?|instances?|qty)?", clean)
        if qty_match:
            try:
                result["quantity"] = int(qty_match.group(1))
            except ValueError:
                pass

        # Price matching: look for currency symbols or price indicators
        price_patterns = [
            r"(?:₹|rs\.?|inr)\s*([\d,]+)",
            r"([\d,]+)\s*(?:/seat|per seat|each)",
            r"(?:price|rate|at)\s*(?:is|of|:)?\s*(?:₹|rs\.?|inr)?\s*([\d,]+)",
            r"for\s*(?:₹|rs\.?|inr)?\s*([\d,]+)(?:\s*(?:/seat|each))?"
        ]
        for pattern in price_patterns:
            p_match = re.search(pattern, clean)
            if p_match:
                num_str = p_match.group(1).replace(",", "")
                if num_str.isdigit():
                    result["proposed_price_inr"] = int(num_str)
                    break

        # Terms matching
        if "net-30" in clean or "net 30" in clean:
            result["terms"]["payment"] = "net_30"
        elif "net-60" in clean or "net 60" in clean:
            result["terms"]["payment"] = "net_60"
        elif "net-90" in clean or "net 90" in clean:
            result["terms"]["payment"] = "net_90"
        elif "card" in clean or "credit" in clean:
            result["terms"]["payment"] = "card"

        if "unlimited refund" in clean:
            result["terms"]["unlimited_refunds"] = True
        if "zero liability" in clean:
            result["terms"]["zero_liability"] = True

        # Intent
        if "refund" in clean:
            result["intent"] = "refund"
        elif "renew" in clean:
            result["intent"] = "renew"
        else:
            result["intent"] = "purchase"

        return result
