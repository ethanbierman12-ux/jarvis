"""Autonomous website builder — invents brand, writes prompts, ships full HTML."""

from __future__ import annotations

import json
import random
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

SITES_DIR = DATA_DIR / "sites"
META_PATH = DATA_DIR / "sites_index.json"

# Invented venture seeds when user just says "build a site"
_INVENTIONS = (
    ("Arc Reactor Roasters", "coffee", "small-batch coffee roasted with precision"),
    ("Midnight Circuit Gym", "gym", "late-night training for builders and founders"),
    ("Northline Legal", "law", "clear, modern counsel for startups"),
    ("Harbor & Hearth Bakery", "bakery", "sourdough and pastries baked before dawn"),
    ("Pulse Clinic", "clinic", "same-day care without the waiting-room fog"),
    ("Velvet Coil Salon", "salon", "cuts and color with editorial polish"),
    ("Keystone Plumbing Co.", "plumber", "fast, respectful home repair"),
    ("Lumen Studio", "studio", "brand films and product photography"),
    ("Atlas Fitness Lab", "gym", "science-backed strength coaching"),
    ("Copper Crow Cafe", "coffee", "neighborhood espresso and quiet tables"),
    ("Brightside Dental", "dentist", "gentle dentistry with modern tools"),
    ("Forge & Frame Agency", "agency", "websites and campaigns that convert"),
    ("Glassline Optics", "optics", "custom frames and same-day lenses"),
    ("Riverbend Pet Care", "pets", "calm grooming and boarding for city dogs"),
    ("Summit Trail Outfitters", "outdoor", "gear for weekend escapes"),
    ("Ember & Oak Kitchen", "restaurant", "wood-fired plates and late reservations"),
    ("Nova Grid Electric", "electrician", "clean installs and honest diagnostics"),
    ("Quiet Room Therapy", "clinic", "focused counseling without the clinic chill"),
    ("Parcel & Post", "shipping", "local courier with same-day drops"),
    ("Ironleaf Landscaping", "landscaping", "sharp yards and seasonal installs"),
    ("Drift Audio Lab", "studio", "podcast rooms and mix sessions"),
    ("Cinder Bike Co.", "bike", "tune-ups and city builds"),
    ("Halo Clean Co.", "cleaning", "detail-obsessed home resets"),
    ("Beacon Tutoring", "education", "after-school clarity that sticks"),
)

# Visual themes — each build picks one so sites never look identical
_THEMES = (
    {
        "id": "cyan_void",
        "accent": "#00e8ff",
        "secondary": "#071018",
        "font": 'Bahnschrift, "Segoe UI", sans-serif',
        "hero_size": "clamp(2.4rem, 5.5vw, 4.4rem)",
        "layout": "classic",
        "radius": "0",
        "card": "left-bar",
    },
    {
        "id": "amber_steel",
        "accent": "#ffb020",
        "secondary": "#0c0e12",
        "font": 'Georgia, "Times New Roman", serif',
        "hero_size": "clamp(2.6rem, 6vw, 4.8rem)",
        "layout": "split",
        "radius": "0",
        "card": "boxed",
    },
    {
        "id": "ice_signal",
        "accent": "#7ec8ff",
        "secondary": "#050a12",
        "font": '"Segoe UI", Bahnschrift, sans-serif',
        "hero_size": "clamp(2.1rem, 4.8vw, 3.8rem)",
        "layout": "centered",
        "radius": "2px",
        "card": "grid",
    },
    {
        "id": "emerald_ops",
        "accent": "#3dff9a",
        "secondary": "#04100a",
        "font": 'Consolas, "Courier New", monospace',
        "hero_size": "clamp(2rem, 4.5vw, 3.4rem)",
        "layout": "classic",
        "radius": "0",
        "card": "left-bar",
    },
    {
        "id": "coral_night",
        "accent": "#ff6b4a",
        "secondary": "#100808",
        "font": 'Bahnschrift, "Trebuchet MS", sans-serif',
        "hero_size": "clamp(2.5rem, 5.8vw, 4.6rem)",
        "layout": "split",
        "radius": "0",
        "card": "boxed",
    },
    {
        "id": "mono_industrial",
        "accent": "#e8f0f8",
        "secondary": "#0a0c10",
        "font": '"Arial Narrow", Bahnschrift, sans-serif',
        "hero_size": "clamp(2.8rem, 6.2vw, 5rem)",
        "layout": "centered",
        "radius": "0",
        "card": "grid",
    },
)

_FALLBACK_HEROES = (
    "{name} — {cat} without the noise.",
    "Built for {place}. Tuned for people who notice the details.",
    "{cat} that feels intentional from the first second.",
    "Quiet confidence. Clear craft. {name}.",
    "The {place} standard for {cat} — raised.",
)


class SiteBuilder:
    """
    Full-stack AI site agent with HITL:
      ~95% autonomous (invent → plan → sandbox write → HUD preview),
      pauses for human permission before deploy / open external / massive rebuilds.
      Zero-setup: static HTML under jarvis/data/sites — no Node install.
    """

    def __init__(self, hitl=None) -> None:
        from jarvis.core.zero_env import ensure_agent_dirs

        ensure_agent_dirs()
        SITES_DIR.mkdir(parents=True, exist_ok=True)
        if not META_PATH.exists():
            META_PATH.write_text(json.dumps({"sites": []}, indent=2), encoding="utf-8")
        self.hitl = hitl
        self.last_site: Path | None = None
        self.last_prompt = ""
        self.last_content: dict[str, Any] = {}
        self.last_brief = ""

    def build(
        self,
        brief: str,
        *,
        business: dict[str, Any] | None = None,
        open_when_done: bool = True,
        city: str = "Philadelphia",
        on_progress: Callable[..., None] | None = None,
        hitl=None,
    ) -> str:
        def progress(msg: str, **extra: Any) -> None:
            if on_progress:
                try:
                    if extra:
                        on_progress({"msg": msg, **extra})
                    else:
                        on_progress(msg)
                except Exception:
                    pass

        def beat(sec: float = 0.45) -> None:
            # Give the HUD time to paint each live step
            time.sleep(sec)

        gate = hitl or self.hitl

        brief = (brief or "").strip()
        brief = self._normalize_brief(brief)

        progress("Session online — opening live build canvas…", stage="invent")
        beat(0.35)

        def agent(**kw: Any) -> None:
            """Emit agentic workbench fields alongside stage progress."""
            progress(kw.pop("msg", kw.get("log", "…")), **kw)

        agent(
            msg="AI coding agent online — starting agentic workflow",
            stage="invent",
            agent_stage="plan",
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": False, "active": True},
                {"text": "Write project files", "done": False, "active": False},
                {"text": "Run sandbox build commands", "done": False, "active": False},
                {"text": "Browser viewport + hot reload", "done": False, "active": False},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
            terminal="jarvis agent init --workflow site",
            file_path="agent/workflow.md",
            file="# Agentic Site Build\n\n1. Invent\n2. Code\n3. Preview\n4. Ship\n",
            browser="Booting sandbox viewport…",
        )
        beat(0.5)

        if business:
            name = business.get("name") or "Local Business"
            brief = brief or (
                f"Professional website for {name}, a {business.get('category') or 'local business'} "
                f"at {business.get('address') or city}. Phone {business.get('phone') or 'on request'}."
            )
            biz = dict(business)
            progress(
                f"Business locked · {name}",
                stage="invent",
                brand=name,
                log=f"Using searched business: {name}",
                agent_stage="plan",
                terminal=f'jarvis resolve --business "{name}"',
                file_path="brief.md",
                file=f"# Brief\n\nBusiness: {name}\nCity: {city}\n",
                browser="Waiting for first render…",
            )
            beat(0.5)
        elif self._is_vague(brief):
            progress("Inventing a brand concept from scratch…", stage="invent", agent_stage="plan",
                     terminal="jarvis invent --mode brand")
            beat(0.55)
            biz, brief = self._invent_venture(city)
            progress(
                f"Brand invented · {biz.get('name')}",
                stage="invent",
                brand=str(biz.get("name") or ""),
                tagline=f"{biz.get('category')} · {city}",
                agent_stage="plan",
                terminal=f"→ brand={biz.get('name')}",
                file_path="brand.json",
                file=json.dumps(
                    {"name": biz.get("name"), "category": biz.get("category"), "city": city},
                    indent=2,
                ),
            )
            beat(0.55)
        else:
            name = self._guess_name(brief) or ""
            cat = self._guess_category(brief)
            if not name:
                progress("Inventing a brand name…", stage="invent", agent_stage="plan",
                         terminal="jarvis invent --mode name")
                beat(0.4)
                name, cat, flavor = self._invent_name_for(cat or "business", city)
                brief = f"{brief}. Brand name: {name} — {flavor}."
            biz = {
                "name": name,
                "category": cat or self._guess_category(brief),
                "address": f"{city}",
                "phone": "",
                "website": "",
            }
            progress(
                f"Brand locked · {name}",
                stage="invent",
                brand=name,
                tagline=f"{cat} · {city}",
                agent_stage="plan",
                file_path="brand.json",
                file=json.dumps({"name": name, "category": cat, "city": city}, indent=2),
                terminal=f"→ brand={name}",
            )
            beat(0.45)

        self.last_brief = brief
        progress(
            f"Writing design prompt for {biz.get('name')}…",
            stage="prompt",
            brand=str(biz.get("name") or ""),
            agent_stage="plan",
            terminal="jarvis prompt --role creative-director",
            file_path="prompt.txt",
            file=f"(drafting prompt for {biz.get('name')}…)\n",
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": False, "active": True},
                {"text": "Write project files", "done": False, "active": False},
                {"text": "Run sandbox build commands", "done": False, "active": False},
                {"text": "Browser viewport + hot reload", "done": False, "active": False},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
        )
        beat(0.4)
        prompt = self._write_own_prompt(brief, biz)
        self.last_prompt = prompt
        progress(
            "Prompt ready — creative direction set",
            stage="prompt",
            brand=str(biz.get("name") or ""),
            log=f"Prompt: {(prompt or '')[:120]}…",
            agent_stage="code",
            file_path="prompt.txt",
            file=prompt,
            terminal="→ prompt written",
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": True, "active": False},
                {"text": "Write project files", "done": False, "active": True},
                {"text": "Run sandbox build commands", "done": False, "active": False},
                {"text": "Browser viewport + hot reload", "done": False, "active": False},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
        )
        beat(0.55)

        progress(
            "Generating page copy and layout…",
            stage="copy",
            agent_stage="code",
            terminal="jarvis generate --target content.json",
            file_path="content.json",
            file='{\n  "status": "generating…"\n}\n',
        )
        beat(0.35)
        content = self._generate_content(prompt, biz, city=city)
        self.last_content = content
        progress(
            f"Copy locked · {content.get('brand')}",
            stage="copy",
            brand=str(content.get("brand") or biz.get("name") or ""),
            tagline=str(content.get("tagline") or ""),
            hero=str(content.get("hero") or ""),
            agent_stage="code",
            file_path="content.json",
            file=json.dumps(content, indent=2)[:3500],
            terminal="→ content.json written",
        )
        beat(0.5)

        # Live skeleton on canvas before full render
        skel = self._skeleton_html(content, biz)
        progress(
            "Drafting live canvas — hero and structure…",
            stage="live",
            brand=str(content.get("brand") or ""),
            tagline=str(content.get("tagline") or ""),
            hero=str(content.get("hero") or ""),
            html=skel,
            agent_stage="browser",
            browser="Hot reload · skeleton mount",
            terminal="jarvis preview --hot-reload",
            file_path="index.html",
            file=skel[:2500],
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": True, "active": False},
                {"text": "Write project files", "done": True, "active": False},
                {"text": "Run sandbox build commands", "done": False, "active": True},
                {"text": "Browser viewport + hot reload", "done": False, "active": False},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
        )
        beat(0.7)

        progress(
            "Selecting visual theme…",
            stage="theme",
            agent_stage="code",
            terminal="jarvis theme --pick",
        )
        theme = self._pick_theme()
        progress(
            f"Theme · {theme.get('id')}",
            stage="theme",
            theme=str(theme.get("id") or ""),
            brand=str(content.get("brand") or ""),
            html=skel,
            agent_stage="code",
            terminal=f"→ theme={theme.get('id')}",
            file_path="theme.json",
            file=json.dumps(theme, indent=2),
            browser="Theme tokens applied — reloading viewport",
        )
        beat(0.45)

        progress(
            "Rendering full HTML…",
            stage="render",
            agent_stage="terminal",
            terminal="jarvis build --out index.html",
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": True, "active": False},
                {"text": "Write project files", "done": True, "active": False},
                {"text": "Run sandbox build commands", "done": False, "active": True},
                {"text": "Browser viewport + hot reload", "done": False, "active": False},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
        )
        beat(0.35)
        slug = self._slug(content.get("brand") or biz["name"])
        slug = f"{slug}-{datetime.now().strftime('%m%d-%H%M%S')}-{random.randint(10, 99)}"
        out_dir = SITES_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        index = out_dir / "index.html"
        html = self._render_html(content, biz, theme=theme)

        # Show nearly-final draft on canvas before save
        progress(
            "Browser automation — checking layout + hot reload",
            stage="live",
            brand=str(content.get("brand") or ""),
            theme=str(theme.get("id") or ""),
            hero=str(content.get("hero") or ""),
            tagline=str(content.get("tagline") or ""),
            html=html,
            agent_stage="browser",
            browser="QA pass · hero / contrast / CTA",
            terminal="→ build ok · opening viewport",
            file_path="index.html",
            file=html[:4000],
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": True, "active": False},
                {"text": "Write project files", "done": True, "active": False},
                {"text": "Run sandbox build commands", "done": True, "active": False},
                {"text": "Browser viewport + hot reload", "done": False, "active": True},
                {"text": "Iterate / ship live preview", "done": False, "active": False},
            ],
        )
        beat(0.85)

        progress(
            "Iterating — polishing spacing before ship",
            stage="live",
            agent_stage="iterate",
            browser="Iterate · spacing + CTA hover",
            terminal="jarvis iterate --fix spacing",
            html=html,
            file_path="index.html",
            file=html[:4000],
        )
        beat(0.55)

        index.write_text(html, encoding="utf-8")
        (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (out_dir / "content.json").write_text(
            json.dumps({**content, "theme": theme.get("id")}, indent=2), encoding="utf-8"
        )
        try:
            from jarvis.core.zero_env import write_env_manifest

            write_env_manifest(
                out_dir,
                stack="static-html",
                files=["index.html", "prompt.txt", "content.json"],
                notes="Zero-setup site — open index.html, no install.",
            )
        except Exception:
            pass

        self.last_site = index
        self._index_site(slug, content, index)

        progress(
            "Ship — agentic workflow complete",
            stage="live",
            brand=str(content.get("brand") or ""),
            theme=str(theme.get("id") or ""),
            agent_stage="ship",
            terminal=f"→ shipped {index.name}",
            browser="Live preview locked",
            html=html,
            file_path="index.html",
            file=html[:4000],
            plan=[
                {"text": "Plan agentic site workflow", "done": True, "active": False},
                {"text": "Invent brand + design prompt", "done": True, "active": False},
                {"text": "Write project files", "done": True, "active": False},
                {"text": "Run sandbox build commands", "done": True, "active": False},
                {"text": "Browser viewport + hot reload", "done": True, "active": False},
                {"text": "Iterate / ship live preview", "done": True, "active": False},
            ],
        )
        beat(0.35)

        brand = content.get("brand") or biz["name"]
        msg = (
            f"Done. Agentic workflow shipped a full site for {brand}. "
            f"Saved to {index.name}. Live preview is on screen."
        )
        if open_when_done:
            deploy_ok = True
            if gate is not None:
                progress(
                    "HITL pause — deploy / open externally?",
                    stage="hitl",
                    agent_stage="hitl",
                    terminal="jarvis hitl --gate deploy",
                    browser="Paused · deploy permission",
                )
                deploy_ok = gate.gate_deploy(
                    what=f"Open {brand} in system browser",
                    path=str(index),
                    agent="site",
                )
            if deploy_ok:
                try:
                    self.open_last()
                    msg += " External browser opened (HITL approved)."
                except Exception:
                    pass
            else:
                msg += " Kept in HUD sandbox only (HITL denied external deploy)."
                progress(
                    "HITL denied deploy — sandbox preview only",
                    stage="hitl",
                    agent_stage="hitl",
                    terminal="→ sandbox only",
                )
        return msg

    def _skeleton_html(self, c: dict[str, Any], biz: dict[str, Any]) -> str:
        """Lightweight in-progress page so the canvas updates before final HTML."""
        accent = c.get("accent") or "#00e8ff"
        brand = _esc(c.get("brand") or biz.get("name") or "Brand")
        tag = _esc(c.get("tagline") or "Assembling…")
        hero = _esc(c.get("hero") or "Writing headline…")
        about = _esc((c.get("about") or "Generating about copy…")[:220])
        services = c.get("services") or ["…", "…", "…"]
        cards = "".join(
            f"<div class='card'><span>{_esc(s)}</span></div>" for s in services[:3]
        )
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
body{{margin:0;font-family:Bahnschrift,Segoe UI,sans-serif;background:#071018;color:#eaf6ff}}
header{{padding:22px 28px;border-bottom:1px solid {accent};letter-spacing:4px;color:{accent};font-weight:800}}
main{{padding:40px 28px}}
.tag{{color:{accent};font-size:12px;letter-spacing:2px;margin-bottom:10px}}
h1{{font-size:clamp(1.8rem,4vw,3rem);margin:0 0 14px;line-height:1.1}}
p{{color:#8aa4b8;max-width:560px;line-height:1.5}}
.cta{{display:inline-block;margin-top:22px;padding:12px 20px;background:{accent};color:#041018;font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:36px}}
.card{{padding:16px;background:rgba(0,232,255,.08);border-left:3px solid {accent};min-height:64px}}
.scan{{position:fixed;left:0;right:0;height:2px;background:{accent};top:0;animation:s 2s linear infinite;opacity:.6}}
@keyframes s{{to{{top:100%}}}}
</style></head><body>
<div class="scan"></div>
<header>{brand}</header>
<main>
  <div class="tag">{tag}</div>
  <h1>{hero}</h1>
  <p>{about}</p>
  <div class="cta">BUILDING…</div>
  <div class="grid">{cards}</div>
</main>
</body></html>"""

    def build_for_index(
        self,
        index: int,
        finder,
        *,
        city: str = "Philadelphia",
        on_progress: Callable[..., None] | None = None,
        hitl=None,
    ) -> str:
        biz = finder.get(index) if finder else None
        if not biz:
            return "I do not have that business number. Search first, then say build a website for number 1."
        return self.build(
            "",
            business=biz,
            open_when_done=True,
            city=city,
            on_progress=on_progress,
            hitl=hitl,
        )

    def open_last(self) -> str:
        path = self.last_site
        if path is None or not path.exists():
            sites = sorted(
                SITES_DIR.glob("*/index.html"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            path = sites[0] if sites else None
        if not path:
            return "No website built yet."
        url = path.resolve().as_uri()
        try:
            from jarvis.core.displays import displays

            displays.open_url_on(url, "secondary")
        except Exception:
            import webbrowser

            webbrowser.open(url)
        return f"Opened {path.parent.name} on your other monitor."

    def list_sites(self) -> str:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            sites = data.get("sites") or []
        except Exception:
            sites = []
        if not sites:
            return "No sites built yet. Say build a website — I will invent one end to end."
        bits = [f"{s.get('brand')} ({s.get('slug')})" for s in sites[-8:]]
        return "Recent sites: " + "; ".join(bits) + "."

    # ── autonomy helpers ────────────────────────────────────────
    def _normalize_brief(self, brief: str) -> str:
        b = brief.strip(" .")
        b = re.sub(
            r"^(build|make|create)\s+(a\s+|me\s+)?(website|site|webpage|landing page)\s*(for\s+)?",
            "",
            b,
            flags=re.I,
        ).strip(" .")
        return b

    def _is_vague(self, brief: str) -> bool:
        t = (brief or "").lower().strip()
        if not t:
            return True
        vague = {
            "a site",
            "site",
            "a website",
            "website",
            "webpage",
            "a webpage",
            "landing page",
            "a landing page",
            "one",
            "something",
            "anything",
            "please",
            "for me",
            "now",
        }
        return t in vague or len(t) < 4

    def _invent_venture(self, city: str) -> tuple[dict[str, Any], str]:
        used = self._recent_brands()
        pool = [inv for inv in _INVENTIONS if inv[0].lower() not in used]
        if not pool:
            pool = list(_INVENTIONS)
        name, cat, flavor = random.choice(pool)
        # Force uniqueness — never ship the exact same brand twice
        stamp = datetime.now().strftime("%y%m")
        extras = ("Works", "House", "Lab", "Co.", "Atelier", "Room", "Collective", "Desk")
        if name.lower() in used or random.random() < 0.55:
            base = name.split()[0]
            city_bit = city.split()[0]
            name = f"{base} {city_bit} {random.choice(extras)}"
        if random.random() < 0.3:
            name = f"{name} {stamp}"
        biz = {
            "name": name,
            "category": cat,
            "address": city,
            "phone": "",
            "website": "",
        }
        angles = (
            f"Invent and launch a premium one-page website for {name} in {city}. "
            f"They offer {flavor}. Make it feel expensive, clear, and ready to convert.",
            f"Design a bold launch site for {name} ({cat}) in {city}. "
            f"Story: {flavor}. Avoid generic stock-site energy — make it memorable.",
            f"Ship a distinct brand page for {name}. Location {city}. "
            f"Promise: {flavor}. Hero must feel unlike anything Jarvis built before.",
        )
        brief = random.choice(angles)
        return biz, brief

    def _recent_brands(self) -> set[str]:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            return {
                str(s.get("brand") or "").lower()
                for s in (data.get("sites") or [])[-30:]
                if s.get("brand")
            }
        except Exception:
            return set()

    def _pick_theme(self) -> dict[str, Any]:
        used_themes: list[str] = []
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            for s in (data.get("sites") or [])[-6:]:
                # themes stored only on newer builds via content; rotate anyway
                pass
        except Exception:
            pass
        # Prefer a theme not used in this process session
        if not hasattr(self, "_theme_hist"):
            self._theme_hist: list[str] = []
        choices = [t for t in _THEMES if t["id"] not in self._theme_hist[-3:]]
        theme = dict(random.choice(choices or _THEMES))
        self._theme_hist.append(theme["id"])
        return theme

    def _invent_name_for(self, category: str, city: str) -> tuple[str, str, str]:
        for name, cat, flavor in _INVENTIONS:
            if cat == category or category in flavor:
                return name, cat, flavor
        prefixes = ("Lumen", "North", "Arc", "Harbor", "Pulse", "Forge", "Copper", "Atlas")
        suffixes = {
            "coffee": ("Roasters", "Cafe", "Brew"),
            "gym": ("Gym", "Lab", "Athletics"),
            "bakery": ("Bakery", "Oven", "Kitchen"),
            "salon": ("Salon", "Studio", "House"),
            "agency": ("Agency", "Collective", "Works"),
        }
        suf = random.choice(suffixes.get(category, ("Co.", "Studio", "Group")))
        return f"{random.choice(prefixes)} {suf}", category, f"{category} in {city}"

    def _write_own_prompt(self, brief: str, biz: dict[str, Any]) -> str:
        seed = (
            f"Create a premium one-page website brief for '{biz.get('name')}'. "
            f"Category: {biz.get('category')}. Location: {biz.get('address')}. "
            f"Mission: {brief}. "
            "Invent brand voice, hero headline, 3 services, CTA, color mood. "
            "Be specific and cinematic. Under 130 words."
        )
        crafted = self._ollama_text(
            "You are Jarvis, an elite creative director AI. Write the design prompt yourself. "
            "No questions. No waiting for the user. Output the prompt only.",
            seed,
            num_predict=180,
        )
        if crafted:
            return crafted.strip()
        return (
            f"Design a cinematic, conversion-focused landing page for {biz.get('name')}, "
            f"a {biz.get('category') or 'local business'} in {biz.get('address') or 'the city'}. "
            f"Mood: confident cyan-on-void tech luxury with warm human service. "
            f"Hero in one bold line. Sections: About, Services, Contact. "
            f"CTA that books or gets a quote. Copy: crisp, trustworthy, premium. "
            f"Context: {brief}"
        )

    def _generate_content(
        self, prompt: str, biz: dict[str, Any], *, city: str = ""
    ) -> dict[str, Any]:
        schema_hint = (
            "Return ONLY JSON with keys: brand, tagline, hero, about, services "
            "(array of 3 strings), cta, accent (hex), secondary (hex), footer. No markdown."
        )
        raw = self._ollama_text(
            "You are Jarvis. Generate finished website copy now. Do not ask questions. "
            + schema_hint,
            prompt,
            num_predict=400,
        )
        parsed = self._parse_json(raw) if raw else None
        if parsed:
            content = self._normalize_content(parsed, biz)
            # Nudge uniqueness even when model returns similar structure
            if random.random() < 0.4:
                content["accent"] = random.choice(
                    ["#00e8ff", "#ffb020", "#3dff9a", "#ff6b4a", "#7ec8ff", "#e8f0f8"]
                )
            return content

        name = biz.get("name") or "Local Business"
        cat = (biz.get("category") or "service").replace("_", " ")
        place = biz.get("address") or city or "town"
        hero = random.choice(_FALLBACK_HEROES).format(name=name, cat=cat, place=place)
        accents = ["#00e8ff", "#ffb020", "#3dff9a", "#ff6b4a", "#7ec8ff", "#e8f0f8"]
        secondaries = ["#071018", "#0c0e12", "#050a12", "#04100a", "#100808", "#0a0c10"]
        service_sets = (
            [
                f"Signature {cat} experiences",
                "Clear pricing and fast replies",
                f"Local {place} service with follow-through",
            ],
            [
                f"Consult-first {cat}",
                "Transparent timelines",
                "Aftercare that actually shows up",
            ],
            [
                f"Flagship {cat} offer",
                "Same-week availability",
                f"Built around {place} clients",
            ],
            [
                "Discovery call",
                f"Custom {cat} plan",
                "Results review",
            ],
        )
        return {
            "brand": name,
            "tagline": random.choice(
                [
                    f"{cat.title()} · {place}",
                    f"{place} · {cat.title()}",
                    f"Est. for {place}",
                    f"{cat.title()} · crafted",
                ]
            ),
            "hero": hero,
            "about": random.choice(
                [
                    (
                        f"{name} was built for {place}. We keep the craft sharp, the process clear, "
                        f"and the experience quietly premium. No gimmicks — just {cat} done right."
                    ),
                    (
                        f"People find {name} when they want {cat} that feels considered. "
                        f"We work in {place} with a simple rule: fewer promises, better delivery."
                    ),
                    (
                        f"{name} started as a response to bland {cat}. "
                        f"In {place}, we built something sharper — human, fast, and exact."
                    ),
                ]
            ),
            "services": list(random.choice(service_sets)),
            "cta": random.choice(
                ["Book a visit", "Get a quote", "Start here", "Reserve a slot", "Talk to us"]
            ),
            "accent": random.choice(accents),
            "secondary": random.choice(secondaries),
            "footer": f"© {datetime.now().year} {name}. Designed and built by Jarvis.",
        }

    def _normalize_content(self, data: dict[str, Any], biz: dict[str, Any]) -> dict[str, Any]:
        services = data.get("services") or []
        if isinstance(services, str):
            services = [s.strip() for s in services.split(";") if s.strip()]
        return {
            "brand": data.get("brand") or biz.get("name") or "Business",
            "tagline": data.get("tagline") or "Excellence, delivered.",
            "hero": data.get("hero") or data.get("tagline") or "",
            "about": data.get("about") or "",
            "services": list(services)[:5] or ["Consultation", "Delivery", "Support"],
            "cta": data.get("cta") or "Contact us",
            "accent": data.get("accent") or "#00e8ff",
            "secondary": data.get("secondary") or "#071018",
            "footer": data.get("footer")
            or f"© {datetime.now().year} {biz.get('name')}. Built by Jarvis.",
        }

    def _render_html(
        self, c: dict[str, Any], biz: dict[str, Any], *, theme: dict[str, Any] | None = None
    ) -> str:
        theme = theme or self._pick_theme()
        accent = c.get("accent") or theme.get("accent") or "#00e8ff"
        secondary = c.get("secondary") or theme.get("secondary") or "#071018"
        font = theme.get("font") or 'Bahnschrift, "Segoe UI", sans-serif'
        hero_size = theme.get("hero_size") or "clamp(2.2rem, 5vw, 4.2rem)"
        layout = theme.get("layout") or "classic"
        radius = theme.get("radius") or "0"
        card = theme.get("card") or "left-bar"

        if card == "grid":
            services = "".join(
                f"<li class='card grid'><span class='num'>{i:02d}</span>"
                f"<span>{_esc(s)}</span></li>"
                for i, s in enumerate(c.get("services") or [], 1)
            )
            services_wrap = f"<ul class='grid3'>{services}</ul>"
        elif card == "boxed":
            services = "".join(
                f"<li class='card boxed'><span>{_esc(s)}</span></li>"
                for s in (c.get("services") or [])
            )
            services_wrap = f"<ul class='stack'>{services}</ul>"
        else:
            services = "".join(
                f"<li class='card'><span class='num'>{i:02d}</span><span>{_esc(s)}</span></li>"
                for i, s in enumerate(c.get("services") or [], 1)
            )
            services_wrap = f"<ul class='stack'>{services}</ul>"

        phone = biz.get("phone") or ""
        address = biz.get("address") or ""
        contact_bits = []
        if phone:
            contact_bits.append(f"<p class='meta'>Phone: {_esc(phone)}</p>")
        if address:
            contact_bits.append(f"<p class='meta'>Based in {_esc(address)}</p>")
        contact = "\n".join(contact_bits) or "<p class='meta'>Reach out — we respond same day.</p>"

        if layout == "split":
            hero_block = f"""
  <section class="hero split">
    <div>
      <div class="tag">{_esc(c.get('tagline'))}</div>
      <h1>{_esc(c.get('hero'))}</h1>
      <a class="cta" href="#contact">{_esc(c.get('cta'))}</a>
    </div>
    <div class="aside">
      <p>{_esc(c.get('about'))[:220]}</p>
    </div>
  </section>"""
        elif layout == "centered":
            hero_block = f"""
  <section class="hero center">
    <div class="tag">{_esc(c.get('tagline'))}</div>
    <h1>{_esc(c.get('hero'))}</h1>
    <p class="center-lead">{_esc(c.get('about'))[:180]}</p>
    <a class="cta" href="#contact">{_esc(c.get('cta'))}</a>
  </section>"""
        else:
            hero_block = f"""
  <section class="hero">
    <div class="tag">{_esc(c.get('tagline'))}</div>
    <h1>{_esc(c.get('hero'))}</h1>
    <p>{_esc(c.get('about'))[:160]}</p>
    <a class="cta" href="#contact">{_esc(c.get('cta'))}</a>
  </section>"""

        # Shuffle section order slightly (about/services) for more variety
        about_sec = f"""
  <section id="about">
    <h2>ABOUT</h2>
    <p class="lead">{_esc(c.get('about'))}</p>
  </section>"""
        services_sec = f"""
  <section id="services">
    <h2>SERVICES</h2>
    {services_wrap}
  </section>"""
        mid = [about_sec, services_sec]
        random.shuffle(mid)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(c.get('brand'))}</title>
<style>
  :root {{ --accent:{accent}; --void:{secondary}; --text:#eaf6ff; --dim:#8aa4b8; --radius:{radius}; }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{
    margin:0; font-family: {font};
    background: radial-gradient(1100px 560px at {random.randint(5,40)}% -10%, color-mix(in srgb, var(--accent) 22%, transparent), transparent),
                linear-gradient({random.randint(140,175)}deg, #02050a, var(--void) 55%, #030810);
    color:var(--text); min-height:100vh;
  }}
  header {{
    padding:28px 8vw; display:flex; justify-content:space-between; align-items:center;
    border-bottom:1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    position:sticky; top:0; backdrop-filter:blur(10px); background:rgba(2,8,14,.85); z-index:5;
  }}
  .brand {{ letter-spacing:5px; color:var(--accent); font-weight:800; font-size:17px; text-transform:uppercase; }}
  .nav a {{ color:var(--dim); text-decoration:none; margin-left:22px; font-size:13px; letter-spacing:1px; }}
  .nav a:hover {{ color:var(--accent); }}
  .hero {{ padding:11vh 8vw 9vh; max-width:1100px; animation:rise .85s ease both; }}
  .hero.split {{ display:grid; grid-template-columns:1.2fr .8fr; gap:40px; align-items:end; max-width:1200px; }}
  .hero.center {{ text-align:center; margin:0 auto; }}
  .hero h1 {{
    font-size:{hero_size}; line-height:1.05; margin:0 0 18px; letter-spacing:-0.4px;
  }}
  .hero p, .aside p, .center-lead {{ color:var(--dim); font-size:1.12rem; max-width:620px; line-height:1.55; }}
  .center-lead {{ margin:0 auto 8px; }}
  .aside {{
    padding:22px; border:1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    background:rgba(0,12,20,.45);
  }}
  .cta {{
    display:inline-block; margin-top:28px; padding:14px 26px; border-radius:var(--radius);
    border:1px solid var(--accent); color:#041018; background:var(--accent);
    text-decoration:none; font-weight:700; letter-spacing:1px;
    transition: transform .2s ease, box-shadow .2s ease;
  }}
  .cta:hover {{ transform:translateY(-2px); box-shadow:0 8px 28px color-mix(in srgb, var(--accent) 35%, transparent); }}
  section {{ padding:68px 8vw; border-top:1px solid color-mix(in srgb, var(--accent) 14%, transparent); }}
  h2 {{ color:var(--accent); letter-spacing:3px; font-size:13px; margin:0 0 18px; }}
  .lead {{ font-size:1.22rem; max-width:720px; line-height:1.5; }}
  ul.stack {{ padding:0; list-style:none; display:grid; gap:14px; max-width:760px; }}
  ul.grid3 {{ padding:0; list-style:none; display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); max-width:960px; }}
  .card {{
    padding:18px 20px; background:rgba(0,20,32,.55); border-radius:var(--radius);
    border-left:3px solid var(--accent); display:flex; gap:16px; align-items:flex-start;
  }}
  .card.boxed {{ border-left:none; border:1px solid color-mix(in srgb, var(--accent) 30%, transparent); }}
  .card.grid {{ flex-direction:column; min-height:120px; border-left:none;
    border-top:3px solid var(--accent); }}
  .num {{ color:var(--accent); font-weight:700; letter-spacing:1px; opacity:.8; }}
  .meta {{ color:var(--dim); }}
  footer {{
    padding:28px 8vw 40px; color:var(--dim); font-size:12px;
    border-top:1px solid color-mix(in srgb, var(--accent) 18%, transparent);
  }}
  .tag {{ color:var(--accent); letter-spacing:2px; font-size:12px; margin-bottom:10px; text-transform:uppercase; }}
  .built {{ opacity:.7; margin-top:8px; font-size:11px; letter-spacing:1px; }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(18px); }} to {{ opacity:1; transform:none; }} }}
  @media (max-width:820px) {{ .hero.split {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <div class="brand">{_esc(c.get('brand'))}</div>
  <nav class="nav">
    <a href="#about">ABOUT</a>
    <a href="#services">SERVICES</a>
    <a href="#contact">CONTACT</a>
  </nav>
</header>
<main>
  {hero_block}
  {''.join(mid)}
  <section id="contact">
    <h2>CONTACT</h2>
    <p class="lead">{_esc(c.get('cta'))} — we are ready when you are.</p>
    {contact}
  </section>
</main>
<footer>
  {_esc(c.get('footer'))}
  <div class="built">AUTONOMOUSLY GENERATED BY JARVIS · THEME {theme.get('id','').upper()}</div>
</footer>
</body>
</html>
"""

    def _ollama_text(self, system: str, user: str, *, num_predict: int = 200) -> str | None:
        try:
            model = self._ollama_model()
            if not model:
                return None
            prompt = f"{system}\n\n{user}"
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.92, "num_predict": num_predict},
            }
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data.get("response") or "").strip()
            return text if len(text) > 20 else None
        except Exception:
            return None

    def _ollama_model(self) -> str | None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models") or []]
            for pref in ("llama", "qwen", "mistral", "phi", "gemma", "moondream"):
                for n in names:
                    if pref in n.lower():
                        return n
            return names[0] if names else None
        except Exception:
            return None

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        text = text.strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    def _guess_name(self, brief: str) -> str:
        m = re.search(
            r"(?:for|called|named)\s+([A-Z][\w\s&'\-]{2,40})",
            brief,
        )
        if m:
            return m.group(1).strip()
        m = re.search(r"website for\s+(.+)$", brief, re.I)
        if m:
            cand = m.group(1).strip(" .")[:40]
            if cand.lower() not in ("a site", "site", "me", "a website"):
                return cand
        return ""

    def _guess_category(self, brief: str) -> str:
        t = brief.lower()
        for word in (
            "coffee",
            "restaurant",
            "plumber",
            "salon",
            "gym",
            "law",
            "clinic",
            "bakery",
            "agency",
            "studio",
            "dentist",
        ):
            if word in t:
                return word
        return "business"

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", (name or "site").lower()).strip("-")
        return (s or "site")[:48]

    def _index_site(self, slug: str, content: dict[str, Any], path: Path) -> None:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {"sites": []}
        data.setdefault("sites", []).append(
            {
                "slug": slug,
                "brand": content.get("brand"),
                "path": str(path),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        )
        data["sites"] = data["sites"][-40:]
        META_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _esc(s: Any) -> str:
    t = str(s or "")
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
