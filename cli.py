import argparse
from agent.agent import Agent
from computers.config import *
from computers.default import *
from computers import computers_config
from analytics.logger import AnalyticsLogger

logger = AnalyticsLogger()

def acknowledge_safety_check_callback(message: str) -> bool:
    response = input(
        f"Safety Check Warning: {message}\nDo you want to acknowledge and proceed? (y/n): "
    ).lower()
    return response.lower().strip() == "y"


def main():
    parser = argparse.ArgumentParser(
        description="Select a computer environment from the available options."
    )
    parser.add_argument(
        "--computer",
        choices=computers_config.keys(),
        help="Choose the computer environment to use.",
        default="local-playwright",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Initial input to use instead of asking the user.",
        default=None,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode for detailed output.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show images during the execution.",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        help="Start the browsing session with a specific URL (only for browser environments).",
        default="https://bing.com",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        help="Maximum number of model round trips to run before returning a capped response.",
        default=None,
    )
    parser.add_argument(
        "--stop-on-message",
        action="store_true",
        help=(
            "Stop the agent automatically once it produces a message for the user. "
            "Useful for terminating the session after the first assistant reply."
        ),
    )
    args = parser.parse_args()
    ComputerClass = computers_config[args.computer]

    with ComputerClass() as computer:
        agent = Agent(
            computer=computer,
            acknowledge_safety_check_callback=acknowledge_safety_check_callback,
            logger=logger,
        )
        items = []

        if args.computer in ["browserbase", "local-playwright"]:
            if not args.start_url.startswith("http"):
                args.start_url = "https://" + args.start_url
            agent.computer.goto(args.start_url)
            get_metadata = getattr(agent.computer, "get_page_metadata", None)
            if callable(get_metadata):
                metadata = get_metadata() or {}
                if not metadata.get("full_url"):
                    metadata["full_url"] = agent.computer.get_current_url()
                logger.log(
                    {
                        "type": "browser_state",
                        "event": "initial_navigation",
                        "metadata": metadata,
                    }
                )

        while True:
            try:
                user_input = args.input or input("> ")
                if user_input == "exit":
                    break
            except EOFError as e:
                print(f"An error occurred: {e}")
                break
            prompt_id = logger.new_prompt(user_input)
            items.append({"role": "user", "content": user_input})
            output_items = agent.run_full_turn(
                items,
                print_steps=True,
                show_images=args.show,
                debug=args.debug,
                prompt_id=prompt_id,
                max_actions=args.max_actions,
            )
            items += output_items
            args.input = None

            if args.stop_on_message and any(
                item.get("type") == "message" and item.get("role") == "assistant"
                for item in output_items
            ):
                print("Assistant message received; stopping due to --stop-on-message.")
                break

            if args.max_actions is not None and any(
                item.get("type") == "max-actions" for item in output_items
            ):
                print("Maximum actions reached; stopping due to --max-actions.")
                break


if __name__ == "__main__":
    main()
