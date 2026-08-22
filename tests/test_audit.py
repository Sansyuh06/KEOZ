from agentpolicy.memory.audit_logger import AuditLogger


def test_audit_logger_hash_chain():
    logger = AuditLogger()

    atom1 = logger.record("bounds_compiled", "1.0", "hash1", {"max": 500000})
    atom2 = logger.record("negotiation_round", "1.0", "hash1", {"price": 45000})

    assert atom1.provenance_hash is not None
    assert atom2.provenance_hash is not None
    assert atom1.provenance_hash != atom2.provenance_hash

    replayed = logger.replay()
    assert len(replayed) == 2
    assert replayed[0]["atom_type"] == "bounds_compiled"
