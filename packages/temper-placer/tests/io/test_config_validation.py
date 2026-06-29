
import pytest
import yaml

from temper_placer.io.config_loader import load_constraints


def test_loss_weight_validation_negative(tmp_path):
    config = {
        "loss_weights": {
            "overlap": -1.0
        }
    }
    p = tmp_path / "config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    with pytest.raises(ValueError, match="must be positive"):
        load_constraints(p)

def test_loss_weight_validation_too_large(tmp_path):
    config = {
        "loss_weights": {
            "overlap": 2e6
        }
    }
    p = tmp_path / "config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    with pytest.raises(ValueError, match="must be less than"):
        load_constraints(p)

def test_loss_weight_validation_inf(tmp_path):
    config = {
        "loss_weights": {
            "overlap": float("inf")
        }
    }
    p = tmp_path / "config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    with pytest.raises(ValueError, match="must be finite"):
        load_constraints(p)

def test_loss_weight_validation_nan(tmp_path):
    config = {
        "loss_weights": {
            "overlap": float("nan")
        }
    }
    p = tmp_path / "config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    with pytest.raises(ValueError, match="must be finite"):
        load_constraints(p)

def test_losses_config_validation_negative(tmp_path):
    config = {
        "losses": {
            "overlap": {
                "weight": -5.0
            }
        }
    }
    p = tmp_path / "config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    with pytest.raises(ValueError, match="must be positive"):
        load_constraints(p)
