import csv
import json
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
            "page_metadata": {
                "full_url": "https://example.com/",
                "page_title": "Example Domain",
                "domain": "example.com",
            },
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

    log_file = log_dir / logger.agent_id / "log.jsonl"
    out_csv = build_structured_table(str(log_file))

    assert Path(out_csv).exists()
    with open(out_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Expect three rows: user prompt + two steps
    assert len(rows) == 3
    prompt_rows = [r for r in rows if r["Prompt_Id"] == prompt_id]
    assert prompt_rows[0]["Step_Id"] == "0"
    assert prompt_rows[1]["Step_Id"] == "1"
    assert prompt_rows[1]["URL"] == "https://example.com/"
    assert prompt_rows[1]["Page_Title"] == "Example Domain"
    assert prompt_rows[1]["Domain"] == "example.com"
    # Ensure screenshot was extracted
    screenshot_file = prompt_rows[1]["Screenshot"]
    assert screenshot_file
    image_dir = log_dir / logger.agent_id / "screenshots"
    image_path = image_dir / screenshot_file
    assert image_path.exists()


def test_build_structured_table_creates_agent_scoped_screenshots(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "log.jsonl"
    agent_id = "agent-123"
    prompt_id = "prompt-456"

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "type": "user_prompt",
                    "prompt_id": prompt_id,
                    "content": "hello",
                    "agent_id": agent_id,
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "type": "computer_call",
                    "prompt_id": prompt_id,
                    "agent_id": agent_id,
                    "action": {"type": "click", "x": 1, "y": 2},
                    "screenshot": PIXEL_BASE64,
                }
            )
            + "\n"
        )

    build_structured_table(str(log_file))

    scoped_dir = log_dir / agent_id / "screenshots"
    assert scoped_dir.exists()
    assert (scoped_dir / f"{prompt_id}_1.png").exists()
    assert not (log_dir / "screenshots").exists()
