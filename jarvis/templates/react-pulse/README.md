# {{TITLE}}

Jarvis **Pulse Arena** — interactive React hub with search, filters, power meters, scoring, and publish configs.

## Commands

```bash
npm install
npm run dev          # local http://127.0.0.1:5173
npm run build        # production → dist/
npm run preview      # serve dist on :4173
```

## Publish

- **Vercel**: `npx vercel --prod` (or drag `dist/` after build)
- **Netlify**: `npx netlify deploy --prod --dir=dist`
- Or tell Jarvis: **publish app**

`vercel.json` and `netlify.toml` are included for SPA routing.

## Score sync

Events POST to Jarvis companion `http://127.0.0.1:8766/api/scores` (override with `VITE_JARVIS_SCORE_URL`). Say **app scores** to Jarvis for the leaderboard.
