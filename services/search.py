from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import case, or_

from models import ImageAsset

PEOPLE_VALUES = {"any", "yes", "no"}
SORT_VALUES = {"recent", "relevant"}

FOOD_CATEGORY_TERMS = {
    "prepared_food": ["food", "meal", "dish", "plate", "cooked", "cuisine", "grill"],
    "meat_poultry": ["meat", "poultry", "chicken", "beef", "steak", "pork", "lamb", "turkey"],
    "dessert_bakery": ["dessert", "cake", "pastry", "bakery", "bread", "cookie", "sweet", "tart"],
    "fruit_vegetable": ["fruit", "vegetable", "salad", "apple", "banana", "tomato", "greens"],
    "drink": ["drink", "beverage", "coffee", "tea", "juice", "cocktail", "wine", "soda"],
}

ENVIRONMENT_TERMS = {
    "kitchen": ["kitchen", "cuisine", "countertop", "stove", "oven", "sink"],
    "indoor": ["indoor", "inside", "interior", "room", "hall", "studio"],
    "outdoor": ["outdoor", "outside", "nature", "park", "beach", "street", "garden", "sky"],
    "restaurant": ["restaurant", "cafe", "bar", "dining", "bistro", "table service"],
}

FOOD_CATEGORY_OPTIONS = [
    {"value": "", "label": "Toutes les catégories food"},
    {"value": "prepared_food", "label": "Plat préparé"},
    {"value": "meat_poultry", "label": "Viande / volaille"},
    {"value": "dessert_bakery", "label": "Dessert / boulangerie"},
    {"value": "fruit_vegetable", "label": "Fruits / légumes"},
    {"value": "drink", "label": "Boisson"},
]

ENVIRONMENT_OPTIONS = [
    {"value": "", "label": "Tous les environnements"},
    {"value": "kitchen", "label": "Cuisine"},
    {"value": "indoor", "label": "Intérieur"},
    {"value": "outdoor", "label": "Extérieur"},
    {"value": "restaurant", "label": "Restaurant"},
]

PEOPLE_OPTIONS = [
    {"value": "any", "label": "Toutes"},
    {"value": "yes", "label": "Avec personnes"},
    {"value": "no", "label": "Sans personnes"},
]

ORIENTATION_OPTIONS = [
    {"value": "", "label": "Toutes les orientations"},
    {"value": ImageAsset.ORIENTATION_LANDSCAPE, "label": "Paysage"},
    {"value": ImageAsset.ORIENTATION_PORTRAIT, "label": "Portrait"},
    {"value": ImageAsset.ORIENTATION_SQUARE, "label": "Carré"},
]

SORT_OPTIONS = [
    {"value": "recent", "label": "Plus récentes"},
    {"value": "relevant", "label": "Plus pertinentes"},
]


@dataclass(slots=True)
class SearchParams:
    query: str = ""
    people: str = "any"
    food_category: str = ""
    environment: str = ""
    orientation: str = ""
    sort: str = "recent"
    favorites: bool = False


def parse_search_params(args: Mapping[str, str]) -> SearchParams:
    raw_query = (args.get("q") or "").strip()
    raw_people = (args.get("people") or "any").strip().lower()
    raw_food_category = (args.get("food_category") or "").strip().lower()
    raw_environment = (args.get("environment") or "").strip().lower()
    raw_orientation = (args.get("orientation") or "").strip().lower()
    raw_sort = (args.get("sort") or "recent").strip().lower()
    raw_favorites = (args.get("favorites") or "").strip().lower()

    return SearchParams(
        query=raw_query,
        people=raw_people if raw_people in PEOPLE_VALUES else "any",
        food_category=raw_food_category if raw_food_category in FOOD_CATEGORY_TERMS else "",
        environment=raw_environment if raw_environment in ENVIRONMENT_TERMS else "",
        orientation=raw_orientation if raw_orientation in ImageAsset.ORIENTATION_VALUES else "",
        sort=raw_sort if raw_sort in SORT_VALUES else "recent",
        favorites=raw_favorites in {"1", "true", "yes"},
    )


def build_default_search_context() -> dict[str, object]:
    params = SearchParams()
    return _build_context(params=params, tokens=[], results_mode=False)


def search_images(params: SearchParams):
    query = ImageAsset.query
    tokens = _tokenize_keywords(params.query)
    keyword_clauses = [_build_text_match_clause(token) for token in tokens]

    if keyword_clauses:
        query = query.filter(or_(*keyword_clauses))

    if params.people == "yes":
        query = query.filter(ImageAsset.has_people.is_(True))
    elif params.people == "no":
        query = query.filter(ImageAsset.has_people.is_(False))

    if params.food_category:
        query = query.filter(_build_taxonomy_clause(FOOD_CATEGORY_TERMS[params.food_category]))

    if params.environment:
        query = query.filter(_build_taxonomy_clause(ENVIRONMENT_TERMS[params.environment]))

    if params.orientation:
        query = query.filter(ImageAsset.orientation == params.orientation)

    if params.favorites:
        query = query.filter(ImageAsset.is_favorite.is_(True))

    if params.sort == "relevant" and keyword_clauses:
        relevance_score = _build_relevance_score(keyword_clauses)
        query = query.order_by(relevance_score.desc(), ImageAsset.created_at.desc())
    else:
        query = query.order_by(ImageAsset.created_at.desc())

    return query, _build_context(params=params, tokens=tokens, results_mode=True)


def _build_context(*, params: SearchParams, tokens: list[str], results_mode: bool) -> dict[str, object]:
    active_filter_count = 0

    if params.people != "any":
        active_filter_count += 1
    if params.food_category:
        active_filter_count += 1
    if params.environment:
        active_filter_count += 1
    if params.orientation:
        active_filter_count += 1
    if params.favorites:
        active_filter_count += 1

    return {
        "params": params,
        "tokens": tokens,
        "results_mode": results_mode,
        "has_search_criteria": bool(tokens or active_filter_count),
        "active_filter_count": active_filter_count,
        "favorites_active": params.favorites,
        "people_options": PEOPLE_OPTIONS,
        "food_category_options": FOOD_CATEGORY_OPTIONS,
        "environment_options": ENVIRONMENT_OPTIONS,
        "orientation_options": ORIENTATION_OPTIONS,
        "sort_options": SORT_OPTIONS,
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


def _build_taxonomy_clause(terms: list[str]):
    return or_(*[_build_text_match_clause(term) for term in terms])


def _build_relevance_score(keyword_clauses: list):
    score = case((keyword_clauses[0], 1), else_=0)
    for keyword_clause in keyword_clauses[1:]:
        score = score + case((keyword_clause, 1), else_=0)
    return score
