"""Search and ranking for chat summaries."""

import json
import re
from typing import Optional

from .summarize import run_agent


def rank_summaries(
    description: str,
    summaries: list[dict],
    model: str = "grok",
    max_results: int = 3,
    use_llm: bool = False,
) -> list[dict]:
    """Rank summaries by relevance to the description."""
    if not summaries:
        return []
    
    # Fast keyword matching by default
    if not use_llm:
        return _fallback_ranking(description, summaries, max_results)
    
    # LLM ranking when --smart flag is used
    candidates = [
        {
            "id": s["conversation_id"],
            "summary": s["summary_text"],
            "name": s.get("chat_name", "Unnamed"),
            "directory": s.get("chat_directory", "Unknown"),
        }
        for s in summaries
    ]
    
    prompt = f"""Rank these chats by relevance to: "{description}"

{json.dumps(candidates, indent=2)}

Return JSON array with relevant chats only (max {max_results}):
[{{"id": "...", "reason": "..."}}]

If none match, return: []"""

    response = run_agent(prompt, model, timeout=60)
    
    if response:
        ranked = _parse_ranking_response(response, summaries)
        if ranked:
            return ranked[:max_results]
    
    return _fallback_ranking(description, summaries, max_results)


def _parse_ranking_response(response: str, summaries: list[dict]) -> list[dict]:
    """Parse the LLM ranking response."""
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if not json_match:
        return []
    
    try:
        ranked_ids = json.loads(json_match.group())
    except json.JSONDecodeError:
        return []
    
    summary_map = {s["conversation_id"]: s for s in summaries}
    
    results = []
    for item in ranked_ids:
        if isinstance(item, dict) and "id" in item:
            conv_id = item["id"]
            if conv_id in summary_map:
                result = summary_map[conv_id].copy()
                result["reason"] = item.get("reason", "")
                results.append(result)
    
    return results


def _fallback_ranking(description: str, summaries: list[dict], max_results: int) -> list[dict]:
    """Simple keyword-based fallback ranking."""
    keywords = set(description.lower().split())
    
    scored = []
    for s in summaries:
        text = f"{s.get('summary_text', '')} {s.get('chat_name', '')} {s.get('chat_directory', '')}".lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, s))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    
    results = []
    for score, s in scored[:max_results]:
        result = s.copy()
        result["reason"] = "Keyword match"
        results.append(result)
    
    return results
