from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import or_

from models import ImageAsset


@dataclass(slots=True)
class SearchParams:
    query: str = ""


def parse_search_params(args: Mapping[str, str]) -> SearchParams:
    raw_query = (args.get("q") or "").strip()
    return SearchParams(query=raw_query)


def build_default_search_context() -> dict[str, object]:
    params = SearchParams()
    return _build_context(params=params, tokens=[], results_mode=False)


def search_images(params: SearchParams):
    query = ImageAsset.query
    tokens = _tokenize_keywords(params.query)
    keyword_clauses = [_build_text_match_clause(token) for token in tokens]

    if keyword_clauses:
        query = query.filter(or_(*keyword_clauses))

    query = query.order_by(ImageAsset.created_at.desc())

    return query, _build_context(params=params, tokens=tokens, results_mode=True)


def _build_context(*, params: SearchParams, tokens: list[str], results_mode: bool) -> dict[str, object]:
    return {
        "params": params,
        "tokens": tokens,
        "results_mode": results_mode,
    }


def _tokenize_keywords(query: str) -> list[str]:
    raw_tokens = re.split(r"[\s,;]+", query.lower())
    return [token.strip() for token in raw_tokens if token.strip()]


def _build_text_match_clause(term: str):
    like_term = f"%{term}%"
    return or_(
        ImageAsset.tags.ilike(like_term),
        ImageAsset.description.ilike(like_term),
    )
