"""Tests for KEOZ OpenEnv & Agent Fine-Tuning Module."""

import pytest
from keoz.openenv.env import KeozCommerceEnv, run_benchmark, conservative_agent, greedy_agent, strategic_agent, adversarial_agent, AgentScore
from keoz.openenv.trajectories import generate_dpo_dataset, generate_sft_dataset


def test_openenv_reset_and_step():
    env = KeozCommerceEnv(merchant_id="acme-saas")
    obs, info = env.reset(seed=42)

    assert obs["merchant_id"] == "acme-saas"
    assert "product_id" in obs
    assert obs["current_round"] == 0
    assert info["margin_floor_pct"] == 0.37

    action = {
        "proposed_price_inr": 48000,
        "quantity": 10,
        "terms": {"payment": "prepaid"}
    }
    next_obs, reward, done, _, step_info = env.step(action)
    assert next_obs["current_round"] == 1
    assert done is True
    assert reward > 0
    assert step_info["episode_stats"] is not None
    assert step_info["episode_stats"]["outcome"] in ["authorized", "escalated"]


def test_openenv_adversarial_step_penalty():
    env = KeozCommerceEnv(merchant_id="acme-saas")
    env.reset(seed=42)

    action = {
        "proposed_price_inr": 9000,
        "quantity": 1,
        "terms": {"payment": "net_90"}
    }
    next_obs, reward, done, _, step_info = env.step(action)
    assert done is True
    assert reward < 0 or step_info.get("code") in ["POLICY_CLAMPED_TO_FLOOR", "MARGIN_FLOOR_VIOLATION", "REQUIRES_HUMAN_APPROVAL"]


def test_dpo_dataset_generation():
    dataset = generate_dpo_dataset(num_samples=10, merchant_id="acme-saas", seed=42)
    assert len(dataset) == 10
    sample = dataset[0]
    assert "prompt" in sample
    assert "chosen" in sample
    assert "rejected" in sample
    assert "metadata" in sample
    assert "floor_price" in sample["metadata"]
    assert "chosen_is_policy_compliant" in sample["metadata"]


def test_sft_dataset_generation():
    dataset = generate_sft_dataset(num_samples=5, merchant_id="acme-saas", seed=42)
    assert len(dataset) == 5
    sample = dataset[0]
    assert "instruction" in sample
    assert "output" in sample
    assert "metadata" in sample


def test_benchmark_conservative_agent():
    score = run_benchmark(conservative_agent, agent_id="test-conservative", num_episodes=5, merchant_id="acme-saas")
    assert isinstance(score, AgentScore)
    assert score.total_episodes == 5
    assert score.agent_id == "test-conservative"
    # Conservative agent should mostly win or escalate
    assert score.wins + score.escalations >= 3


def test_benchmark_adversarial_agent():
    score = run_benchmark(adversarial_agent, agent_id="test-adversarial", num_episodes=5, merchant_id="acme-saas")
    assert isinstance(score, AgentScore)
    assert score.total_episodes == 5
    # Adversarial agent should be blocked or escalated, not authorized
    assert score.blocks + score.escalations >= 3
