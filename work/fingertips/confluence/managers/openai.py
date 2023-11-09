from typing import Any, Dict, List

from atlassian import Confluence

from work.fingertips.confluence.agents.openai import OpenAIAgent


class OpenAIManager:
    """
    A manager class for interacting with Confluence and OpenAI.
    """

    def __init__(
        self,
        confluence_base_url: str,
        confluence_username: str,
        confluence_token: str,
    ):
        """
        Initialize the ConfluenceHelper with the necessary credentials.
        """
        self.confluence_base_url = confluence_base_url
        self.confluence_client = Confluence(
            url=confluence_base_url,
            username=confluence_username,
            password=confluence_token,
            cloud=True,
        )
        self._agent = None

    @property
    def agent(self) -> OpenAIAgent:
        if self._agent is None:
            tools = [self.search_confluence, self.load_confluence_page]
            self._agent = OpenAIAgent(self, tools=tools)
        return self._agent

    def get_session_thread_key(self, slack_user: str, slack_channel: str) -> str:
        """
        Get the session thread key based on the slack user or channel.
        """
        if not slack_user and not slack_channel:
            raise ValueError("Either slack_user or slack_channel must be provided")
        return slack_channel if slack_channel is not None else slack_user

    def answer(self, user_query: str, slack_user: str, slack_channel: str) -> str:
        """
        Pass the user_query to the assistant and return the response.
        """
        thread_key = self.get_session_thread_key(slack_user, slack_channel)
        response = self.agent.send_message(user_query, thread_key)
        response = [
            msg.content[0].text.value
            for msg in response
            if msg.content[0].type == "text" and msg.content[0].text.value != ""
        ]
        return ",".join(response)

    def answer_old(self, user_query: str, slack_user: str, slack_channel: str) -> str:
        """
        Answer the user query using Confluence and OpenAI.
        """
        thread_key = self.get_session_thread_key(slack_user, slack_channel)
        cql_query = self.convert_to_cql(user_query, thread_key)
        results = self.confluence_client.cql(cql_query, limit=5)
        return self.formulate_answer(user_query, results, thread_key)

    def search_confluence(self, cql_query: str) -> List[Dict[str, Any]]:
        """
        Search Confluence using the Confluence Query Language (CQL).
        """
        return self.confluence_client.cql(cql_query, limit=5)

    def load_confluence_page(self, page_or_content_id: str) -> str:
        """
        Load a Confluence page using the Confluence REST API.
        """
        result = self.confluence_client.get_page_by_id(
            page_or_content_id, expand="body.view"
        )
        return result["body"]["view"]["value"]

    def convert_to_cql(self, user_query: str, thread_key: str) -> str:
        """
        Convert the user query to a Confluence Query Language (CQL) query.
        """
        # Analyze the query using OpenAI's API
        # Create an Assistant if it doesn't exist
        user_query = f"""
        Ponder the user query below very carefully to identify keywords, remove useless information like the company name, and generate effective, efficient CQL queries.
        Consider synonyms, categories, alternative meanings, and other possibilities.
        For example, if the user asks about databases, you might not find the word 'databases' but may want to search for common types of databases like 'MySQL', 'Postgresql' or 'MsSQL'.
        The CQL queries should search the text and titles use all reasonable permutations of OR, and AND, and parentheses to mimimize API calls.
        Think step by step. We only get one shot at this, so make it count. If the user query is not a valid question, respond as your system message mandates.
        
        USER QUERY: 
        {user_query}
        """

        # Extract relevant information to form a CQL query
        # This is a placeholder for the actual logic to convert response to CQL
        cql_queries = self.send_openai_message_await_responses(
            message=user_query, thread_key=thread_key
        )
        return " OR ".join(
            [f"({query.content[0].text.value})" for query in cql_queries]
        )

    def formulate_answer(
        self,
        user_query: str,
        results: List[Dict[str, Any]],
        thread_key: str,
    ) -> str:
        """
        Formulate an answer based on the results from the CQL query.
        """
        if not results:
            return "I couldn't find any information related to your query."

        # Iterate over results to find an answer
        for result in results:
            ai_query = f"""
                Answer the following question: {user_query}, using only the context provided at the end of this message.
                If there is no answer, respond with 'failure: I'm sorry, inadequate info.'.
                Do not include the question in your response. Use only the context above to answer the question.
                
                Context:
                {result["results"]}
                
            """
            answers = self.send_openai_message_await_responses(ai_query, thread_key)

            # Placeholder for logic to check if the result answers the user's query
            # if self._is_relevant_result(user_query, result):
            for answer in answers:
                page_id = result["id"]
                title = result["title"]
                url = f"{self.confluence_base_url}/wiki/spaces/{result['_expandable']['space']}/pages/{page_id}"
                return f"I found some information that might help you: *{title}* <{url}|View on Confluence>"

        return "I found some information, but nothing that directly answers your question. Please check the search results on Confluence."
