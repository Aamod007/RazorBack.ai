import pytest
import numpy as np
from backend.app.risk_scorer import risk_scorer

def test_risk_scorer_training_and_metrics():
    metrics = risk_scorer.train_and_evaluate()
    
    # Verify presence of all PRD success metrics
    assert "metrics" in metrics
    assert "precision" in metrics["metrics"]
    assert "recall" in metrics["metrics"]
    assert "f1_score" in metrics["metrics"]
    assert "roc_auc" in metrics["metrics"]
    
    # Assert sensible performance bounds
    assert 0.0 <= metrics["metrics"]["precision"] <= 1.0
    assert 0.0 <= metrics["metrics"]["recall"] <= 1.0
    assert metrics["metrics"]["roc_auc"] > 0.65

    # Verify confusion matrix
    cm = metrics["confusion_matrix"]
    assert "true_negatives" in cm
    assert "false_positives" in cm
    assert "false_negatives" in cm
    assert "true_positives" in cm

    # Verify financial impact in INR
    fin = metrics["financial_impact_inr"]
    assert fin["false_positive_cost_inr"] >= 0.0
    assert fin["false_negative_cost_inr"] >= 0.0
    assert fin["average_dispute_amount_inr"] > 0.0

    # Verify win-rate lift vs baselines
    comp = metrics["win_rate_comparison"]
    assert comp["baseline_accept_all_rate"] == 0.0
    assert comp["disputeguard_win_rate"] >= comp["baseline_contest_all_rate"]

def test_risk_scorer_inference():
    features_strong = {
        "reason_code": "goods_not_as_described",
        "phase": "chargeback",
        "amount_inr": 2500.0,
        "response_window_hours": 72.0,
        "time_remaining_hours": 48.0,
        "payment_method": "card",
        "merchant_historical_win_rate": 0.70,
        "order_fulfillment_confirmed": 1,
        "evidence_completeness_score": 1.0,
        "customer_prior_disputes": 0
    }
    prob_strong = risk_scorer.predict_win_probability(features_strong)
    assert 0.0 <= prob_strong <= 1.0

    features_weak = {
        "reason_code": "fraudulent",
        "phase": "chargeback",
        "amount_inr": 800.0,
        "response_window_hours": 48.0,
        "time_remaining_hours": 12.0,
        "payment_method": "card",
        "merchant_historical_win_rate": 0.25,
        "order_fulfillment_confirmed": 0,
        "evidence_completeness_score": 0.2,
        "customer_prior_disputes": 3
    }
    prob_weak = risk_scorer.predict_win_probability(features_weak)
    assert 0.0 <= prob_weak <= 1.0

    # Strong case must have higher win probability than weak case
    assert prob_strong > prob_weak
