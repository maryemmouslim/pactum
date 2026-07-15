from langchain_groq import ChatGroq
from pydantic import SecretStr

from pactum.settings import settings


def get_llm(role: str = "reasoning") -> ChatGroq:
    """Return a configured Groq model for a given agent role.

    role: "reasoning" (causal agent, contract gen) or "fast" (classification, critique).
    """
    model = "llama-3.1-8b-instant" if role == "fast" else "llama-3.3-70b-versatile"
    return ChatGroq(
        model=model,
        api_key=SecretStr(settings.groq_api_key),
        temperature=0.1,
    )
