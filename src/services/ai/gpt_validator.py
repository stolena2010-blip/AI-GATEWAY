"""
GPT Validator — GPT-4o-mini text-based validation of DI output.
================================================================

Not images — text only. Very cheap.
Uses GPT-4o-mini to validate and correct DI extraction results.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def validate_extraction(
    di_result: Dict[str, Any],
    prompts_folder: str = "prompts/invoices",
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """Validate and correct DI extraction using GPT-4o-mini.

    Takes the raw DI output (fields + tables + text) and asks GPT
    to validate, correct, and fill in missing data.

    Returns the validated/corrected result dict.
    """
    from openai import AzureOpenAI
    from src.services.ai.model_runtime import ModelRuntimeConfig

    runtime = ModelRuntimeConfig.from_env()

    client = AzureOpenAI(
        azure_endpoint=runtime.endpoint,
        api_key=runtime.api_key,
        api_version=runtime.api_version,
    )

    # Load validation prompt
    prompt_path = Path(prompts_folder) / "validate.txt"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
    else:
        system_prompt = (
            "You are a data validation assistant. "
            "Given raw extracted data from a document, validate and correct it. "
            "Return a JSON object with the corrected fields."
        )

    # Build user message with DI output
    user_message = json.dumps(di_result, ensure_ascii=False, indent=2)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        validated = json.loads(content)

        # Merge validated fields back into original
        di_result["validated_fields"] = validated
        di_result["validation_model"] = model

        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        logger.info(
            f"GPT validation complete: {tokens_in} in / {tokens_out} out tokens"
        )

        return di_result

    except Exception as e:
        logger.error(f"GPT validation failed: {e}")
        di_result["validation_error"] = str(e)
        return di_result
