from typing import Any, Dict, Optional, cast

# Ignore plomp import type error with a type: ignore comment
import plomp  # type: ignore


@plomp.wrap_prompt_fn()
def prompt_llm(prompt: str, *, model: str, response_schema: dict[str, Any], system_prompt: str) -> dict[str, Any]:
    return f"<LLM RESPONSE model={model}>"


# Fix the return value type
def sample_response(model: str, prompt: str, temperature: Optional[float] = None) -> Dict[str, Any]:
    # Assuming the function should return a dict instead of str
    response = plomp.sample(model, prompt, temperature=temperature)
    if isinstance(response, str):
        return {"response": response}
    return cast(Dict[str, Any], response)
