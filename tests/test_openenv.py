"""Tests for KEOZ OpenEnv & Agent Fine-Tuning Module."""

import pytest
from keoz.openenv.env import KeozCommerceEnv
from keoz.openenv.trajectories import generate_dpo_dataset


def test_openenv_reset_and_step():
    env = KeozCommerceEnv(merchant_id="acme-saas")
    obs, info = env.reset(seed=42)

    assert obs["merchant_id"] == "acme-saas"
    assert "product_id" in obs
    assert obs["current_round"] == 0
    assert info["margin_floor_pct"] == 0.37

    # Valid step
    action = {
        "proposed_price_inr": 48000,
        "quantity": 10,
        "terms": {"payment": "prepaid"}
    }
    next_obs, reward, done, _, step_info = env.step(action)
    assert next_obs["current_round"] == 1
    assert done is True  # Successful authorization closes session
    assert reward > 0


def test_openenv_adversarial_step_penalty():
    env = KeozCommerceEnv(merchant_id="acme-saas")
    env.reset(seed=42)

    # Margin draining action: 80% discount
    action = {
        "proposed_price_inr": 9000,
        "quantity": 1,
        "terms": {"payment": "net_90"}
    }
    next_obs, reward, done, _, step_info = env.step(action)
    assert done is True
    # Reward should be penalty for illegal parameter attempt
    assert reward < 0 or step_info.get("code") in ["POLICY_CLAMPED_TO_FLOOR", "MARGIN_FLOOR_VIOLATION", "REQUIRES_HUMAN_APPROVAL"]


def test_dpo_dataset_generation():
    dataset = generate_dpo_dataset(num_samples=10, merchant_id="acme-saas")
    assert len(dataset) == 10
    sample = dataset[0]
    assert "prompt" in sample
    assert "chosen" in sample
    assert "rejected" in sample
    assert "metadata" in sample
