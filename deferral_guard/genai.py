"""OCI Generative AI integration.

Two narrow jobs, both kept *outside* the compliance decision:

1. ``classify_intake`` turns a participant's free-text request (email, call
   note) into a structured draft: trigger event, amount, dates. A person
   confirms it before it becomes a DG_DISTRIBUTION_REQUESTS row.
2. ``explain_finding`` rewrites a rule finding in plain language for a
   participant letter or a plan committee packet.

The deterministic rules engine always makes the pass/fail call; the model
never does. Without OCI credentials the module falls back to an offline
keyword provider so the demo and CI run anywhere.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from .models import Finding, Trigger

DEFAULT_MODEL = "meta.llama-3.3-70b-instruct"

INTAKE_PROMPT = """You are an intake assistant for a nonqualified deferred compensation plan.
Read the participant message and return ONLY a JSON object with these keys:
  "trigger_event": one of {events}
  "amount": number or null
  "requested_payment_date": "YYYY-MM-DD" or null
  "emergency_need_amount": number or null (documented need, only for emergencies)
  "summary": one sentence, no personal data beyond what is needed
Choose IN_SERVICE when the person simply wants money while still employed
without a qualifying event. Do not decide eligibility.

Message:
\"\"\"{text}\"\"\"
"""

EXPLAIN_PROMPT = """Rewrite this Section 409A plan finding for a {audience}.
Use plain language, at most three sentences, no legal advice, and keep the
dates and dollar amounts exactly as given. Mention the regulation citation once.

Rule: {rule_code} ({severity})
Finding: {message}
Citation: {citation}
"""


class ChatProvider(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# OCI Generative AI provider
# ---------------------------------------------------------------------------

class OCIGenAIProvider:
    """Calls the OCI Generative AI inference endpoint with an on-demand model.

    Configuration (environment):
      OCI_CONFIG_FILE / OCI_CONFIG_PROFILE  standard OCI SDK config (~/.oci/config)
      OCI_GENAI_COMPARTMENT_ID              compartment with Generative AI access
      OCI_GENAI_REGION                      e.g. us-chicago-1
      OCI_GENAI_MODEL                       defaults to meta.llama-3.3-70b-instruct
    """

    name = "oci-genai"

    def __init__(self, client=None, compartment_id: str | None = None,
                 model_id: str | None = None, region: str | None = None):
        self.compartment_id = compartment_id or os.environ["OCI_GENAI_COMPARTMENT_ID"]
        self.model_id = model_id or os.getenv("OCI_GENAI_MODEL", DEFAULT_MODEL)
        if client is None:
            import oci  # imported lazily so the package works without the SDK

            config = oci.config.from_file(
                os.getenv("OCI_CONFIG_FILE", oci.config.DEFAULT_LOCATION),
                os.getenv("OCI_CONFIG_PROFILE", oci.config.DEFAULT_PROFILE),
            )
            region = region or os.getenv("OCI_GENAI_REGION", config.get("region"))
            client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                config,
                service_endpoint=f"https://inference.generativeai.{region}.oci.oraclecloud.com",
            )
        self.client = client

    def complete(self, prompt: str) -> str:
        from oci.generative_ai_inference import models as m

        details = m.ChatDetails(
            compartment_id=self.compartment_id,
            serving_mode=m.OnDemandServingMode(model_id=self.model_id),
            chat_request=m.GenericChatRequest(
                api_format=m.GenericChatRequest.API_FORMAT_GENERIC,
                messages=[m.UserMessage(content=[m.TextContent(text=prompt)])],
                max_tokens=600,
                temperature=0,
            ),
        )
        response = self.client.chat(details)
        return response.data.chat_response.choices[0].message.content[0].text


# ---------------------------------------------------------------------------
# Offline provider (demo / CI)
# ---------------------------------------------------------------------------

_KEYWORDS = [
    (Trigger.DEATH, r"\b(passed away|died|death|estate|beneficiary)\b"),
    (Trigger.DISABILITY, r"\b(disabled|disability|long[- ]term disability)\b"),
    (Trigger.UNFORESEEABLE_EMERGENCY,
     r"\b(emergency|medical bills?|hospital|foreclos\w*|evict\w*|flood|fire|casualty)\b"),
    (Trigger.CHANGE_IN_CONTROL, r"\b(acquisition|acquired|merger|change in control)\b"),
    (Trigger.SEPARATION, r"\b(retir\w*|resign\w*|last day|separat\w*|terminat\w*|left the company)\b"),
    (Trigger.DE_MINIMIS, r"\b(small balance|cash[- ]?out|close (out )?my account)\b"),
    (Trigger.FIXED_DATE, r"\b(scheduled (payment|distribution)|in-service date I elected)\b"),
]

_MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


class OfflineProvider:
    """Deterministic keyword classifier that mimics the JSON contract."""

    name = "offline"

    def complete(self, prompt: str) -> str:
        if prompt.startswith("Rewrite this Section 409A"):
            finding = re.search(r"Finding: (.*)\n", prompt).group(1)
            citation = re.search(r"Citation: (.*)\n", prompt).group(1)
            return f"{finding} This follows {citation}."

        text = re.search(r'"""(.*)"""', prompt, re.S).group(1)
        lowered = text.lower()
        trigger = Trigger.IN_SERVICE
        for candidate, pattern in _KEYWORDS:
            if re.search(pattern, lowered):
                trigger = candidate
                break
        amounts = [float(a.replace(",", "")) for a in _MONEY.findall(text)]
        dates = _DATE.findall(text)
        return json.dumps({
            "trigger_event": trigger.value,
            "amount": amounts[0] if amounts else None,
            "requested_payment_date": dates[0] if dates else None,
            "emergency_need_amount": amounts[1] if len(amounts) > 1 else None,
            "summary": f"Participant request classified as {trigger.value.replace('_', ' ').lower()}.",
        })


def default_provider() -> ChatProvider:
    if os.getenv("OCI_GENAI_COMPARTMENT_ID"):
        return OCIGenAIProvider()
    return OfflineProvider()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntakeDraft:
    trigger_event: Trigger
    amount: float | None
    requested_payment_date: str | None
    emergency_need_amount: float | None
    summary: str
    provider: str
    needs_human_review: bool = True


def _extract_json(raw: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the object."""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError(f"model returned no JSON object: {raw[:200]!r}")
    return json.loads(match.group(0))


def classify_intake(text: str, provider: ChatProvider | None = None) -> IntakeDraft:
    provider = provider or default_provider()
    prompt = INTAKE_PROMPT.format(events=", ".join(t.value for t in Trigger), text=text)
    data = _extract_json(provider.complete(prompt))
    try:
        trigger = Trigger(str(data.get("trigger_event", "")).upper())
    except ValueError:
        trigger = Trigger.IN_SERVICE  # unknown label: route to review as non-qualifying
    return IntakeDraft(
        trigger_event=trigger,
        amount=_num(data.get("amount")),
        requested_payment_date=data.get("requested_payment_date"),
        emergency_need_amount=_num(data.get("emergency_need_amount")),
        summary=str(data.get("summary", ""))[:4000],
        provider=provider.name,
    )


def explain_finding(finding: Finding, audience: str = "plan participant",
                    provider: ChatProvider | None = None) -> str:
    provider = provider or default_provider()
    prompt = EXPLAIN_PROMPT.format(audience=audience, rule_code=finding.rule_code,
                                   severity=finding.severity.value, message=finding.message,
                                   citation=finding.citation)
    return provider.complete(prompt).strip()[:4000]


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return None
