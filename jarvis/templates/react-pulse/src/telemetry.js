import { APP_ID, APP_TITLE, JARVIS_SCORE_URL } from './data.js'

const STORAGE_KEY = `jarvis-pulse:${APP_ID}`

function loadLocal() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveLocal(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* ignore quota */
  }
}

export function getScoreState() {
  const s = loadLocal()
  return {
    points: Number(s.points) || 0,
    streak: Number(s.streak) || 0,
    best: Number(s.best) || 0,
    visits: Number(s.visits) || 0,
    searches: Number(s.searches) || 0,
    lastDay: s.lastDay || '',
  }
}

async function postJarvis(payload) {
  try {
    await fetch(JARVIS_SCORE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        app_id: APP_ID,
        title: APP_TITLE,
        publish_url: window.location?.origin || '',
        ...payload,
      }),
      mode: 'cors',
      keepalive: true,
    })
  } catch {
    /* Jarvis offline — local score still counts */
  }
}

export function track(kind, { points = 0, label = '', meta = {} } = {}) {
  const s = getScoreState()
  const today = new Date().toISOString().slice(0, 10)
  if (kind === 'visit') {
    s.visits += 1
    if (s.lastDay && s.lastDay !== today) {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
      s.streak = s.lastDay === yesterday ? s.streak + 1 : 1
    } else if (!s.lastDay) {
      s.streak = 1
    }
    s.lastDay = today
  }
  if (kind === 'search') s.searches += 1
  if (points) {
    s.points += points
    s.best = Math.max(s.best, s.points)
  }
  saveLocal(s)
  postJarvis({ kind, points, label: label || kind, meta })
  return s
}

export function resetScores() {
  saveLocal({ points: 0, streak: 0, best: 0, visits: 0, searches: 0, lastDay: '' })
  postJarvis({ kind: 'action', points: 0, label: 'reset' })
}
