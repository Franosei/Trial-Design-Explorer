import os


def configured_model_name() -> str | None:
    return os.getenv("OPENAI_MODEL")


def has_openai_config() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def generate_chat_completion(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 900,
) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    target_model = model or configured_model_name() or "gpt-4o-mini"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message.content
        if isinstance(message, list):
            return "".join(str(part) for part in message).strip() or None
        return message.strip() if message else None
    except Exception:
        pass

    try:
        import openai

        openai.api_key = api_key
        openai.api_base = base_url
        response = openai.ChatCompletion.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

