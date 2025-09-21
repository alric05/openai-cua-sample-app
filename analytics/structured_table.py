import os
import json
import csv
import base64
from itertools import chain
from typing import Dict, Any, Iterable, Optional, List

def build_structured_table(
    log_path: str,
    output_csv: Optional[str] = None,
    image_dir: Optional[str] = None,
) -> str:
    """Convert a JSONL log file to a structured CSV table.

    Screenshots in the log are written to ``image_dir`` and the filename is
    recorded in the ``Screenshot`` column of the CSV. Each row represents a
    step in a prompt run and contains identifiers for the agent, prompt and
    step along with action details.

    Parameters
    ----------
    log_path: str
        Path to the JSON Lines log file produced by ``AnalyticsLogger``.
    output_csv: str, optional
        Destination path for the structured CSV. Defaults to ``steps.csv``
        in the same directory as ``log_path``.
    image_dir: str, optional
        Directory where extracted screenshots will be written. Defaults to a
        ``screenshots`` subdirectory next to ``log_path``.

    Returns
    -------
    str
        The path to the generated CSV file.
    """

    log_dir = os.path.dirname(log_path)
    if output_csv is None:
        output_csv = os.path.join(log_dir, "steps.csv")

    def _default_image_dir(record: Dict[str, Any]) -> str:
        agent_id = record.get("agent_id") or record.get("run_id")
        parent_name = os.path.basename(os.path.normpath(log_dir))
        if agent_id and parent_name == "logs":
            return os.path.join(log_dir, agent_id, "screenshots")
        return os.path.join(log_dir, "screenshots")

    step_counters: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []

    with open(log_path, "r", encoding="utf-8") as f:
        first_line = f.readline()

        if not first_line:
            resolved_image_dir = image_dir or os.path.join(log_dir, "screenshots")
            os.makedirs(resolved_image_dir, exist_ok=True)
            records_iter: Iterable[Dict[str, Any]] = []
        else:
            first_record = json.loads(first_line)
            resolved_image_dir = image_dir or _default_image_dir(first_record)
            os.makedirs(resolved_image_dir, exist_ok=True)

            records_iter = chain([first_record], (json.loads(rest_line) for rest_line in f))

        for record in records_iter:
            agent_id = record.get("agent_id") or record.get("run_id")
            prompt_id = record.get("prompt_id")
            record_type = record.get("type")
            timestamp = record.get("timestamp")
            duration = record.get("duration")
            screenshot_file = ""
            action_type = ""
            x = ""
            y = ""
            text = ""

            if record_type == "user_prompt":
                step_id = 0
                text = record.get("content", "")
            else:
                step_id = step_counters.get(prompt_id, 0) + 1
                step_counters[prompt_id] = step_id
                action = record.get("action", {})
                action_type = action.get("type", record.get("name", ""))
                x = action.get("x", "")
                y = action.get("y", "")
                if action_type == "type":
                    text = action.get("text", "")
                elif record_type == "message":
                    content = record.get("content", [])
                    if isinstance(content, list):
                        text = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
                    else:
                        text = str(content)
                elif record_type == "reasoning":
                    text = record.get("summary", "")

                if "screenshot" in record:
                    image_bytes = base64.b64decode(record["screenshot"])
                    screenshot_file = f"{prompt_id}_{step_id}.png"
                    with open(os.path.join(resolved_image_dir, screenshot_file), "wb") as img_f:
                        img_f.write(image_bytes)

            rows.append(
                {
                    "Agent_Id": agent_id,
                    "Prompt_Id": prompt_id,
                    "Step_Id": step_id,
                    "Type": record_type,
                    "Action": action_type,
                    "X": x,
                    "Y": y,
                    "Text": text,
                    "Duration": duration,
                    "Timestamp": timestamp,
                    "Screenshot": screenshot_file,
                }
            )

    fieldnames = [
        "Agent_Id",
        "Prompt_Id",
        "Step_Id",
        "Type",
        "Action",
        "X",
        "Y",
        "Text",
        "Duration",
        "Timestamp",
        "Screenshot",
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_csv
