import logging
import os
import sys
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from slack_bolt import App

from work.fingertips.confluence.managers.openai import OpenAIManager

load_dotenv()

CONTEXT_LIMIT = os.getenv("OPENAI_MODEL_CONTEXT_LIMIT", 100000)
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

# Initialize the Bolt app with the bot token and signing secret
slack_app = App(
    token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET")
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set global logging level to DEBUG

# Create a handler for stdout, set level to INFO
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)

# Create a handler for stderr, set level to WARNING
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)

# Add both handlers to the logger
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)
formatter = logging.Formatter("%(filename)s:%(lineno)d - %(message)s")
stdout_handler.setFormatter(formatter)
stderr_handler.setFormatter(formatter)


logger.info("Initialized Confluence API and Slack App")


confluence_helper = OpenAIManager(
    confluence_base_url=os.getenv("CONFLUENCE_URL"),
    confluence_username=os.getenv("CONFLUENCE_USERNAME"),
    confluence_token=os.getenv("CONFLUENCE_API_TOKEN"),
)


@lru_cache
def get_my_info() -> str:
    """Fetches bot info and caches it."""
    logger.info("Fetching bot info")
    return slack_app.client.auth_test().data


def speaking_to_me(body: Any) -> bool:
    """Checks if the bot was mentioned in the message."""
    logger.info("Checking if the bot was mentioned")
    event = body["event"]
    app_mention = "app_mention" in event.get("type")
    im = event.get("channel_type") == "im"

    # If the message is part of a thread that the bot is in
    my_thread = False
    if "thread_ts" in event:
        # Fetch the thread's history
        thread_history = slack_app.client.conversations_replies(
            channel=event["channel"], ts=event["thread_ts"]
        )

        # Check all messages in the thread
        messages = thread_history.data.get("messages", [])
        for message_index, message in enumerate(messages):
            # Check if I sent any of the messages in the thread
            if message.get("bot_id") == get_my_info().get("bot_id"):
                if message_index < len(messages) - 1:
                    # This isn't the last message in the thread, so the bot is in the thread
                    my_thread = True
                else:
                    # This is the last message in the thread, so the bot sent the most recent message
                    # And shouldn't respond to itself
                    my_thread = False

            # Check if I was mentioned in any of the messages
            if f"<@{get_my_info().get('user')}>" in message.get("text", "").lower():
                my_thread = True
    return app_mention or im or my_thread


@slack_app.event("app_mention")
def handle_app_mention_events(body: Any, logger: Any) -> None:
    """Handles app mention events."""
    logger.info("Handling app mention events")
    generate_response(body, source="handle_app_mention_events")


@slack_app.event("message")
def handle_message_events(body: Any, logger: Any) -> None:
    """Handles message events."""
    logger.info("Handling message events")
    if (
        body.get("event", {}).get("subtype") != "bot_message"
        and "app_mention" not in body.get("event", {}).get("type")
        and speaking_to_me(body)
    ):
        generate_response(body, source="handle_message_events")


def generate_response(body: Any, source=None) -> None:
    """Generates response for the given event."""
    logger.info("Generating response")
    event = body["event"]
    channel = body["event"].get("channel")
    user = body["event"].get("user")
    thread_ts = event.get("thread_ts")

    user_query = body["event"].get("text")

    response = confluence_helper.answer(user_query, user, channel)

    if channel:
        logger.info("Posting message to channel")
        slack_app.client.chat_postMessage(
            channel=channel, text=response, thread_ts=thread_ts
        )
    else:
        logger.info("Posting message to user")
        slack_app.client.chat_postMessage(
            channel=user, text=response, thread_ts=thread_ts
        )


if __name__ == "__main__":
    if 0:
        slack_app.start(port=int(os.environ.get("PORT", 3000)))

    # Testing
    else:
        import time

        start_time = time.time()

        print(
            confluence_helper.answer(
                # "What is the buddy system?", "U01UJ9ZLZ9Z", "C01UJ9ZLZ9Z"
                "What is the API documentation URL for the enterprise product?",
                "U01UJ9ZLZ9Z",
                "C01UJ9ZLZ9Z",
            )
        )
        print("--- %s seconds ---" % (time.time() - start_time))
