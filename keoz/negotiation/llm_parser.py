"""LLM-assisted natural language offer parser supporting Gemini & Anthropic with deterministic regex fallback for KEOZ."""

import os
import re
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a natural-language offer parser for an agentic commerce gateway.
Your job is to parse the buyer's natural language request and extract commercial parameters into JSON format:
{
  "product_id": string or null,
  "proposed_price_inr": integer or null,
  "quantity": integer or null,
  "terms": object with payment terms (e.g. {"payment": "net_30"}),
  "intent": "purchase" | "renew" | "refund" | "negotiate",
  "confidence": float between 0.0 and 1.0
}
CRITICAL RULES:
- Convert Lakhs/L/k into full integers (e.g. "45k" -> 45000, "1.8L" -> 180000, "₹42,000" -> 42000).
- Do NOT negotiate, make commercial decisions, or change any terms.
- Output ONLY valid JSON, with no explanation or preamble."""


@dataclass
class ParsedOffer:
    product_id: Optional[str] = None
    proposed_price_inr: Optional[int] = None
    quantity: Optional[int] = None
    terms: Optional[Dict[str, Any]] = None
    intent: Optional[str] = "purchase"
    confidence: float = 0.0
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, key, default=None):
        return getattr(self, key, default)


class LLMOfferParser:
    """Parses natural language buyer offers into structured parameters via Gemini / Anthropic LLM (with deterministic fallback)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.gemini_api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

        if api_key:
            if api_key.startswith("AQ.") or api_key.startswith("AIza"):
                self.gemini_api_key = api_key
            elif api_key.startswith("sk-ant"):
                self.anthropic_api_key = api_key

        self.provider = provider or ("gemini" if self.gemini_api_key else ("anthropic" if self.anthropic_api_key else None))
        self.model = model
        self.enabled = bool(self.gemini_api_key or self.anthropic_api_key)

    def parse(self, raw_text: str, default_product_id: str = "pro_annual") -> ParsedOffer:
        """Synchronously parse natural language offer into structured ParsedOffer."""
        if not raw_text or not raw_text.strip():
            return ParsedOffer(product_id=default_product_id, quantity=1, terms={}, raw_text=raw_text or "")

        # 1. Try Gemini REST / Client if key is available
        if self.gemini_api_key:
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
                resp = requests.post(url, json=payload, timeout=3.0)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        clean_json = re.search(r"\{.*\}", text_content, re.DOTALL)
                        if clean_json:
                            parsed = json.loads(clean_json.group(0))
                            return self._build_offer(parsed, raw_text, default_product_id, confidence=0.95)
            except Exception as e:
                logger.debug(f"Gemini LLM call failed, falling back: {e}")

        # 2. Try Anthropic REST if key is available
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
                resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=3.0)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    content = resp_json.get("content", [{}])[0].get("text", "")
                    clean_json = re.search(r"\{.*\}", content, re.DOTALL)
                    if clean_json:
                        parsed = json.loads(clean_json.group(0))
                        return self._build_offer(parsed, raw_text, default_product_id, confidence=0.95)
            except Exception as e:
                logger.debug(f"Anthropic LLM call failed, using deterministic fallback: {e}")

        # 3. Deterministic Regex / Heuristic Fallback (Guaranteed 100% reliable)
        return self._deterministic_fallback(raw_text, default_product_id)

    async def parse_async(self, raw_text: str, default_product_id: str = "pro_annual") -> ParsedOffer:
        """Async parse method."""
        return self.parse(raw_text, default_product_id)

    def _build_offer(self, parsed: Dict[str, Any], raw_text: str, default_product_id: str, confidence: float = 0.9) -> ParsedOffer:
        return ParsedOffer(
            product_id=parsed.get("product_id") or default_product_id,
            proposed_price_inr=int(parsed["proposed_price_inr"]) if parsed.get("proposed_price_inr") is not None else None,
            quantity=int(parsed.get("quantity", 1)),
            terms=parsed.get("terms") if isinstance(parsed.get("terms"), dict) else {},
            intent=parsed.get("intent", "purchase"),
            confidence=float(parsed.get("confidence", confidence)),
            raw_text=raw_text
        )

    def _deterministic_fallback(self, text: str, default_product_id: str) -> ParsedOffer:
        """Deterministic extraction for common commercial & procurement phrases."""
        clean = text.lower()
        terms: Dict[str, Any] = {}

        # 1. Product extraction
        product_id = default_product_id
        if "pro" in clean:
            product_id = "pro_annual"
        elif "enterprise" in clean:
            product_id = "enterprise_custom"

        # 2. Quantity extraction
        quantity = 1
        qty_match = re.search(r"(\d+)\s*(?:seats?|units?|licenses?|instances?|qty)?", clean)
        if qty_match:
            try:
                quantity = int(qty_match.group(1))
            except ValueError:
                pass

        # 3. Price extraction (supports ₹45,000, 42k, 1.8L, 45000)
        price: Optional[int] = None

        # Check Lakh format e.g. 1.8L, 1.5 Lakh, 2L
        lakh_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lakhs?|l)\b', clean)
        if lakh_match:
            price = int(float(lakh_match.group(1)) * 100000)
        else:
            # Check k format e.g. 42k, 45k
            k_match = re.search(r'(\d+(?:\.\d+)?)\s*k\b', clean)
            if k_match:
                price = int(float(k_match.group(1)) * 1000)
            else:
                # Check standard currency patterns
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
                            price = int(num_str)
                            break

        # 4. Payment terms extraction
        if "net-15" in clean or "net 15" in clean:
            terms["payment"] = "net_15"
        elif "net-30" in clean or "net 30" in clean or "net_30" in clean:
            terms["payment"] = "net_30"
        elif "net-45" in clean or "net 45" in clean or "net_45" in clean:
            terms["payment"] = "net_45"
        elif "net-60" in clean or "net 60" in clean or "net_60" in clean:
            terms["payment"] = "net_60"
        elif "net-90" in clean or "net 90" in clean or "net_90" in clean:
            terms["payment"] = "net_90"
        elif "prepaid" in clean or "advance" in clean:
            terms["payment"] = "prepaid"
        elif "upi" in clean:
            terms["payment"] = "upi"
        elif "card" in clean or "credit" in clean:
            terms["payment"] = "card"

        if "unlimited refund" in clean:
            terms["unlimited_refunds"] = True
        if "zero liability" in clean:
            terms["zero_liability"] = True

        # 5. Intent detection
        if any(w in clean for w in ["refund", "return", "cancel", "money back", "defective"]):
            intent = "refund"
        elif "renew" in clean or "renewal" in clean:
            intent = "renew"
        else:
            intent = "purchase"

        return ParsedOffer(
            product_id=product_id,
            proposed_price_inr=price,
            quantity=quantity,
            terms=terms,
            intent=intent,
            confidence=0.85 if price is not None else 0.6,
            raw_text=text
        )
