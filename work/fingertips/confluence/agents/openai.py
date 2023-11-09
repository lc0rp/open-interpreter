import inspect
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from openai.types.beta.assistant import Assistant
from openai.types.beta.thread import Thread
from openai.types.beta.threads import ThreadMessage
from openai.types.beta.threads.run import Run

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


class OpenAIAgent:
    def __init__(self, confluence_manager: object, tools=Optional[list[callable]]):
        self._openai_client = OpenAI()
        self._assistant = None
        self._threads: Dict[str, Thread] = {}
        self._confluence_manager = confluence_manager
        self._tools = tools

    def create_message(self, thread_id: str, content: str) -> ThreadMessage:
        """
        Send a message in the OpenAI thread.
        """
        return self._openai_client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=content
        )

    def get_tools_config(self):
        """
        Get the tools config.
        """
        tools_config = []
        for tool in self._tools:
            tools_config.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.__name__,
                        "description": tool.__doc__,
                        "parameters": self.generate_json_schema(tool),
                    },
                }
            )
        return tools_config

    def get_tool_parameters(tool: callable):
        """
        Inspect tool and get its parameters. For each parameter, find the json schema representation
        """
        import inspect

        params = inspect.signature(tool).parameters
        tool_params = {}
        for name, param in params.items():
            tool_params[name] = {
                "type": str(param.annotation),
                "description": param.default
                if param.default != inspect.Parameter.empty
                else None,
            }
        return tool_params

    def type_to_json_type(self, type_hint):
        """
        Convert a Python type hint to a JSON schema type.

        :param type_hint: The Python type hint.
        :return: A string representing the JSON schema type.
        """
        if type_hint is int:
            return "integer"
        elif type_hint is float:
            return "number"
        elif type_hint is bool:
            return "boolean"
        elif type_hint is str:
            return "string"
        elif type_hint is list:
            return "array"
        elif type_hint is dict:
            return "object"
        else:
            return "string"  # Default or unknown types

    def generate_json_schema(self, callable_to_inspect: callable):
        """
        Generate a JSON schema for the parameters of a callable (function/method).
        This version infers types from type annotations.
        """
        signature = inspect.signature(callable_to_inspect)
        schema = {"type": "object", "properties": {}, "required": []}

        for param_name, param in signature.parameters.items():
            # Infer type from annotation, default to "string" if not provided
            type_hint = (
                self.type_to_json_type(param.annotation)
                if param.annotation is not inspect.Parameter.empty
                else "string"
            )

            param_schema = {"type": type_hint}

            if param.default is not inspect.Parameter.empty:
                param_schema["default"] = param.default
            else:
                schema["required"].append(param_name)

            schema["properties"][param_name] = param_schema

        return schema

    @property
    def assistant(self) -> Assistant:
        """
        Get the OpenAI assistant.
        """
        if self._assistant is None:
            from jinja2 import Environment, FileSystemLoader

            env = Environment(
                loader=FileSystemLoader(Path.cwd() / "work/fingertips/prompts")
            )
            template = env.get_template("fingertips/prompt.j2")
            instructions = template.render()
            self._assistant = self._openai_client.beta.assistants.create(
                instructions=instructions,
                name="Fingertip Search Assistant",
                model=os.getenv("OPENAI_MODEL"),
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "search_confluence",
                            "description": "Searches Confluence using the Confluence Query Language (CQL). Returns max 5 results.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "cql_query": {
                                        "type": "string",
                                        "description": "The Confluence Query Language (CQL) query to search Confluence",
                                    },
                                },
                                "required": ["cql_query"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "load_confluence_page",
                            "description": "Loads a Confluence page using the Confluence REST API",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "page_or_content_id": {
                                        "type": "string",
                                        "description": "The Confluence page or content ID to load, e.g. from result['content']['id']",
                                    },
                                },
                                "required": ["page_or_content_id"],
                            },
                        },
                    },
                ],
            )
        return self._assistant

    def get_openai_thread(self, thread_key: str) -> Thread:
        """
        Get the OpenAI thread based on the thread key.
        """
        if thread_key not in self._threads:
            self._threads[thread_key] = self._openai_client.beta.threads.create()
        return self._threads[thread_key]

    def send_message(self, message: str, thread_key: str) -> List[Dict[str, Any]]:
        """
        Send a message to OpenAI and await the responses.
        """
        thread = self.get_openai_thread(thread_key)
        message = self.create_message(thread.id, message)
        run = self.create_run(thread.id)
        run = self.wait_for_run(thread.id, run.id)
        messages = self.get_thread_messages(thread.id)
        relevant_messages = self.extract_relevant_messages(messages, message.id)
        return relevant_messages

    def create_run(self, thread_id: str) -> Run:
        """
        Create a run in the OpenAI thread.
        """
        return self._openai_client.beta.threads.runs.create(
            thread_id=thread_id, assistant_id=self.assistant.id
        )

    def wait_for_run(self, thread_id: str, run_id: str) -> Run:
        """
        Wait for the run to complete or enter requires_action in the OpenAI thread.
        """
        run = self._openai_client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run_id
        )
        while run.status not in ["completed", "requires_action"]:
            run = self._openai_client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run_id
            )

        if run.status == "completed":
            return run

        if (
            run.status == "requires_action"
            and run.required_action.type == "submit_tool_outputs"
        ):
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            self.handle_submit_tool_outputs(tool_calls, thread_id, run_id)
            run = self.wait_for_run(thread_id, run_id)
        return run

    def handle_submit_tool_outputs(
        self, tool_calls: Any, thread_id: str, run_id: str
    ) -> Run:
        for tool_call in tool_calls:
            results = None
            if tool_call.function.name == "search_confluence":
                arguments = json.loads(tool_call.function.arguments)
                cql_query = arguments.get("cql_query")
                logger.info(f"Searching Confluence with CQL query: {cql_query}")
                results = self._confluence_manager.search_confluence(cql_query)
                result_count = results.get("size", 0)
                results = json.dumps(results)
                logger.info(f"Found {result_count} results: {results}")
            if tool_call.function.name == "load_confluence_page":
                arguments = json.loads(tool_call.function.arguments)
                page_or_content_id = arguments.get("page_or_content_id")
                logger.info(
                    f"Loading Confluence page or content with ID: {page_or_content_id}"
                )
                results = json.dumps(
                    self._confluence_manager.load_confluence_page(page_or_content_id)
                )

            if results is not None:
                return self.submit_search_confluence_tool_outputs(
                    thread_id=thread_id,
                    run_id=run_id,
                    tool_call_id=tool_call.id,
                    results=results,
                )

    def submit_search_confluence_tool_outputs(
        self,
        thread_id: str,
        run_id: str,
        tool_call_id: str,
        results: str,
    ) -> Run:
        return self._openai_client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=[
                {
                    "tool_call_id": tool_call_id,
                    "output": results,
                },
            ],
        )

    def get_thread_messages(self, thread_id: str) -> List[ThreadMessage]:
        """
        Get all messages from the OpenAI thread.
        """
        return self._openai_client.beta.threads.messages.list(thread_id=thread_id)

    def extract_relevant_messages(
        self, messages: List[ThreadMessage], message_id: str
    ) -> List[ThreadMessage]:
        """
        Extract relevant messages from the OpenAI thread.
        """
        relevant_messages = []
        for msg in messages:
            if msg.id == message_id:
                break
            relevant_messages.append(msg)
        return relevant_messages
