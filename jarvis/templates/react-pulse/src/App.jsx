import React, { useEffect, useMemo, useState } from 'react'
import { SEED, TAGS, APP_TITLE } from './data.js'
import { getScoreState, track } from './telemetry.js'

const statusClass = (s) => {
  const v = (s || '').toLowerCase()
  if (v === 'live') return 'pill live'
  if (v === 'draft') return 'pill draft'
  return 'pill paused'
}

function Ring({ value, label }) {
  const pct = Math.max(0, Math.min(100, value))
  const r = 34
  const c = 2 * Math.PI * r
  const offset = c - (pct / 100) * c
  return (
    <div className="ring" title={label}>
      <svg viewBox="0 0 80 80" aria-hidden="true">
        <circle className="ring-bg" cx="40" cy="40" r={r} />
        <circle
          className="ring-fg"
          cx="40"
          cy="40"
          r={r}
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="ring-label">
        <b>{Math.round(pct)}</b>
        <span>{label}</span>
      </div>
    </div>
  )
}

export default function App() {
  const [items, setItems] = useState(() => {
    try {
      const raw = localStorage.getItem(`jarvis-pulse-items:{{SLUG}}`)
      return raw ? JSON.parse(raw) : SEED
    } catch {
      return SEED
    }
  })
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('All')
  const [selectedId, setSelectedId] = useState(SEED[0]?.id ?? null)
  const [draft, setDraft] = useState({ title: '', tag: 'Ops', blurb: '', status: 'Draft', power: 70 })
  const [scores, setScores] = useState(getScoreState)
  const [flash, setFlash] = useState('')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const next = track('visit', { points: 5, label: 'session' })
    setScores({ ...next })
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(`jarvis-pulse-items:{{SLUG}}`, JSON.stringify(items))
    } catch {
      /* ignore */
    }
  }, [items])

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 4000)
    return () => clearInterval(id)
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter((item) => {
      const tagOk = tag === 'All' || item.tag === tag
      if (!tagOk) return false
      if (!q) return true
      return (
        item.title.toLowerCase().includes(q) ||
        item.blurb.toLowerCase().includes(q) ||
        item.tag.toLowerCase().includes(q) ||
        item.status.toLowerCase().includes(q)
      )
    })
  }, [items, query, tag])

  const selected = items.find((i) => i.id === selectedId) || filtered[0] || null
  const liveCount = items.filter((i) => i.status === 'Live').length
  const avgPower = items.length
    ? Math.round(items.reduce((a, i) => a + (i.power || 0), 0) / items.length)
    : 0

  function bump(msg, points, kind = 'action', meta = {}) {
    const next = track(kind, { points, label: msg, meta })
    setScores({ ...next })
    setFlash(`+${points} ${msg}`)
    setTimeout(() => setFlash(''), 1400)
  }

  function onSearch(value) {
    setQuery(value)
    if (value.trim().length === 1 || value.trim().length === 3) {
      bump('search', 2, 'search', { q: value.slice(0, 40) })
    }
  }

  function addItem(e) {
    e.preventDefault()
    if (!draft.title.trim()) return
    const next = {
      id: Date.now(),
      title: draft.title.trim(),
      tag: draft.tag,
      status: draft.status,
      power: Number(draft.power) || 70,
      blurb: draft.blurb.trim() || 'New module forged in the arena.',
    }
    setItems((prev) => [next, ...prev])
    setSelectedId(next.id)
    setDraft({ title: '', tag: 'Ops', blurb: '', status: 'Draft', power: 70 })
    setQuery('')
    setTag('All')
    bump('forge module', 25, 'score', { title: next.title })
  }

  function toggleStatus(id) {
    setItems((prev) =>
      prev.map((item) => {
        if (item.id !== id) return item
        const order = ['Live', 'Draft', 'Paused']
        const i = order.indexOf(item.status)
        return { ...item, status: order[(i + 1) % order.length] }
      })
    )
    bump('status cycle', 8, 'score')
  }

  function boostPower(id) {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, power: Math.min(100, (item.power || 0) + 7) }
          : item
      )
    )
    bump('power boost', 12, 'score')
  }

  function openCard(id) {
    setSelectedId(id)
    bump('inspect', 3, 'action')
  }

  return (
    <div className="shell">
      <div className="aurora" aria-hidden="true" />
      <div className="grid-fx" aria-hidden="true" />

      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Jarvis Pulse Arena · v1</p>
          <h1>{APP_TITLE}</h1>
          <p className="lede">
            Search the board, rack up points, boost module power, and ship — Jarvis
            tracks your scoreboard live.
          </p>
          <div className="hero-actions">
            <button type="button" className="btn primary" onClick={() => bump('combo', 15, 'score')}>
              Score combo +15
            </button>
            <a className="btn ghost" href="#board">
              Enter board
            </a>
          </div>
        </div>
        <div className="hero-meters">
          <Ring value={Math.min(100, scores.points % 100 || scores.points)} label="Pulse" />
          <Ring value={avgPower} label="Power" />
          <Ring value={Math.min(100, scores.streak * 12)} label="Streak" />
        </div>
      </header>

      <section className="scorebar" aria-live="polite">
        <div className="score-chip"><span>Score</span><b>{scores.points}</b></div>
        <div className="score-chip"><span>Best</span><b>{scores.best}</b></div>
        <div className="score-chip"><span>Streak</span><b>{scores.streak}d</b></div>
        <div className="score-chip"><span>Visits</span><b>{scores.visits}</b></div>
        <div className="score-chip"><span>Live</span><b>{liveCount}</b></div>
        {flash ? <div className="flash">{flash}</div> : null}
      </section>

      <div className="toolbar" id="board">
        <label className="search">
          <span className="search-ico" aria-hidden="true">⌕</span>
          <input
            value={query}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search modules, tags, status…"
            aria-label="Search modules"
          />
          {query ? (
            <button type="button" className="clear" onClick={() => setQuery('')}>
              Clear
            </button>
          ) : null}
        </label>
        <div className="tags" role="tablist" aria-label="Filter by tag">
          {TAGS.map((t) => (
            <button
              key={t}
              type="button"
              className={`tag ${tag === t ? 'on' : ''}`}
              onClick={() => {
                setTag(t)
                bump('filter', 1, 'action', { tag: t })
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="layout">
        <section>
          {filtered.length === 0 ? (
            <div className="empty">No modules match “{query || tag}”. Forge a new one →</div>
          ) : (
            <div className="cards">
              {filtered.map((item, idx) => (
                <article
                  key={item.id}
                  className={`card ${selected?.id === item.id ? 'selected' : ''}`}
                  style={{ animationDelay: `${idx * 40}ms` }}
                  onClick={() => openCard(item.id)}
                >
                  <div className="card-top">
                    <span className="pill">{item.tag}</span>
                    <span className={statusClass(item.status)}>{item.status}</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.blurb}</p>
                  <div className="power">
                    <div className="power-track">
                      <i style={{ width: `${item.power || 0}%` }} />
                    </div>
                    <span>{item.power || 0}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="side">
          {selected ? (
            <>
              <p className="side-kicker">Module detail</p>
              <h2>{selected.title}</h2>
              <div className="meta">
                {selected.tag} · {selected.status} · power {selected.power}
              </div>
              <p>{selected.blurb}</p>
              <div className="side-actions">
                <button type="button" className="btn amber" onClick={() => toggleStatus(selected.id)}>
                  Cycle status
                </button>
                <button type="button" className="btn primary" onClick={() => boostPower(selected.id)}>
                  Boost +7
                </button>
              </div>
            </>
          ) : (
            <p className="meta">Select a card to inspect it.</p>
          )}

          <form className="composer" onSubmit={addItem}>
            <strong>Forge module</strong>
            <input
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              placeholder="Title"
              required
            />
            <div className="row2">
              <select
                value={draft.tag}
                onChange={(e) => setDraft({ ...draft, tag: e.target.value })}
              >
                {TAGS.filter((t) => t !== 'All').map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value })}
              >
                <option>Live</option>
                <option>Draft</option>
                <option>Paused</option>
              </select>
            </div>
            <label className="power-input">
              Power {draft.power}
              <input
                type="range"
                min="20"
                max="100"
                value={draft.power}
                onChange={(e) => setDraft({ ...draft, power: Number(e.target.value) })}
              />
            </label>
            <textarea
              value={draft.blurb}
              onChange={(e) => setDraft({ ...draft, blurb: e.target.value })}
              placeholder="Short description"
            />
            <button type="submit" className="btn primary wide">Add to arena · +25</button>
          </form>

          <p className="foot">
            Tick {tick} · scores sync to Jarvis when online · publish with{' '}
            <code>npm run build</code> or say “publish app”
          </p>
        </aside>
      </div>
    </div>
  )
}
