"""Question resolution and ambiguity handling for natural-language queries.

Layer 6 module: translates natural language and DatasetProfile into a typed ResolvedQuestion.
Rejects unanswerable or out-of-scope questions deterministically without calling LLMs.
"""

from __future__ import annotations

import re

from da_agent.contracts.models import (
    AmbiguityDecision,
    DatasetProfile,
    FilterSpec,
    PeriodSpec,
    ResolvedQuestion,
    SemanticType,
)

# Common aliases mapping user phrases to potential canonical column concepts
COLUMN_ALIASES: dict[str, str] = {
    "sales": "Sales",
    "revenue": "Sales",
    "turnover": "Sales",
    "profit": "Profit",
    "profits": "Profit",
    "earnings": "Profit",
    "margin": "Profit",
    "quantity": "Quantity",
    "quantities": "Quantity",
    "volume": "Quantity",
    "units": "Quantity",
    "discount": "Discount",
    "discounts": "Discount",
    "date": "Order Date",
    "dates": "Order Date",
    "order date": "Order Date",
    "ship date": "Ship Date",
    "shipping date": "Ship Date",
    "ship mode": "Ship Mode",
    "shipping mode": "Ship Mode",
    "segment": "Segment",
    "segments": "Segment",
    "country": "Country",
    "city": "City",
    "cities": "City",
    "state": "State",
    "states": "State",
    "postal code": "Postal Code",
    "zip code": "Postal Code",
    "zip": "Postal Code",
    "region": "Region",
    "regions": "Region",
    "category": "Category",
    "categories": "Category",
    "sub-category": "Sub-Category",
    "subcategory": "Sub-Category",
    "sub category": "Sub-Category",
    "sub-categories": "Sub-Category",
    "customer": "Customer Name",
    "customers": "Customer Name",
    "customer name": "Customer Name",
    "product": "Product Name",
    "products": "Product Name",
    "product name": "Product Name",
}

OUT_OF_SCOPE_PATTERNS = [
    (
        re.compile(
            r"\b(machine learning|train a model|train model|classifier|neural net|clustering)\b",
            re.IGNORECASE,
        ),
        "Machine learning model training is outside the system's analytical scope (PROJECT_SCOPE.md).",
    ),
    (
        re.compile(r"\b(forecast|predict|prediction|future|projected|will sell)\b", re.IGNORECASE),
        "Forecasting and predictive modeling are outside the system's analytical scope (PROJECT_SCOPE.md).",
    ),
    (
        re.compile(r"\b(what caused|why did|cause of|effect of|causal)\b", re.IGNORECASE),
        "Causal claims and root-cause attribution are outside the system's analytical scope (PROJECT_SCOPE.md).",
    ),
]

NONEXISTENT_CONCEPTS = [
    re.compile(r"\b(salary|salaries|employee|employees|payroll|wage|wages|bonus)\b", re.IGNORECASE),
    re.compile(r"\b(inventory|warehouse|stock level|stock levels|stock price)\b", re.IGNORECASE),
    re.compile(r"\b(churn|retention rate|attrition)\b", re.IGNORECASE),
    re.compile(r"\b(cogs|cost of goods|cost price|tax rate|vat)\b", re.IGNORECASE),
    re.compile(r"\b(weather|temperature|climate)\b", re.IGNORECASE),
]


def map_columns(text: str, profile: DatasetProfile) -> list[str]:
    """Map user phrases in question text to real column names in DatasetProfile.

    Any column not present in the profile is strictly excluded.
    """
    valid_cols_by_lower = {col.name.lower(): col.name for col in profile.columns}
    normalized_text = re.sub(r"[^\w\s-]", " ", text.lower())
    found_cols: dict[str, str] = {}

    # 1. Check multi-word and single-word aliases
    sorted_aliases = sorted(COLUMN_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for phrase, target_col in sorted_aliases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, normalized_text) and target_col in [c.name for c in profile.columns]:
            found_cols[target_col] = target_col

    # 2. Check exact column names in profile
    for lower_name, real_name in valid_cols_by_lower.items():
        pattern = r"\b" + re.escape(lower_name) + r"\b"
        if re.search(pattern, normalized_text):
            found_cols[real_name] = real_name

    return list(found_cols.values())


def _extract_quoted_values(text: str) -> list[str]:
    """Extract quoted string literals from question."""
    single_quotes = re.findall(r"'([^']+)'", text)
    double_quotes = re.findall(r'"([^"]+)"', text)
    return single_quotes + double_quotes


def _extract_dates(text: str) -> list[str]:
    """Extract ISO formatted dates (YYYY-MM-DD)."""
    return re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)


def resolve_question(question: str, profile: DatasetProfile) -> ResolvedQuestion:
    """Resolve natural-language question against a DatasetProfile into a ResolvedQuestion."""
    q_stripped = question.strip()

    # 1. Check out-of-scope analytical requests
    for pattern, reason in OUT_OF_SCOPE_PATTERNS:
        if pattern.search(q_stripped):
            return ResolvedQuestion(
                question_text=q_stripped,
                intent="unanswerable",
                answerable=False,
                decline_reason=reason,
            )

    # 2. Check explicitly nonexistent concepts/data
    for pattern in NONEXISTENT_CONCEPTS:
        if pattern.search(q_stripped):
            return ResolvedQuestion(
                question_text=q_stripped,
                intent="unanswerable",
                answerable=False,
                decline_reason="The question refers to concepts or data that do not exist in the dataset profile (unanswerable).",
            )

    # 3. Check for completely vague / content-free questions
    words = re.findall(r"\b\w+\b", q_stripped.lower())
    stop_words = {
        "what",
        "is",
        "the",
        "tell",
        "me",
        "something",
        "interesting",
        "about",
        "show",
        "how",
        "a",
        "an",
        "of",
        "in",
    }
    significant_words = [w for w in words if w not in stop_words]
    mapped_columns = map_columns(q_stripped, profile)

    if len(significant_words) < 2 and not mapped_columns:
        return ResolvedQuestion(
            question_text=q_stripped,
            intent="unanswerable",
            answerable=False,
            decline_reason="The question is too ambiguous or vague to determine an analytical objective.",
        )

    # 4. Detect Intent
    q_lower = q_stripped.lower()
    ambiguity_decisions: list[AmbiguityDecision] = []
    grouping: list[str] = []
    filters: list[FilterSpec] = []
    period: PeriodSpec | None = None
    metric: str | None = None

    # Check multistep: an explicit filter condition combined with ranking or grouping
    has_filter_condition = bool(
        re.search(r"\b(in the|for orders shipped|where|shipped via)\b", q_lower)
    )
    has_ranking = bool(re.search(r"\b(top|bottom|highest|lowest|best|worst|rank)\b", q_lower))
    has_grouping = bool(
        re.search(r"\b(for each|across each|per category|per segment|per region)\b", q_lower)
    )

    if has_filter_condition and (has_ranking or has_grouping):
        intent = "multistep"
    elif re.search(r"\b(anomaly|anomalies|outlier|outliers|iqr)\b", q_lower):
        intent = "detect_anomalies_iqr"
    elif re.search(r"\b(correlation|relationship between|pearson)\b", q_lower):
        intent = "correlation"
    elif re.search(r"\b(share|contribution|proportion|percentage of total)\b", q_lower):
        intent = "segment_contribution"
    elif re.search(r"\b(trend|direction|monthly trend|quarterly trend)\b", q_lower):
        intent = "trend"
    elif re.search(r"\b(compare|base period|comparison period)\b", q_lower):
        intent = "period_compare"
    elif has_ranking:
        intent = "rank"
    elif has_grouping or re.search(r"\bby\b", q_lower):
        intent = "group_aggregate"
    elif has_filter_condition or re.search(r"\b(how many rows|filter)\b", q_lower):
        intent = "filter"
    else:
        intent = "group_aggregate"

    # 5. Extract Metric
    numeric_measures = [
        c.name for c in profile.columns if c.semantic_type == SemanticType.NUMERIC_MEASURE
    ]
    # Preserve order of appearance in question
    referenced_measures = [c for c in mapped_columns if c in numeric_measures]

    agg = "sum"
    if re.search(r"\b(average|mean|avg)\b", q_lower):
        agg = "mean"
    elif re.search(r"\b(count|how many rows)\b", q_lower):
        agg = "count"

    if intent == "correlation" and len(referenced_measures) >= 2:
        metric = f"corr({referenced_measures[0]}, {referenced_measures[1]})"
    elif intent == "correlation" and len(referenced_measures) == 1:
        metric = f"corr({referenced_measures[0]})"
    elif referenced_measures:
        chosen_metric_col = referenced_measures[0]
        if re.search(r"\b(count|how many rows)\b", q_lower):
            metric = "count()"
        else:
            metric = f"{agg}({chosen_metric_col})"
            if not re.search(r"\b(total|sum|average|mean|avg)\b", q_lower):
                ambiguity_decisions.append(
                    AmbiguityDecision(
                        field="metric",
                        issue="No aggregation specified for metric",
                        decision=f"Defaulted to sum({chosen_metric_col})",
                        assumption=f"Sum is standard default aggregation for {chosen_metric_col}",
                    )
                )
    elif re.search(r"\b(count|how many rows|row count)\b", q_lower):
        metric = "count()"
    else:
        if not mapped_columns:
            return ResolvedQuestion(
                question_text=q_stripped,
                intent="unanswerable",
                answerable=False,
                decline_reason="Could not identify any valid dataset column or metric in the question.",
            )

    # 6. Extract Grouping
    cat_columns = [
        c.name
        for c in profile.columns
        if c.semantic_type in (SemanticType.CATEGORY, SemanticType.IDENTIFIER)
    ]
    for col in mapped_columns:
        if col in cat_columns and col not in [f.column for f in filters]:
            grouping.append(col)

    # 7. Extract Filters (quoted strings and specific recognized categories)
    quoted_values = _extract_quoted_values(q_stripped)
    for val in quoted_values:
        matched_col = None
        for col_profile in profile.columns:
            if col_profile.examples and any(
                str(val).lower() == str(ex).lower() for ex in col_profile.examples
            ):
                matched_col = col_profile.name
                break
        if not matched_col:
            val_lower = val.lower()
            if val_lower in ["first class", "second class", "standard class", "same day"]:
                matched_col = "Ship Mode"
            elif val_lower in ["technology", "furniture", "office supplies"]:
                matched_col = "Category"
            elif val_lower in ["west", "east", "central", "south"]:
                matched_col = "Region"
            elif val_lower in ["consumer", "corporate", "home office"]:
                matched_col = "Segment"

        if matched_col:
            filters.append(FilterSpec(column=matched_col, operator="eq", value=val))
            if matched_col in grouping:
                grouping.remove(matched_col)

    # 8. Extract Period if dates exist
    dates = _extract_dates(q_stripped)
    date_col = next(
        (c.name for c in profile.columns if c.semantic_type == SemanticType.DATE),
        "Order Date",
    )
    if len(dates) >= 4:
        period = PeriodSpec(
            column=date_col,
            start=dates[0],
            end=dates[3],
            grain="year",
        )
    elif len(dates) >= 2:
        period = PeriodSpec(
            column=date_col,
            start=dates[0],
            end=dates[1],
            grain="year" if "year" in q_lower else "month",
        )
    elif "2017" in q_lower:
        period = PeriodSpec(
            column=date_col,
            start="2017-01-01",
            end="2017-12-31",
            grain="month" if "month" in q_lower else "year",
        )

    return ResolvedQuestion(
        question_text=q_stripped,
        intent=intent,
        metric=metric,
        period=period,
        grouping=grouping,
        filters=filters,
        ambiguity_decisions=ambiguity_decisions,
        answerable=True,
    )
