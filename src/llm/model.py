import os
import re
import time
from typing import Any, Dict, List, Optional, Union

import requests

from llm.prompts import prompts_fewshot_parse
from runner.logger import Logger


def model_chose(step: str, model: str = "gpt-4o-mini") -> "BaseReq":
    if "/" in model:
        return OpenRouterReq(step, model)
    if model.startswith("gpt") or model.startswith("claude") or model.startswith("gemini"):
        return OpenAICompatibleReq(step, model)
    if model.startswith("qwen"):
        return OpenRouterReq(step, model)
    return OpenAICompatibleReq(step, model)


class BaseReq:
    def __init__(self, step: str, model: str) -> None:
        self.cost = 0.0
        self.model = model
        self.step = step

    def log_record(self, prompt_text: str, output: Any) -> None:
        logger = Logger()
        logger.log_conversation(prompt_text, "Human", self.step)
        logger.log_conversation(output, "AI", self.step)

    def fewshot_parse(self, question: str, evidence: str, sql: str) -> str:
        prompt = prompts_fewshot_parse().parse_fewshot.format(question=question, sql=sql)
        response = self.get_ans(prompt)
        response = response.replace("```", "").strip()
        response = response.split("#SQL:")[0]
        return self.convert_table(response, sql)

    def convert_table(self, content: str, sql: str) -> str:
        aliases = re.findall(r" ([^ ]*) +AS +([^ ]*)", sql)
        header, select_and_values = content.split("#SELECT:")
        select_part, value_part = select_and_values.split("#values:")
        for table, alias in aliases:
            select_part = select_part.replace(f"{alias}.", f"{table}.")
        return f"{header}#SELECT:{select_part}#values:{value_part}"

    def get_ans(self, messages: str, temperature: float = 0.0, top_p: Optional[float] = None, n: int = 1, single: bool = True, **kwargs: Any) -> Union[str, List[Dict[str, Any]]]:
        raise NotImplementedError


class OpenAICompatibleReq(BaseReq):
    def __init__(self, step: str, model: str = "gpt-4o-mini") -> None:
        super().__init__(step, model)
        self.api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    def _request(
        self,
        messages: str,
        temperature: float,
        top_p: Optional[float],
        n: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI-compatible models.")
        optional_keys = {
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "response_format",
            "seed",
            "tools",
            "tool_choice",
        }
        extras = {k: v for k, v in kwargs.items() if k in optional_keys}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an SQL expert, skilled in handling SQL-related tasks."},
                {"role": "user", "content": messages},
            ],
            "max_tokens": 800,
            "temperature": temperature,
            "n": n,
            **extras,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        response = requests.post(
            self.api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def get_ans(
        self,
        messages: str,
        temperature: float = 0.0,
        top_p: Optional[float] = None,
        n: int = 1,
        single: bool = True,
        **kwargs: Any,
    ) -> Union[str, List[Dict[str, Any]]]:
        attempts = 0
        last_error: Optional[Exception] = None
        while attempts < 8:
            try:
                result = self._request(messages, temperature, top_p, n, **kwargs)
                choices = result.get("choices", [])
                if n == 1 and single:
                    content = choices[0]["message"]["content"]
                else:
                    content = choices
                if self.step != "prepare_train_queries":
                    self.log_record(messages, content)
                return content
            except Exception as exc:
                attempts += 1
                last_error = exc
                time.sleep(2)
        raise RuntimeError(f"Model request failed after retries: {last_error}")


class OpenRouterReq(BaseReq):
    def __init__(self, step: str, model: str) -> None:
        super().__init__(step, model)
        self.api_url = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.site_url = os.getenv("OPENROUTER_SITE_URL", "")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "OpenSearch-SQL")
        self.timeout = float(os.getenv("OPENROUTER_TIMEOUT", "45"))

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouter models.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name
        return headers

    def _request(
        self,
        messages: str,
        temperature: float,
        top_p: Optional[float],
        n: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        optional_keys = {
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "response_format",
            "seed",
            "tools",
            "tool_choice",
        }
        extras = {k: v for k, v in kwargs.items() if k in optional_keys}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an SQL expert, skilled in handling SQL-related tasks."},
                {"role": "user", "content": messages},
            ],
            "max_tokens": 800,
            "temperature": temperature,
            "n": n,
            **extras,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        response = requests.post(self.api_url, json=payload, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_ans(
        self,
        messages: str,
        temperature: float = 0.0,
        top_p: Optional[float] = None,
        n: int = 1,
        single: bool = True,
        **kwargs: Any,
    ) -> Union[str, List[Dict[str, Any]]]:
        attempts = 0
        last_error: Optional[Exception] = None
        while attempts < 4:
            try:
                result = self._request(messages, temperature, top_p, n, **kwargs)
                choices = result.get("choices", [])
                if n == 1 and single:
                    content = choices[0]["message"]["content"]
                else:
                    content = choices
                if self.step != "prepare_train_queries":
                    self.log_record(messages, content)
                return content
            except Exception as exc:
                attempts += 1
                last_error = exc
                time.sleep(2)
        raise RuntimeError(f"OpenRouter request failed after retries: {last_error}")
