import os
import uuid
import csv
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class AnalyticsLogger:
    """Structured logger that stores prompts and steps for analytics.

    Each run creates a unique directory containing two CSV files:
    - ``prompts.csv``: one row per user prompt
    - ``steps.csv``: one row per agent step triggered by a prompt

    Screenshots are stored as separate ``.txt`` files containing the
    base64-encoded image. The corresponding filename is referenced in the
    ``screenshot`` column of ``steps.csv``.
    """

    prompt_fields = ["agent_id", "prompt_id", "prompt", "timestamp"]
    step_fields = [
        "agent_id",
        "prompt_id",
        "step_id",
        "step_type",
        "action_type",
        "role",
        "text",
        "button",
        "x",
        "y",
        "call_id",
        "screenshot",
        "timestamp",
        "duration",
        "details",
    ]

    def __init__(self, log_dir: str = "logs") -> None:
        self.base_dir = log_dir
        os.makedirs(self.base_dir, exist_ok=True)
        run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.agent_id = f"{run_ts}_{uuid.uuid4()}"
        self.run_dir = os.path.join(self.base_dir, self.agent_id)
        self.screenshot_dir = os.path.join(self.run_dir, "screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)

        self.prompts_path = os.path.join(self.run_dir, "prompts.csv")
        self.steps_path = os.path.join(self.run_dir, "steps.csv")

        # Initialize CSV files with headers
        with open(self.prompts_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.prompt_fields)
        with open(self.steps_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.step_fields)

    def new_prompt(self, content: str) -> str:
        """Record a user prompt and return its identifier."""
        prompt_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(self.prompts_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([self.agent_id, prompt_id, content, timestamp])
        return prompt_id

    def log_step(
        self,
        prompt_id: str,
        step_type: str,
        duration: float,
        **data: Any,
    ) -> str:
        """Log a step taken by the agent.

        Args:
            prompt_id: ID of the prompt that triggered this step.
            step_type: The kind of item (e.g., "message", "computer_call").
            duration: Time taken in seconds.
            **data: Additional structured information about the step. Any
                unrecognized keys will be stored as JSON in the ``details``
                column.
        Returns:
            The generated step identifier.
        """
        step_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        screenshot_file = ""
        screenshot_b64: Optional[str] = data.pop("screenshot", None)
        if screenshot_b64:
            screenshot_file = f"{step_id}.txt"
            with open(
                os.path.join(self.screenshot_dir, screenshot_file),
                "w",
                encoding="utf-8",
            ) as img_file:
                img_file.write(screenshot_b64)

        known_fields = {
            "action_type",
            "role",
            "text",
            "button",
            "x",
            "y",
            "call_id",
        }
        row: Dict[str, Any] = {
            "agent_id": self.agent_id,
            "prompt_id": prompt_id,
            "step_id": step_id,
            "step_type": step_type,
            "screenshot": screenshot_file,
            "timestamp": timestamp,
            "duration": duration,
        }

        extras = {}
        for key, value in data.items():
            if key in known_fields:
                row[key] = value
            else:
                extras[key] = value

        # Ensure all known fields exist even if None
        for field in known_fields:
            row.setdefault(field, "")

        row["details"] = json.dumps(extras) if extras else ""

        with open(self.steps_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.step_fields)
            writer.writerow(row)

        return step_id
