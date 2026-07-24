export const APP_ID = '{{SLUG}}'
export const APP_TITLE = '{{TITLE}}'
export const JARVIS_SCORE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_JARVIS_SCORE_URL) ||
  'http://127.0.0.1:8766/api/scores'

export const SEED = [
  {
    id: 1,
    title: 'Neon Briefing',
    tag: 'Ops',
    status: 'Live',
    power: 92,
    blurb: 'Morning status pack with weather, calendar, and priorities.',
  },
  {
    id: 2,
    title: 'Vault Notes',
    tag: 'Memory',
    status: 'Draft',
    power: 71,
    blurb: 'Pinned facts and project context for quick recall.',
  },
  {
    id: 3,
    title: 'Signal Desk',
    tag: 'Comms',
    status: 'Live',
    power: 88,
    blurb: 'Inbox triage board with starred threads and drafts.',
  },
  {
    id: 4,
    title: 'Forge Lab',
    tag: 'Build',
    status: 'Live',
    power: 95,
    blurb: 'Active builds, preview links, and ship checklist.',
  },
  {
    id: 5,
    title: 'Night Watch',
    tag: 'Ops',
    status: 'Paused',
    power: 54,
    blurb: 'Quiet-hours monitor for CPU, disk, and door alerts.',
  },
  {
    id: 6,
    title: 'Atlas Map',
    tag: 'Travel',
    status: 'Live',
    power: 79,
    blurb: 'Saved places, routes, and sector scans.',
  },
  {
    id: 7,
    title: 'Pulse Media',
    tag: 'Media',
    status: 'Draft',
    power: 63,
    blurb: 'Playlist queue and focus soundscapes.',
  },
  {
    id: 8,
    title: 'Healer Bay',
    tag: 'System',
    status: 'Live',
    power: 84,
    blurb: 'Process health, RAM pressure, and kill suggestions.',
  },
]

export const TAGS = ['All', 'Ops', 'Memory', 'Comms', 'Build', 'Travel', 'Media', 'System']
