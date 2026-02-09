# backend/nlp.py
import os
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key=os.getenv("AI_FOUNDRY_API_KEY"),
    azure_endpoint=os.getenv("AI_FOUNDRY_ENDPOINT"),
    api_version="2024-02-01"
)

def extract_intent(user_input: str):
    prompt = f"""
    Extract intent and resource from the user input.
    Return JSON only.

    Input: "{user_input}"

    Example output:
    {{
      "intent": "create",
      "resource": "namespace"
    }}
    """

    response = client.chat.completions.create(
        model=os.getenv("AI_MODEL_NAME"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return eval(response.choices[0].message.content)
