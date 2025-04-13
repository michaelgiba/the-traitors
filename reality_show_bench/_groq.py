import os
import time

import requests

_GROQ_APIKEY = os.environ.get("GROQ_API_KEY")

GROQ_VALID_MODELS = {
    "deepseek-r1-distill-llama-70b",
    "deepseek-r1-distill-qwen-32b",
    "gemma2-9b-it",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen-qwq-32b",
    "qwen-2.5-32b",
}


def _add_json_schema_to_prompt(prompt: str, response_json_schema: dict | None) -> str:
    if response_json_schema is None:
        return prompt

    return f"""Respond to the following prompt in JSON format.
    Confirm to this json schema: {response_json_schema}

    {prompt}"""


MAX_RETRIES: int = 12
RETRY_DELAY_SEC: float = 5.0


def groq_completion(
    prompt: str,
    system_prompt: str,
    temperature: float,
    *,
    model: str,
    response_json_schema: dict | None = None,
) -> str:
    prompt = _add_json_schema_to_prompt(prompt, response_json_schema=response_json_schema)

    for attempt in range(MAX_RETRIES):
        try:
            result = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_GROQ_APIKEY}",
                },
                json={
                    "model": model,  # Use the passed model parameter
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": temperature,
                    **({"response_format": {"type": "json_object"}} if response_json_schema is not None else {}),
                },
            )
            result.raise_for_status()
            response_json = result.json()

            # Sometimes Groq returns valid json that does't conform, if so we fail and retry.
            if response_json_schema:
                for field in response_json_schema["required"]:
                    assert field in response_json["choices"][0]["message"]["content"]

            return response_json
        except (requests.RequestException, ValueError, KeyError) as e:
            import sys

            print(f"Error during API call (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}", file=sys.stderr)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY_SEC * (attempt + 1))

    # This line should never be reached due to the raise in the last iteration
    # but is included to satisfy return type requirements
    raise RuntimeError("Failed to get completion after all retries")
