#!/usr/bin/env python3
"""
CIRA CDRP Decision Search Engine
SQLite FTS5-backed boolean full-text search over all CIRA domain dispute decisions.

Boolean search syntax (SQLite FTS5):
  - AND:  trademark AND transfer        (both terms must appear)
  - OR:   registrant OR respondent       (either term)
  - NOT:  domain NOT parking             (exclude term)
  - Phrase: "bad faith"                  (exact phrase)
  - Prefix: trade*                       (prefix match)
  - Group: (trademark OR trade-mark) AND "bad faith"
  - NEAR:  NEAR(complainant registrant, 10)  (within 10 tokens)

Run: python3 search_server.py
Then open: http://localhost:8642
"""

import sqlite3, json, os, html, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cira_search_v2.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search(query, limit=50, offset=0):
    conn = get_db()
    try:
        # FTS5 search with snippet extraction
        rows = conn.execute("""
            SELECT d.id, d.filename, d.page_num, d.domain_label, d.char_count,
                   snippet(decisions_fts, 2, '<mark>', '</mark>', '...', 40) as snippet,
                   rank
            FROM decisions_fts
            JOIN decisions d ON d.id = decisions_fts.rowid
            WHERE decisions_fts MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
        """, (query, limit, offset)).fetchall()

        count = conn.execute("""
            SELECT COUNT(*) FROM decisions_fts WHERE decisions_fts MATCH ?
        """, (query,)).fetchone()[0]

        return {"results": [dict(r) for r in rows], "total": count, "query": query}
    except Exception as e:
        return {"error": str(e), "query": query, "results": [], "total": 0}
    finally:
        conn.close()

def get_full_text(doc_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_stats():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        chars = conn.execute("SELECT SUM(char_count) FROM decisions").fetchone()[0]
        pages = conn.execute("SELECT DISTINCT page_num FROM decisions ORDER BY page_num").fetchall()
        return {"total_decisions": total, "total_characters": chars,
                "pages": [r[0] for r in pages]}
    finally:
        conn.close()

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CIRA CDRP Decision Search</title>
<style>
:root { --bg: #f8f9fa; --card: #fff; --border: #dee2e6; --primary: #2563eb; --text: #212529; --muted: #6c757d; --mark: #fef3cd; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
.container { max-width: 960px; margin: 0 auto; padding: 20px; }
header { padding: 30px 0 20px; text-align: center; }
header h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
header p { color: var(--muted); font-size: 14px; }
.search-box { display: flex; gap: 8px; margin: 20px 0; }
.search-box input { flex: 1; padding: 12px 16px; border: 2px solid var(--border); border-radius: 8px; font-size: 16px; outline: none; transition: border-color 0.2s; }
.search-box input:focus { border-color: var(--primary); }
.search-box button { padding: 12px 24px; background: var(--primary); color: #fff; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; font-weight: 600; }
.search-box button:hover { background: #1d4ed8; }
.help-toggle { text-align: right; margin-bottom: 10px; }
.help-toggle a { color: var(--primary); cursor: pointer; font-size: 13px; text-decoration: none; }
.help-panel { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; font-size: 13px; display: none; }
.help-panel.visible { display: block; }
.help-panel h3 { margin-bottom: 8px; font-size: 14px; }
.help-panel code { background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-size: 12px; }
.help-panel table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.help-panel td { padding: 4px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
.help-panel td:first-child { white-space: nowrap; font-weight: 600; width: 40%; }
.stats { color: var(--muted); font-size: 14px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.result { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.result-domain { font-weight: 700; font-size: 16px; color: var(--primary); }
.result-page { font-size: 12px; color: var(--muted); background: #e9ecef; padding: 2px 8px; border-radius: 12px; }
.result-snippet { font-size: 14px; color: #495057; line-height: 1.6; }
.result-snippet mark { background: var(--mark); padding: 1px 2px; border-radius: 2px; }
.result-footer { margin-top: 8px; display: flex; gap: 12px; align-items: center; }
.result-footer a { color: var(--primary); text-decoration: none; font-size: 13px; cursor: pointer; }
.result-footer span { color: var(--muted); font-size: 12px; }
.full-text-panel { margin-top: 12px; background: #f8f9fa; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-size: 13px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; display: none; }
.full-text-panel.visible { display: block; }
.pagination { text-align: center; margin: 20px 0; }
.pagination button { padding: 8px 16px; margin: 0 4px; border: 1px solid var(--border); background: var(--card); border-radius: 6px; cursor: pointer; }
.pagination button:hover { background: #e9ecef; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.no-results { text-align: center; padding: 40px; color: var(--muted); }
#loading { display: none; text-align: center; padding: 20px; color: var(--muted); }
.db-stats { text-align: center; color: var(--muted); font-size: 13px; margin-top: 20px; }
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>CIRA CDRP Decision Search Engine</h1>
        <p>Full-text boolean search across all Canadian domain dispute decisions</p>
    </header>

    <div class="search-box">
        <input type="text" id="q" placeholder='Search decisions... e.g. "bad faith" AND trademark' autofocus>
        <button onclick="doSearch()">Search</button>
    </div>

    <div class="help-toggle"><a onclick="toggleHelp()">Boolean search syntax help</a></div>
    <div class="help-panel" id="help">
        <h3>Search Operators</h3>
        <table>
            <tr><td><code>term1 AND term2</code></td><td>Both terms must appear in the document</td></tr>
            <tr><td><code>term1 OR term2</code></td><td>Either term can appear</td></tr>
            <tr><td><code>NOT term</code></td><td>Exclude documents containing term</td></tr>
            <tr><td><code>"exact phrase"</code></td><td>Match an exact phrase</td></tr>
            <tr><td><code>trade*</code></td><td>Prefix match (trademark, trade-mark, etc.)</td></tr>
            <tr><td><code>(A OR B) AND C</code></td><td>Group terms with parentheses</td></tr>
            <tr><td><code>NEAR(term1 term2, 5)</code></td><td>Terms within 5 words of each other</td></tr>
        </table>
        <p style="margin-top:10px;color:#6c757d;">Examples: <code>"bad faith"</code> &bull; <code>trademark AND transfer</code> &bull; <code>registrant AND NOT parking</code> &bull; <code>NEAR(domain complainant, 10)</code></p>
    </div>

    <div id="stats" class="stats" style="display:none;"></div>
    <div id="loading">Searching...</div>
    <div id="results"></div>
    <div id="pagination" class="pagination"></div>
    <div id="db-stats" class="db-stats"></div>
</div>

<script>
let currentQuery = '';
let currentOffset = 0;
const LIMIT = 30;

document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

function toggleHelp() {
    document.getElementById('help').classList.toggle('visible');
}

async function doSearch(offset = 0) {
    const q = document.getElementById('q').value.trim();
    if (!q) return;
    currentQuery = q;
    currentOffset = offset;
    document.getElementById('loading').style.display = 'block';
    document.getElementById('results').innerHTML = '';
    document.getElementById('pagination').innerHTML = '';

    try {
        const res = await fetch('/search?q=' + encodeURIComponent(q) + '&limit=' + LIMIT + '&offset=' + offset);
        const data = await res.json();
        document.getElementById('loading').style.display = 'none';

        if (data.error) {
            document.getElementById('results').innerHTML = '<div class="no-results">Search error: ' + escHtml(data.error) + '<br><br>Check your boolean syntax.</div>';
            document.getElementById('stats').style.display = 'none';
            return;
        }

        document.getElementById('stats').style.display = 'block';
        document.getElementById('stats').textContent = data.total + ' decision' + (data.total !== 1 ? 's' : '') + ' matched' + (data.total > LIMIT ? ' (showing ' + (offset+1) + '-' + Math.min(offset+LIMIT, data.total) + ')' : '');

        if (data.results.length === 0) {
            document.getElementById('results').innerHTML = '<div class="no-results">No decisions found. Try different search terms or boolean operators.</div>';
            return;
        }

        let html = '';
        data.results.forEach(r => {
            html += '<div class="result">' +
                '<div class="result-header">' +
                    '<span class="result-domain">' + escHtml(r.domain_label) + '</span>' +
                    '<span class="result-page">Page ' + r.page_num + '</span>' +
                '</div>' +
                '<div class="result-snippet">' + r.snippet + '</div>' +
                '<div class="result-footer">' +
                    '<a onclick="toggleFull(' + r.id + ')">View full text</a>' +
                    '<span>' + (r.char_count || 0).toLocaleString() + ' chars</span>' +
                    '<span>' + escHtml(r.filename) + '</span>' +
                '</div>' +
                '<div class="full-text-panel" id="full-' + r.id + '"></div>' +
            '</div>';
        });
        document.getElementById('results').innerHTML = html;

        // Pagination
        if (data.total > LIMIT) {
            let pHtml = '';
            if (offset > 0) pHtml += '<button onclick="doSearch(' + (offset - LIMIT) + ')">Previous</button>';
            pHtml += '<span style="color:#6c757d;margin:0 8px;">Page ' + (Math.floor(offset/LIMIT)+1) + ' of ' + Math.ceil(data.total/LIMIT) + '</span>';
            if (offset + LIMIT < data.total) pHtml += '<button onclick="doSearch(' + (offset + LIMIT) + ')">Next</button>';
            document.getElementById('pagination').innerHTML = pHtml;
        }
    } catch(e) {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('results').innerHTML = '<div class="no-results">Network error: ' + e.message + '</div>';
    }
}

async function toggleFull(id) {
    const el = document.getElementById('full-' + id);
    if (el.classList.contains('visible')) { el.classList.remove('visible'); return; }
    if (!el.dataset.loaded) {
        el.textContent = 'Loading...';
        el.classList.add('visible');
        const res = await fetch('/doc?id=' + id);
        const data = await res.json();
        el.textContent = data.full_text || 'No text available.';
        el.dataset.loaded = '1';

        // Highlight search terms in full text
        if (currentQuery) {
            const terms = currentQuery.replace(/AND|OR|NOT|NEAR\([^)]+\)/gi, '').replace(/[()""*]/g, '').trim().split(/\s+/).filter(t => t.length > 2);
            let txt = escHtml(el.textContent);
            terms.forEach(t => {
                const re = new RegExp('(' + t.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
                txt = txt.replace(re, '<mark>$1</mark>');
            });
            el.innerHTML = txt;
        }
    } else {
        el.classList.add('visible');
    }
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// Load DB stats on page load
fetch('/stats').then(r => r.json()).then(s => {
    document.getElementById('db-stats').textContent = s.total_decisions + ' decisions indexed | ' + (s.total_characters || 0).toLocaleString() + ' characters | Pages ' + (s.pages?.[0] || '?') + '-' + (s.pages?.[s.pages.length-1] || '?');
});
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/search':
            params = parse_qs(parsed.query)
            q = params.get('q', [''])[0]
            limit = int(params.get('limit', ['30'])[0])
            offset = int(params.get('offset', ['0'])[0])
            result = search(q, limit, offset)
            self._json(result)
        elif parsed.path == '/doc':
            params = parse_qs(parsed.query)
            doc_id = int(params.get('id', ['0'])[0])
            result = get_full_text(doc_id)
            self._json(result or {"error": "not found"})
        elif parsed.path == '/stats':
            self._json(get_stats())
        else:
            self._html(HTML_PAGE)

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(content.encode())

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8642))
    print(f"CIRA CDRP Decision Search Engine")
    print(f"Database: {DB_PATH}")
    print(f"Starting server at http://localhost:{port}")
    print(f"Press Ctrl+C to stop\n")
    server = HTTPServer(('0.0.0.0', port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
