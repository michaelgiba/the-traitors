import sys
from collections.abc import Callable
from functools import partial
from typing import Any

import plomp  # type: ignore

from reality_show_bench._groq import GROQ_VALID_MODELS, groq_completion
from reality_show_bench._local import local_phi4_completion

MODEL_TO_PROMPT_FN: dict[str, Callable] = {
    "local-phi4": local_phi4_completion,
    **{f"groq-{mn}": partial(groq_completion, model=mn) for mn in GROQ_VALID_MODELS},
}


@plomp.wrap_prompt_fn(capture_tag_kwargs={"model"})
def prompt_llm(prompt: str, *, model: str, response_schema: dict[str, Any], system_prompt: str) -> str:
    sys.stderr.write(f"Prompting LLM with model: {model}\n")
    sys.stderr.flush()

    try:
        raw_response = MODEL_TO_PROMPT_FN[model](
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.9,
            response_json_schema=response_schema,
        )
        sys.stderr.write(f"{model}\n")
        sys.stderr.flush()

        # Ensure we're only returning the content string, not the whole response object
        response_content = raw_response["choices"][0]["message"]["content"]
        return str(response_content)
    except Exception as e:
        sys.stderr.write(f"Error during LLM prompt: {str(e)}\n")
        sys.stderr.flush()
        raise
