"""Debate chamber topic library — preset questions for the agent crew.

Voice:
  crew debates / crew debate list
  crew debate random
  crew debate tech|money|career|lifestyle|ai|gaming|health|home|philadelphi a
  crew debate 12
  crew debate <freeform question>
"""

from __future__ import annotations

import random
from typing import Iterable

# category -> list of debate questions (should/ought framing works best)
DEBATE_TOPICS: dict[str, list[str]] = {
    "tech": [
        "Should I buy an RTX 5090 this year?",
        "Should I upgrade to a 4K OLED monitor right now?",
        "Should I switch from Windows to a Linux daily driver?",
        "Should I buy a MacBook Pro for development?",
        "Should I replace my phone this cycle or wait another year?",
        "Should I buy mechanical keyboard switches again or stick with what I have?",
        "Should I build a new PC or upgrade this one piece by piece?",
        "Should I get a second ultrawide monitor for the desk?",
        "Should I move my main storage to a larger NVMe drive now?",
        "Should I buy a NAS for home backups?",
        "Should I cancel cloud storage and self-host everything?",
        "Should I buy smart glasses this year?",
        "Should I get a dedicated streaming PC?",
        "Should I invest in a better microphone before a better camera?",
        "Should I buy the latest GPU or a used previous-gen flagship?",
    ],
    "ai": [
        "Should I rely on local LLMs instead of paid cloud AI?",
        "Should I let AI write most of my first drafts?",
        "Should I automate more of my business with agents this quarter?",
        "Should I pay for Claude / GPT Pro long-term?",
        "Should I open-source my Jarvis customizations?",
        "Should I train a personal fine-tune on my own notes?",
        "Should I let AI handle customer emails with light supervision?",
        "Should I replace junior freelance work with agent pipelines?",
        "Should I build products that wrap foundation models?",
        "Should I pause AI tooling spend until ROI is clearer?",
    ],
    "money": [
        "Should I buy a house in the next 18 months?",
        "Should I rent longer and invest the difference?",
        "Should I pay down debt aggressively or invest while rates are high?",
        "Should I start a side business this year?",
        "Should I raise my prices for clients?",
        "Should I hire help before I feel fully ready?",
        "Should I put more money into index funds than individual stocks?",
        "Should I keep an emergency fund in cash or short Treasuries?",
        "Should I buy Bitcoin as a long-term hedge?",
        "Should I cut subscriptions hard for 90 days?",
        "Should I lease a car or buy used?",
        "Should I take on a bigger project even if cashflow is lumpy?",
        "Should I reinvest profits or take a larger owner draw?",
        "Should I open a second business entity for risk isolation?",
        "Should I negotiate every recurring bill this month?",
    ],
    "career": [
        "Should I quit my job to go fully independent?",
        "Should I ask for a raise this quarter?",
        "Should I switch careers into AI engineering?",
        "Should I learn Rust seriously this year?",
        "Should I specialize deeper or stay a generalist?",
        "Should I take a lower-paying role with better upside?",
        "Should I say no to meetings that drain focus time?",
        "Should I publish more publicly about my work?",
        "Should I apply to bigger companies even if I like autonomy?",
        "Should I take a sabbatical to rebuild?",
        "Should I mentor juniors even when busy?",
        "Should I build in public daily for 90 days?",
    ],
    "lifestyle": [
        "Should I wake up at 5 AM every day?",
        "Should I quit social media for 30 days?",
        "Should I move cities for opportunity?",
        "Should I buy fewer things and optimize what I own?",
        "Should I keep a strict no-phone morning routine?",
        "Should I travel more even if it costs focus?",
        "Should I get a dog right now?",
        "Should I declutter aggressively this weekend?",
        "Should I cook almost all meals at home for 60 days?",
        "Should I schedule deep-work blocks like meetings?",
        "Should I take Sundays completely offline?",
        "Should I date more intentionally this year?",
    ],
    "health": [
        "Should I hire a personal trainer?",
        "Should I try a stricter diet for 8 weeks?",
        "Should I prioritize sleep over late-night hustle?",
        "Should I buy a standing desk setup?",
        "Should I cut caffeine after noon permanently?",
        "Should I train for a 5K or focus on strength?",
        "Should I get a full blood panel before changing supplements?",
        "Should I walk 10,000 steps daily no matter what?",
        "Should I replace late dinners with earlier meals?",
        "Should I meditate every morning for 10 minutes?",
    ],
    "gaming": [
        "Should I buy the next PlayStation or stick to PC gaming?",
        "Should I pre-order big AAA games anymore?",
        "Should I quit competitive ranked games for a season?",
        "Should I buy a Steam Deck or ROG Ally?",
        "Should I finish my backlog before buying new games?",
        "Should I join a regular gaming group weekly?",
        "Should I stream my gameplay publicly?",
        "Should I spend money on cosmetics in games?",
    ],
    "home": [
        "Should I automate more lights with Home Assistant?",
        "Should I buy a robot vacuum?",
        "Should I upgrade the router / mesh Wi-Fi now?",
        "Should I soundproof the office before buying more gear?",
        "Should I get blackout curtains for better sleep?",
        "Should I replace the desk chair before the desk?",
        "Should I add more cameras for home security?",
        "Should I install a smart lock?",
        "Should I deep-clean and reorganize the apartment this weekend?",
        "Should I put plants all over the workspace?",
    ],
    "philadelphia": [
        "Should I stay in Philadelphia long-term?",
        "Should I buy property in Philly instead of renting?",
        "Should I explore more neighborhoods outside Center City?",
        "Should I get a SEPTA-centric lifestyle and drive less?",
        "Should I plan more weekend trips from Philly this year?",
        "Should I eat out less and cook more in Philly?",
        "Should I go to more live events in the city?",
        "Should I network harder in the local tech scene?",
    ],
    "business": [
        "Should I double down on one product or keep experimenting?",
        "Should I fire an underperforming client?",
        "Should I productize my services into packages?",
        "Should I run paid ads this month?",
        "Should I post daily on LinkedIn for lead gen?",
        "Should I hire a VA before a specialist?",
        "Should I raise prices even if some clients leave?",
        "Should I partner with someone or stay solo?",
        "Should I launch a waitlist before the product is ready?",
        "Should I kill a project that is not growing?",
        "Should I focus on retainers over one-off gigs?",
        "Should I spend a week only on sales?",
    ],
}

# Friendly aliases people say out loud
CATEGORY_ALIASES: dict[str, str] = {
    "tech": "tech",
    "technology": "tech",
    "gadgets": "tech",
    "hardware": "tech",
    "ai": "ai",
    "artificial intelligence": "ai",
    "money": "money",
    "finance": "money",
    "financial": "money",
    "investing": "money",
    "career": "career",
    "job": "career",
    "work": "career",
    "lifestyle": "lifestyle",
    "life": "lifestyle",
    "health": "health",
    "fitness": "health",
    "gaming": "gaming",
    "games": "gaming",
    "home": "home",
    "house": "home",
    "apartment": "home",
    "philadelphia": "philadelphia",
    "philly": "philadelphia",
    "local": "philadelphia",
    "business": "business",
    "startup": "business",
    "clients": "business",
}


def all_categories() -> list[str]:
    return sorted(DEBATE_TOPICS.keys())


def all_topics() -> list[tuple[str, str]]:
    """Flat list of (category, question) in stable order."""
    out: list[tuple[str, str]] = []
    for cat in all_categories():
        for q in DEBATE_TOPICS[cat]:
            out.append((cat, q))
    return out


def topic_count() -> int:
    return sum(len(v) for v in DEBATE_TOPICS.values())


def resolve_category(text: str) -> str | None:
    key = (text or "").strip().lower()
    if key in DEBATE_TOPICS:
        return key
    return CATEGORY_ALIASES.get(key)


def pick_random(*, category: str | None = None) -> tuple[str, str]:
    if category:
        cat = resolve_category(category) or category
        pool = DEBATE_TOPICS.get(cat) or []
        if not pool:
            cat, q = random.choice(all_topics())
            return cat, q
        return cat, random.choice(pool)
    return random.choice(all_topics())


def pick_by_index(n: int) -> tuple[str, str] | None:
    topics = all_topics()
    if n < 1 or n > len(topics):
        return None
    return topics[n - 1]


def list_summary(*, limit_per_cat: int = 3) -> str:
    lines = [f"Debate chamber — {topic_count()} topics across {len(DEBATE_TOPICS)} categories."]
    for cat in all_categories():
        sample = DEBATE_TOPICS[cat][:limit_per_cat]
        lines.append(f"\n{cat.upper()} ({len(DEBATE_TOPICS[cat])}):")
        for q in sample:
            lines.append(f"  • {q}")
        if len(DEBATE_TOPICS[cat]) > limit_per_cat:
            lines.append(f"  … +{len(DEBATE_TOPICS[cat]) - limit_per_cat} more")
    lines.append(
        "\nSay: crew debate random · crew debate tech · crew debate 7 · "
        "or crew debate <your question>"
    )
    return "\n".join(lines)


def spoken_menu() -> str:
    cats = ", ".join(all_categories())
    return (
        f"I have {topic_count()} debates ready across {cats}. "
        "Say crew debate random, or name a category like tech, money, career, "
        "AI, Philly, or business."
    )


def iter_category_labels() -> Iterable[str]:
    return all_categories()
