from __future__ import annotations

"""CLI entrypoint for promotions model training."""

from runtime.promotions.promotions_pipeline_runner import main


if __name__ == "__main__":
    main(default_mode="train")
