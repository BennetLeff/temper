
import json
import shutil
from pathlib import Path


def generate_dummy_dataset(dataset_dir: Path, n_samples: int = 10):
    """Creates a dummy dataset for testing the ML pipeline."""
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # Template PCB
    template_pcb = Path("packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb")

    for i in range(n_samples):
        design_id = f"sample_{i}"
        design_dir = dataset_dir / design_id
        design_dir.mkdir()

        # 1. Copy PCB
        shutil.copy(template_pcb, design_dir / "board.kicad_pcb")

        # 2. Create metadata
        metadata = {
            "id": design_id,
            "drc": {
                "success": True,
                "error_count": i % 5, # Varying quality
                "warning_count": i % 3,
                "violations": []
            }
        }

        (design_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("test_dataset"))
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    generate_dummy_dataset(args.output, args.n)
    print(f"Generated dummy dataset with {args.n} samples at {args.output}")
