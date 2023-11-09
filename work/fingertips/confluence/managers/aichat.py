import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from atlassian import Confluence
from pydantic import BaseModel
from simpleaichat import AIChat

CONTEXT_LIMIT = os.getenv("OPENAI_MODEL_CONTEXT_LIMIT", 100000)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", 100000)

logger = logging.getLogger(__name__)


class cql_output(BaseModel):
    """Output schema for Confluence Query Language (CQL) queries."""

    cql: Optional[List[str]] = None
    failure: Optional[str] = None
    thoughts: Optional[str] = None
    keywords: Optional[str] = None
    synonyms: Optional[str] = None
    answer: Optional[str] = None
    warning: Optional[str] = None


class answer_output(BaseModel):
    """Output schema for answers."""

    failure: Optional[str] = None
    thoughts: Optional[str] = None
    keywords: Optional[str] = None
    synonyms: Optional[str] = None
    answer: Optional[str] = None
    warning: Optional[str] = None


class AIChatManager:
    def __init__(
        self,
        user_query: str,
        confluence_base_url: str,
        confluence_username: str,
        confluence_token: str,
    ):
        self.confluence_client = Confluence(
            url=confluence_base_url,
            username=confluence_username,
            password=confluence_token,
            cloud=True,
        )
        self.user_query = user_query
        path = Path(__file__).parent / "prompt.md"
        self.system_prompt = path.read_text()

    def get_ai(self) -> AIChat:
        logger.info("Generating response for user query")
        params = {"temperature": 0.0, "model": OPENAI_MODEL, "max_tokens": 1000}
        ai = AIChat(
            id="qna",
            params=params,
            system=self.system_prompt,
        )
        return ai

    def generate_response(
        self,
        failed_cql: Optional[List[str]] = [],
        failure_count: int = 0,
    ) -> str:
        ai = self.get_ai()

        user_query = f"""
        Ponder the user query below very carefully to identify keywords, remove useless information like the company name, and generate effective, efficient CQL queries.
        Consider synonyms, categories, alternative meanings, and other possibilities.
        For example, if the user asks about databases, you might not find the word 'databases' but may want to search for common types of databases like 'MySQL', 'Postgresql' or 'MsSQL'.
        The CQL queries should search the text and titles use all reasonable permutations of OR, and AND, and parentheses to mimimize API calls.
        Think step by step. We only get one shot at this, so make it count. If the user query is not a valid question, respond as your system message mandates.
        
        USER QUERY: 
        {self.user_query}
        """
        if failed_cql:
            user_query += """
                FORBIDDEN QUERIES: 
                The following CQL queries returned no results. Do not use them:
                """ + "\n- ".join(
                failed_cql
            )

        ai_response = ai(user_query, id="qna", output_schema=cql_output)

        if warning := ai_response.get("warning"):
            logger.warning(warning)
            return "I'm sorry, I am unable to answer your request. Please paraphrase your question. What information do you seek?"

        if failure := ai_response.get("failure"):
            logger.error(failure)
            return "I'm sorry, I am unable to answer your request. Please paraphrase your question. What information do you seek?"

        if answer := ai_response.get("answer"):
            logger.info(answer)
            return answer

        if cql := ai_response.get("cql"):
            logger.info("Number of cql queries: " + str(len(cql)))
            query = " OR ".join([f"({cql})" for cql in cql])
            response = self.process_query(query)

            if response == "":
                failure_count += 1
                failed_cql.extend(cql)
                if failure_count < 2:
                    response = self.generate_response(failed_cql, failure_count)
            else:
                return response

        return "I'm sorry, I am unable to answer your request. Please paraphrase your question. What information do you seek?"

    def process_query(self, query):
        """Processes a query with the Confluence API."""
        logger.info(f"Processing query: {query}")
        with ThreadPoolExecutor(max_workers=5) as results_executor:
            results = self.confluence_client.cql(query, limit=5)

            answers = list(
                results_executor.map(self.process_result, results["results"])
            )
            answers = [answer for answer in answers if answer is not None]
            return "\n".join(answers)

    def process_result(self, result):
        """Processes the result from the Confluence API."""
        expanded_result = self.confluence_client.get_page_by_id(
            result["content"]["id"], expand="body.view"
        )
        content_body = expanded_result["body"]["view"]["value"]
        # Strip any HTML tags from content_body
        content_body = re.sub("<.*?>", "", content_body)
        # Chunk content body if necessary
        chunks = [
            content_body[i : i + CONTEXT_LIMIT]
            for i in range(0, len(content_body), CONTEXT_LIMIT)
        ]

        # Initialize ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5) as chunk_executor:
            # Process each chunk with OpenAI GPT-4 using ThreadPoolExecutor
            answers = list(chunk_executor.map(self.process_chunk, chunks))
            answers = [
                f'Page ID{result["content"]["id"]}: {answer}, Refs: {expanded_result["_links"]["webui"]}'
                for answer in answers
                if answer is not None
            ]

            if answers:
                return "\n".join(answers)
            else:
                return None

    def process_chunk(self, chunk):
        """Processes a chunk with OpenAI GPT-4."""
        ai_query = f"""
            Answer the following question: {self.user_query}, using only the context provided at the end of this message.
            If there is no answer, respond with 'failure: I'm sorry, inadequate info.'.
            Do not include the question in your response. Use only the context above to answer the question.
            
            Context:
            {chunk}
            
        """
        ai = self.get_ai()
        ai_response = ai(ai_query, id="qna", output_schema=answer_output)

        if warning := ai_response.get("warning"):
            logger.warning(warning)

        if failure := ai_response.get("failure"):
            logger.error(failure)

        if answer := ai_response.get("answer"):
            return answer
