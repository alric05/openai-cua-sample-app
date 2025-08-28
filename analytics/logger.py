import os
import uuid
import json
from datetime import datetime
from typing import Any, Dict


class AnalyticsLogger:
    """Persist interaction events for later analysis.

    Each run of the CLI creates a unique log file in JSON Lines format so that
    multiple agents running in parallel do not clobber each other's data.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        run_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        # Unique identifier for a single agent session.
        self.agent_id = f"{run_ts}_{uuid.uuid4()}"
        self.log_path = os.path.join(self.log_dir, f"{self.agent_id}.jsonl")

    def log(self, record: Dict[str, Any]) -> None:
        """Append a record to the log file."""
        # Persist the agent identifier on every record so logs can be
        # correlated later.
        record["agent_id"] = self.agent_id
        record.setdefault("timestamp", datetime.utcnow().isoformat())
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def new_prompt(self, content: str) -> str:
        """Log a new user prompt and return its identifier."""
        prompt_id = str(uuid.uuid4())
        self.log({"type": "user_prompt", "prompt_id": prompt_id, "content": content})
        return prompt_id
