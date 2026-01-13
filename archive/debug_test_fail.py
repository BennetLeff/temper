
import yaml
from click.testing import CliRunner
from temper_placer.cli import main
from pathlib import Path
import tempfile
import os

def debug_test():
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_path = Path(tmp_dir_str)
        # Create a dummy PCB and config
        pcb_file = tmp_path / "test.kicad_pcb"
        pcb_file.write_text("(kicad_pcb (version 20211014) (generator pcbnew) (general (thickness 1.6)))")

        study_config = {
            "study_name": "test_study",
            "experiments": [
                {
                    "name": "baseline",
                    "description": "Baseline experiment",
                    "components": {},
                    "losses": {},
                    "tags": ["baseline"]
                }
            ],
            "seeds": [42],
            "test_cases": [str(pcb_file)],
            "output_dir": str(tmp_path / "results"),
            "parallel_workers": 1
        }

        config_file = tmp_path / "study.yaml"
        config_file.write_text(yaml.dump(study_config))

        runner = CliRunner()
        print("Invoking CLI...")
        result = runner.invoke(main, ["ablate", "run", str(config_file), "--no-report"])
        
        print(f"Exit Code: {result.exit_code}")
        print(f"Exception: {result.exception}")
        print("Output:")
        print(result.output)

if __name__ == "__main__":
    debug_test()
