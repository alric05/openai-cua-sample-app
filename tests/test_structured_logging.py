import csv
from pathlib import Path

from analytics import AnalyticsLogger, build_structured_table

# 1x1 transparent PNG
PIXEL_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z/C/HwAF/gL+VkC4XAAAAABJRU5ErkJggg=="
)


def test_build_structured_table(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    logger = AnalyticsLogger(log_dir=str(log_dir))
    prompt_id = logger.new_prompt("hello")
    logger.log(
        {
            "prompt_id": prompt_id,
            "type": "computer_call",
            "action": {"type": "click", "x": 1, "y": 2},
            "screenshot": PIXEL_BASE64,
            "duration": 0.5,
        }
    )
    logger.log(
        {
            "prompt_id": prompt_id,
            "type": "message",
            "role": "assistant",
            "content": [{"text": "done"}],
            "duration": 0.1,
        }
    )

    log_file = next(log_dir.glob("*.jsonl"))
    out_csv = tmp_path / "structured.csv"
    build_structured_table(str(log_file), str(out_csv))

    assert out_csv.exists()
    with open(out_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Expect three rows: user prompt + two steps
    assert len(rows) == 3
    prompt_rows = [r for r in rows if r["Prompt_Id"] == prompt_id]
    assert prompt_rows[0]["Step_Id"] == "0"
    assert prompt_rows[1]["Step_Id"] == "1"
    # Ensure screenshot was extracted
    screenshot_file = prompt_rows[1]["Screenshot"]
    assert screenshot_file
    image_dir = Path(str(log_file).replace(".jsonl", "_images"))
    image_path = image_dir / screenshot_file
    assert image_path.exists()
