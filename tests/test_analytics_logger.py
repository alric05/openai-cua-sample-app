import csv
from analytics import AnalyticsLogger


def test_structured_logging(tmp_path):
    log_dir = tmp_path / "logs"
    logger = AnalyticsLogger(log_dir=str(log_dir))

    # Prompt logging
    prompt_id = logger.new_prompt("hello")
    prompts_path = log_dir / logger.agent_id / "prompts.csv"
    with open(prompts_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["prompt_id"] == prompt_id
    assert rows[0]["prompt"] == "hello"

    # Step logging with screenshot
    step_id = logger.log_step(
        prompt_id,
        "computer_call",
        0.5,
        action_type="click",
        x=1,
        y=2,
        button="left",
        screenshot="abc123",
    )
    steps_path = log_dir / logger.agent_id / "steps.csv"
    with open(steps_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["step_id"] == step_id
    assert rows[0]["x"] == "1"
    assert rows[0]["y"] == "2"
    assert rows[0]["button"] == "left"
    assert rows[0]["screenshot"] == f"{step_id}.txt"

    screenshot_file = log_dir / logger.agent_id / "screenshots" / f"{step_id}.txt"
    assert screenshot_file.read_text() == "abc123"
