from computers import Computer
from utils import (
    create_response,
    show_image,
    pp,
    sanitize_message,
    check_blocklisted_url,
)
import json
import time
from typing import Callable, Optional


class Agent:
    """
    A sample agent class that can be used to interact with a computer.

    (See simple_cua_loop.py for a simple example without an agent.)
    """

    def __init__(
        self,
        model="computer-use-preview",
        computer: Computer = None,
        tools: list[dict] = [],
        acknowledge_safety_check_callback: Callable = lambda: False,
        logger=None,
    ):
        self.model = model
        self.computer = computer
        self.tools = tools
        self.print_steps = True
        self.debug = False
        self.show_images = False
        self.acknowledge_safety_check_callback = acknowledge_safety_check_callback
        self.logger = logger
        self.current_prompt_id = None

        if computer:
            dimensions = computer.get_dimensions()
            self.tools += [
                {
                    "type": "computer-preview",
                    "display_width": dimensions[0],
                    "display_height": dimensions[1],
                    "environment": computer.get_environment(),
                },
            ]

    def debug_print(self, *args):
        if self.debug:
            pp(*args)

    def handle_item(self, item):
        """Handle each item; may cause a computer action + screenshot."""
        start_time = time.time()
        record = {"prompt_id": self.current_prompt_id, "type": item.get("type")}
        output_items = []

        if item["type"] in {"message", "max-actions"}:
            if self.print_steps:
                print(item["content"][0]["text"])
            record["role"] = item.get("role")
            record["content"] = item.get("content")

        elif item["type"] == "function_call":
            name, args = item["name"], json.loads(item["arguments"])
            if self.print_steps:
                print(f"{name}({args})")

            if hasattr(self.computer, name):  # if function exists on computer, call it
                method = getattr(self.computer, name)
                method(**args)
            output_items = [
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": "success",  # hard-coded output for demo
                }
            ]
            record.update({"name": name, "arguments": args})

        elif item["type"] == "computer_call":
            action = item["action"]
            action_type = action["type"]
            action_args = {k: v for k, v in action.items() if k != "type"}
            if self.print_steps:
                print(f"{action_type}({action_args})")

            method = getattr(self.computer, action_type)
            method(**action_args)

            screenshot_base64 = self.computer.screenshot()
            if self.show_images:
                show_image(screenshot_base64)

            # if user doesn't ack all safety checks exit with error
            pending_checks = item.get("pending_safety_checks", [])
            for check in pending_checks:
                message = check["message"]
                if not self.acknowledge_safety_check_callback(message):
                    raise ValueError(
                        f"Safety check failed: {message}. Cannot continue with unacknowledged safety checks."
                    )

            call_output = {
                "type": "computer_call_output",
                "call_id": item["call_id"],
                "acknowledged_safety_checks": pending_checks,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}",
                },
            }

            # additional URL safety checks for browser environments
            if self.computer.get_environment() == "browser":
                current_url = self.computer.get_current_url()
                check_blocklisted_url(current_url)

                metadata = {}
                get_metadata = getattr(self.computer, "get_page_metadata", None)
                if callable(get_metadata):
                    metadata = get_metadata() or {}

                if not metadata.get("full_url"):
                    metadata["full_url"] = current_url

                call_output["output"]["current_url"] = metadata.get("full_url", current_url)
                if metadata:
                    call_output["output"]["page_metadata"] = metadata
                    record["page_metadata"] = metadata
                else:
                    record["current_url"] = current_url

            output_items = [call_output]
            record.update(
                {
                    "action": action,
                    "call_id": item.get("call_id"),
                    "screenshot": screenshot_base64,
                }
            )

        elif item["type"] == "reasoning":
            record["summary"] = item.get("summary")

        duration = time.time() - start_time
        record["duration"] = duration

        if self.logger:
            self.logger.log(record)

        return output_items

    def run_full_turn(
        self,
        input_items,
        print_steps: bool = True,
        debug: bool = False,
        show_images: bool = False,
        prompt_id: Optional[str] = None,
        max_actions: Optional[int] = None,
    ):
        self.print_steps = print_steps
        self.debug = debug
        self.show_images = show_images
        self.current_prompt_id = prompt_id
        new_items = []
        action_count = 0

        # keep looping until we get a final response or hit the action ceiling
        while True:
            if new_items and new_items[-1].get("role") == "assistant":
                break

            if max_actions is not None and action_count >= max_actions:
                limit_message = {
                    "type": "max-actions",
                    "role": "assistant",
                    "content": [
                        {
                            "text": (
                                "Reached the configured maximum of "
                                f"{max_actions} actions without a final assistant response."
                                " Stopping further processing."
                            )
                        }
                    ],
                }
                new_items.append(limit_message)
                new_items += self.handle_item(limit_message)
                break

            self.debug_print([sanitize_message(msg) for msg in input_items + new_items])

            response = create_response(
                model=self.model,
                input=input_items + new_items,
                tools=self.tools,
                truncation="auto",
            )
            self.debug_print(response)

            if "output" not in response and self.debug:
                print(response)
                raise ValueError("No output from model")
            else:
                new_items += response["output"]
                for item in response["output"]:
                    new_items += self.handle_item(item)

            action_count += 1

        return new_items
