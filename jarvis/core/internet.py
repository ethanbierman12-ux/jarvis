"""Internet control — web search, fetch, summarize (Jarvis browses for you)."""

from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

RESULTS_PATH = DATA_DIR / "web_search.json"
RESULTS_HTML = DATA_DIR / "last_search.html"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisNet/1.0"


class InternetAgent:
    """
    Search the public internet, summarize answers, open results.
    Sources: DuckDuckGo Instant + HTML results, Wikipedia, page fetch.
    """

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.last_query = ""
        self.last_results: list[dict[str, Any]] = []
        self.last_answer = ""

    def search(
        self,
        query: str,
        *,
        open_page: bool = True,
        speak_limit: int = 5,
    ) -> str:
        q = " ".join((query or "").split())
        if not q:
            return "What should I search for on the internet?"

        self.last_query = q
        hits: list[dict[str, Any]] = []
        answer = ""

        # 1) Instant answer / abstract
        ddg = self._duckduckgo_instant(q)
        if ddg.get("abstract"):
            answer = ddg["abstract"]
        for r in ddg.get("results") or []:
            hits.append(r)

        # 2) Organic HTML results
        organic = self._duckduckgo_html(q, limit=8)
        for r in organic:
            if not any(self._same_url(r.get("url"), h.get("url")) for h in hits):
                hits.append(r)

        # 3) Wikipedia if it looks like a what/who question
        if self._looks_encyclopedic(q) or not answer:
            wiki = self._wikipedia(q)
            if wiki:
                if wiki.get("extract") and not answer:
                    answer = wiki["extract"]
                if wiki.get("url"):
                    hits.insert(
                        0,
                        {
                            "title": wiki.get("title") or "Wikipedia",
                            "url": wiki["url"],
                            "snippet": (wiki.get("extract") or "")[:180],
                            "source": "wikipedia",
                        },
                    )

        # 3b) Hacker News + Google News RSS for fresh angles
        for extra in self._hackernews_hits(q) + self._news_rss_hits(q):
            if not any(self._same_url(extra.get("url"), h.get("url")) for h in hits):
                hits.append(extra)

        # 4) Fetch top page snippet to enrich answer
        if hits and (not answer or len(answer) < 80):
            fetched = self._fetch_snippet(hits[0].get("url") or "")
            if fetched:
                if not answer:
                    answer = fetched
                else:
                    answer = answer + " " + fetched[:200]

        # 5) Optional Ollama synthesis
        if hits:
            synthesized = self._synthesize(q, answer, hits[:5])
            if synthesized:
                answer = synthesized

        if not hits and not answer:
            return (
                f"I could not reach useful results for '{q}'. "
                f"Check the network, or try a simpler query."
            )

        self.last_results = hits[:12]
        self.last_answer = answer or ""
        self._save()
        self._write_html()

        if open_page:
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(RESULTS_HTML.resolve().as_uri(), "secondary")
            except Exception:
                pass

        parts = [f"Internet search for {q}."]
        if answer:
            spoken = answer.strip()
            if len(spoken) > 380:
                cut = spoken[:380]
                spoken = cut.rsplit(".", 1)[0] + "." if "." in cut else cut + "…"
            parts.append(spoken)
        if hits:
            parts.append("Top links:")
            for i, h in enumerate(hits[:speak_limit], 1):
                parts.append(f"{i}. {h.get('title') or 'Result'}.")
            parts.append("Say open result 1, or search deeper on …")
        return " ".join(parts)

    def open_result(self, index: int = 1) -> str:
        if not self.last_results:
            self._load()
        if not self.last_results:
            return "No search results yet. Ask me to search the web first."
        if index < 1 or index > len(self.last_results):
            return f"Pick a result between 1 and {len(self.last_results)}."
        url = self.last_results[index - 1].get("url") or ""
        if not url:
            return "That result has no link."
        try:
            from jarvis.core.displays import displays

            displays.open_url_on(url, "secondary")
        except Exception:
            import webbrowser

            webbrowser.open(url)
        title = self.last_results[index - 1].get("title") or url
        return f"Opening result {index} on your other monitor: {title}."

    def open_results_page(self) -> str:
        if not RESULTS_HTML.exists():
            return "No search page yet."
        try:
            from jarvis.core.displays import displays

            displays.open_url_on(RESULTS_HTML.resolve().as_uri(), "secondary")
        except Exception:
            import webbrowser

            webbrowser.open(RESULTS_HTML.resolve().as_uri())
        return "Opening the search brief on your other monitor."

    # ── providers ───────────────────────────────────────────────
    def _duckduckgo_instant(self, q: str) -> dict[str, Any]:
        out: dict[str, Any] = {"abstract": "", "results": []}
        try:
            url = (
                "https://api.duckduckgo.com/?"
                + urllib.parse.urlencode(
                    {
                        "q": q,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    }
                )
            )
            data = self._get_json(url, timeout=8)
            abstract = (data.get("AbstractText") or "").strip()
            heading = (data.get("Heading") or "").strip()
            if abstract:
                out["abstract"] = (
                    f"{heading}: {abstract}" if heading and heading.lower() not in abstract.lower() else abstract
                )
            if data.get("AbstractURL"):
                out["results"].append(
                    {
                        "title": heading or "DuckDuckGo",
                        "url": data["AbstractURL"],
                        "snippet": abstract[:180],
                        "source": "ddg",
                    }
                )
            for rel in (data.get("RelatedTopics") or [])[:6]:
                if not isinstance(rel, dict):
                    continue
                if rel.get("Topics"):
                    continue
                text = (rel.get("Text") or "").strip()
                link = (rel.get("FirstURL") or "").strip()
                if text and link:
                    out["results"].append(
                        {
                            "title": text.split(" - ")[0][:80],
                            "url": link,
                            "snippet": text[:180],
                            "source": "ddg",
                        }
                    )
        except Exception as e:
            print(f"[net] ddg instant failed: {e}")
        return out

    def _duckduckgo_html(self, q: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
            raw = self._get_text(url, timeout=12)
            # Result blocks: <a class="result__a" href="...">title</a>
            # and snippet in result__snippet
            results: list[dict[str, Any]] = []
            # DDG often wraps redirects — unwrap uddg=
            for m in re.finditer(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                raw,
                re.I | re.S,
            ):
                href = html_lib.unescape(m.group(1))
                title = re.sub(r"<[^>]+>", "", html_lib.unescape(m.group(2))).strip()
                real = self._unwrap_ddg(href)
                if not real or not title:
                    continue
                results.append(
                    {
                        "title": title[:120],
                        "url": real,
                        "snippet": "",
                        "source": "web",
                    }
                )
                if len(results) >= limit:
                    break
            # Snippets
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
                raw,
                re.I | re.S,
            )
            for i, sn in enumerate(snippets[: len(results)]):
                text = re.sub(r"<[^>]+>", "", html_lib.unescape(sn)).strip()
                if text:
                    results[i]["snippet"] = text[:220]
            return results
        except Exception as e:
            print(f"[net] ddg html failed: {e}")
            return []

    def _hackernews_hits(self, q: str) -> list[dict[str, Any]]:
        try:
            url = (
                "https://hn.algolia.com/api/v1/search?"
                + urllib.parse.urlencode({"query": q, "hitsPerPage": 4, "tags": "story"})
            )
            data = self._get_json(url, timeout=8)
            out: list[dict[str, Any]] = []
            for h in (data.get("hits") or [])[:4]:
                title = (h.get("title") or "").strip()
                if not title:
                    continue
                link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                out.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": f"HN · {h.get('points') or 0} pts",
                        "source": "hackernews",
                    }
                )
            return out
        except Exception as e:
            print(f"[net] hn: {e}")
            return []

    def _news_rss_hits(self, q: str) -> list[dict[str, Any]]:
        try:
            import xml.etree.ElementTree as ET

            feed = (
                "https://news.google.com/rss/search?"
                + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
            )
            req = urllib.request.Request(feed, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read()
            root = ET.fromstring(raw)
            out: list[dict[str, Any]] = []
            for it in root.findall(".//item")[:4]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                if title:
                    out.append(
                        {
                            "title": title,
                            "url": link,
                            "snippet": "Google News",
                            "source": "rss",
                        }
                    )
            return out
        except Exception as e:
            print(f"[net] rss: {e}")
            return []

    def _wikipedia(self, q: str) -> dict[str, Any] | None:
        try:
            topic = re.sub(
                r"^(what(?:'s| is)|who(?:'s| is)|tell me about|define|explain)\s+",
                "",
                q,
                flags=re.I,
            ).strip(" ?.")
            if not topic:
                topic = q
            # Resolve a real article title first (avoids REST 404 spam)
            title = None
            opensearch = (
                "https://en.wikipedia.org/w/api.php?"
                + urllib.parse.urlencode(
                    {
                        "action": "opensearch",
                        "search": topic,
                        "limit": 1,
                        "namespace": 0,
                        "format": "json",
                    }
                )
            )
            titles = self._get_json(opensearch, timeout=8)
            if isinstance(titles, list) and len(titles) > 1 and titles[1]:
                title = titles[1][0]
            if not title:
                search = (
                    "https://en.wikipedia.org/w/api.php?"
                    + urllib.parse.urlencode(
                        {
                            "action": "query",
                            "list": "search",
                            "srsearch": topic,
                            "srlimit": 1,
                            "format": "json",
                        }
                    )
                )
                data_s = self._get_json(search, timeout=8)
                hits = (
                    ((data_s or {}).get("query") or {}).get("search") or []
                )
                if hits:
                    title = hits[0].get("title")
            if not title:
                return None
            api = (
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + urllib.parse.quote(str(title).replace(" ", "_"))
            )
            try:
                data = self._get_json(api, timeout=8)
            except Exception as e:
                # Missing articles are normal — stay quiet on 404
                if "404" in str(e):
                    return None
                raise
            if data.get("type") == "disambiguation":
                return None
            extract = (data.get("extract") or "").strip()
            if not extract:
                return None
            return {
                "title": data.get("title") or title,
                "extract": extract[:500],
                "url": (data.get("content_urls") or {}).get("desktop", {}).get("page")
                or data.get("url")
                or "",
            }
        except Exception as e:
            if "404" not in str(e):
                print(f"[net] wiki failed: {e}")
            return None

    def _fetch_snippet(self, url: str) -> str:
        if not url or not url.startswith("http"):
            return ""
        try:
            raw = self._get_text(url, timeout=8)
            # Strip scripts/styles
            raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
            text = re.sub(r"(?is)<[^>]+>", " ", raw)
            text = html_lib.unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            # Skip nav junk — take a mid chunk with letters
            if len(text) < 80:
                return ""
            # Prefer sentence-looking segment
            for part in re.split(r"(?<=[.!?])\s+", text[200:2000] if len(text) > 400 else text):
                if len(part) > 60 and sum(c.isalpha() for c in part) > 40:
                    return part[:280]
            return text[200:480] if len(text) > 400 else text[:280]
        except Exception:
            return ""

    def _synthesize(self, q: str, answer: str, hits: list[dict[str, Any]]) -> str | None:
        try:
            bullets = []
            for h in hits:
                bullets.append(f"- {h.get('title')}: {h.get('snippet') or h.get('url')}")
            prompt = (
                f"Question: {q}\n"
                f"Known answer: {answer or 'none'}\n"
                f"Sources:\n" + "\n".join(bullets) + "\n\n"
                "In 2-3 short sentences, give a clear spoken answer for Jarvis. "
                "Be factual. No markdown."
            )
            model = self._ollama_model()
            if not model:
                return None
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 120},
            }
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data.get("response") or "").strip()
            return text if len(text) > 30 else None
        except Exception:
            return None

    def _ollama_model(self) -> str | None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models") or []]
            for pref in ("llama", "qwen", "mistral", "phi", "gemma"):
                for n in names:
                    if pref in n.lower():
                        return n
            return names[0] if names else None
        except Exception:
            return None

    # ── helpers ─────────────────────────────────────────────────
    def _looks_encyclopedic(self, q: str) -> bool:
        return bool(
            re.search(
                r"\b(what(?:'s| is)|who(?:'s| is)|define|explain|tell me about|when (?:was|did)|where is)\b",
                q,
                re.I,
            )
        )

    def _unwrap_ddg(self, href: str) -> str:
        if "uddg=" in href:
            try:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real = parsed.get("uddg", [""])[0]
                return urllib.parse.unquote(real) if real else href
            except Exception:
                return href
        if href.startswith("//"):
            return "https:" + href
        return href

    def _same_url(self, a: Any, b: Any) -> bool:
        if not a or not b:
            return False
        return str(a).rstrip("/") == str(b).rstrip("/")

    def _get_json(self, url: str, timeout: float = 10) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))

    def _get_text(self, url: str, timeout: float = 10) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def _save(self) -> None:
        RESULTS_PATH.write_text(
            json.dumps(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "query": self.last_query,
                    "answer": self.last_answer,
                    "results": self.last_results,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load(self) -> None:
        try:
            raw = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            self.last_query = raw.get("query") or ""
            self.last_answer = raw.get("answer") or ""
            self.last_results = list(raw.get("results") or [])
        except Exception:
            pass

    def _write_html(self) -> None:
        rows = []
        for i, r in enumerate(self.last_results, 1):
            rows.append(
                f"<tr><td>{i}</td><td><a href='{_esc(r.get('url'))}' target='_blank'>"
                f"{_esc(r.get('title'))}</a><div class='sn'>{_esc(r.get('snippet'))}</div>"
                f"</td><td>{_esc(r.get('source'))}</td></tr>"
            )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Jarvis · Internet</title>
<style>
body{{margin:0;background:#02050a;color:#eaf6ff;font-family:Bahnschrift,Segoe UI,sans-serif;}}
header{{padding:28px 32px;border-bottom:1px solid rgba(0,232,255,.35);}}
h1{{margin:0;color:#00e8ff;letter-spacing:6px;font-size:22px;}}
.ans{{padding:20px 32px;color:#cfe8f4;line-height:1.5;max-width:980px;}}
table{{width:calc(100% - 64px);margin:10px 32px 40px;border-collapse:collapse;}}
th,td{{text-align:left;padding:14px 10px;border-bottom:1px solid rgba(0,232,255,.12);vertical-align:top;}}
th{{color:#00e8ff;font-size:11px;letter-spacing:2px;}}
a{{color:#6ec8ff;text-decoration:none;}}
.sn{{color:#8aa4b8;font-size:13px;margin-top:6px;}}
</style></head><body>
<header><h1>JARVIS · INTERNET</h1>
<p style="color:#8aa4b8">Query: {_esc(self.last_query)} · {len(self.last_results)} results</p></header>
<div class="ans"><strong>Answer</strong><br/>{_esc(self.last_answer) or 'See links below.'}</div>
<table><thead><tr><th>#</th><th>RESULT</th><th>SOURCE</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
        RESULTS_HTML.write_text(html, encoding="utf-8")


def _esc(s: Any) -> str:
    t = str(s or "")
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
