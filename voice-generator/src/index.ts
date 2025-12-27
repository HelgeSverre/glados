import { Hono } from 'hono';
import { serveStatic } from 'hono/bun';
import { createEntry, getAllEntries, getEntry } from './db';

const app = new Hono();

// Serve static files from public directory
app.use('/audio/*', serveStatic({ root: './public' }));
app.use('/styles.css', serveStatic({ root: './public' }));

// Serve index.html for root
app.get('/', async (c) => {
  const file = Bun.file('./public/index.html');
  return c.html(await file.text());
});

// API: Create new entry
app.post('/api/generate', async (c) => {
  const body = await c.req.parseBody();
  const text = body.text as string;

  if (!text || text.trim().length === 0) {
    return c.redirect('/?error=empty');
  }

  if (text.length > 2000) {
    return c.redirect('/?error=toolong');
  }

  createEntry(text.trim());
  return c.redirect('/');
});

// API: Get all entries (JSON)
app.get('/api/entries', (c) => {
  const entries = getAllEntries();
  return c.json(entries);
});

// API: Get single entry (for polling status)
app.get('/api/entries/:id', (c) => {
  const id = parseInt(c.req.param('id'));
  const entry = getEntry(id);
  if (!entry) {
    return c.json({ error: 'Not found' }, 404);
  }
  return c.json(entry);
});

const PORT = parseInt(process.env.PORT || '3000');

console.log(`GLaDOS Voice Generator running at http://localhost:${PORT}`);

export default {
  port: PORT,
  fetch: app.fetch,
};
