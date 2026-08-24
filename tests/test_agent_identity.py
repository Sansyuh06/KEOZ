from keoz.gateway.agent_identity import AgentIdentityVerifier


def test_agent_identity_token_verification():
    verifier = AgentIdentityVerifier(trusted_principals=["acme-corp"])

    # Valid token
    token = verifier.issue_token(
        agent_id="bot-1",
        principal_id="acme-corp",
        max_commitment_inr=1000000
    )
    res = verifier.verify(token, required_amount_inr=500000)
    assert res.verified is True
    assert res.identity.agent_id == "bot-1"

    # Exceeds max commitment
    res_overspend = verifier.verify(token, required_amount_inr=2000000)
    assert res_overspend.verified is False
    assert res_overspend.code == "AGENT_COMMITMENT_EXCEEDED"

    # Untrusted principal
    untrusted_token = verifier.issue_token(
        agent_id="rogue-bot",
        principal_id="evil-corp",
        max_commitment_inr=1000000
    )
    res_untrusted = verifier.verify(untrusted_token)
    assert res_untrusted.verified is False
    assert res_untrusted.code == "UNTRUSTED_PRINCIPAL"
