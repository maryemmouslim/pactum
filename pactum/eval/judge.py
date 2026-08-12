from typing import cast

from pydantic import BaseModel, Field

from pactum.llm import get_llm, invoke_structured


class JudgeVerdict(BaseModel):
    correct: bool
    reasoning: str = Field(description="One-sentence explanation of the verdict.")


def judge_hypothesis(expected_cause: str, actual_hypothesis: str) -> JudgeVerdict:
    """Score whether an agent's top hypothesis correctly identifies the true cause.

    Hypothesis.description is free LLM text with no fixed vocabulary, so this
    can't be a keyword or exact-match comparison -- a second LLM call judges
    whether the two descriptions are pointing at the same underlying cause,
    paraphrasing allowed.
    """
    # "reasoning", not "fast" -- on judgment calls this nuanced, the smaller
    # model's own stated reasoning repeatedly contradicted its boolean
    # verdict (e.g. calling the core mechanism correct in its explanation,
    # then still returning correct=False).
    llm = get_llm("reasoning").with_structured_output(JudgeVerdict)
    prompt = (
        "You are grading whether an automated data-incident investigation agent "
        "correctly identified the true cause of an incident.\n\n"
        f"True cause:\n{expected_cause}\n\n"
        f"Agent's proposed explanation:\n{actual_hypothesis}\n\n"
        "Does the agent's explanation correctly identify the true cause? Grade "
        "on the core mechanism only (e.g. 'a column is missing' and 'a column "
        "was removed' are the same cause; 'the distribution shifted' is correct "
        "even if it doesn't guess *why* the distribution shifted, since that "
        "deeper reason usually isn't observable from the data alone). Two "
        "specific things to NOT penalize: (1) the agent omitting speculative "
        "contributing detail that the true cause mentions as one possible "
        "example, and (2) the agent tacking on its own unconfirmed guess about "
        "*why* the core cause happened, as long as the core cause itself is "
        "correctly named -- an extra wrong guess bolted onto a correct core "
        "claim does not make the core claim wrong. Only fail it if the core "
        "mechanism itself is a different, wrong one, or is too vague to tell "
        "what it thinks happened at all. Respond with `correct` (true/false) "
        "and a one-sentence `reasoning`."
    )
    return cast(JudgeVerdict, invoke_structured(llm, prompt))
