from types import SimpleNamespace

import pytest

from deferral_guard.genai import (
    OCIGenAIProvider,
    OfflineProvider,
    classify_intake,
    explain_finding,
)
from deferral_guard.models import Finding, Severity, Trigger


class CannedProvider:
    name = "canned"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def test_classify_handles_fenced_json_from_model():
    reply = ('Here is the result:\n```json\n{"trigger_event": "unforeseeable_emergency", '
             '"amount": "$60,000", "requested_payment_date": "2026-09-30", '
             '"emergency_need_amount": 48750, "summary": "Medical bills."}\n```')
    draft = classify_intake("my spouse was hospitalized", CannedProvider(reply))
    assert draft.trigger_event is Trigger.UNFORESEEABLE_EMERGENCY
    assert draft.amount == 60_000
    assert draft.emergency_need_amount == 48_750
    assert draft.needs_human_review


def test_unknown_label_routes_to_review_as_non_qualifying():
    draft = classify_intake("x", CannedProvider('{"trigger_event": "HARDSHIP_LOAN"}'))
    assert draft.trigger_event is Trigger.IN_SERVICE


def test_model_without_json_raises():
    with pytest.raises(ValueError):
        classify_intake("x", CannedProvider("I cannot help with that."))


@pytest.mark.parametrize("text, expected", [
    ("I retired on 2026-06-30 and want my deferred comp paid out.", Trigger.SEPARATION),
    ("We have $60,000 in medical bills after a hospital stay; need is $48,750.",
     Trigger.UNFORESEEABLE_EMERGENCY),
    ("Can I take $25,000 out of my deferred comp for a boat? Still working.", Trigger.IN_SERVICE),
    ("My father passed away; I am the beneficiary.", Trigger.DEATH),
])
def test_offline_provider_classification(text, expected):
    assert classify_intake(text, OfflineProvider()).trigger_event is expected


def test_explain_finding_keeps_facts():
    f = Finding("DIST-002", Severity.FAIL, "D-1", "P-1",
                "Payment 2026-08-01 is inside the six-month delay. Earliest date is 2026-12-30.",
                "Treas. Reg. 1.409A-3(i)(2)")
    text = explain_finding(f, provider=OfflineProvider())
    assert "2026-12-30" in text and "1.409A-3(i)(2)" in text


def test_oci_provider_builds_generic_chat_request():
    pytest.importorskip("oci")
    captured = {}

    class FakeClient:
        def chat(self, details):
            captured["details"] = details
            msg = SimpleNamespace(content=[SimpleNamespace(text='{"trigger_event": "DEATH"}')])
            return SimpleNamespace(data=SimpleNamespace(
                chat_response=SimpleNamespace(choices=[SimpleNamespace(message=msg)])))

    provider = OCIGenAIProvider(client=FakeClient(), compartment_id="ocid1.compartment.oc1..test")
    draft = classify_intake("beneficiary claim", provider)
    details = captured["details"]
    assert draft.trigger_event is Trigger.DEATH and draft.provider == "oci-genai"
    assert details.serving_mode.model_id == "meta.llama-3.3-70b-instruct"
    assert details.chat_request.temperature == 0
    assert details.compartment_id.startswith("ocid1.compartment")
