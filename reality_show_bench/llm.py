from typing import Any

import plomp


@plomp.wrap_prompt_fn()
def prompt_llm(prompt: str, *, model: str, response_schema: dict[str, Any], system_prompt: str) -> dict[str, Any]:
    return f"<LLM RESPONSE model={model}>"
