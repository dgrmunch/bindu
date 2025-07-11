from flask import Flask, render_template, abort
import markdown
import os
import re
import json
import threading
import time

app = Flask(__name__)

VAULT_DIR = os.path.join(os.path.dirname(__file__), 'vault')
DB_PATH = os.path.join(os.path.dirname(__file__), 'vault_index.json')
INDEX_UPDATE_INTERVAL = 60  # seconds

def parse_links(content):
    return re.sub(r'\[\[([^\]]+)\]\]', r'<a href="/note/\1">\1</a>', content)

def get_note_content(note_name):
    note_file = note_map.get(note_name.lower())
    if not note_file:
        abort(404)
    with open(note_file, encoding='utf-8') as f:
        md_content = f.read()
    html = markdown.markdown(parse_links(md_content), extensions=['fenced_code', 'tables', 'toc'])
    return html, backlinks_map.get(note_name.lower(), [])

def update_vault_index():
    global note_map, backlinks_map
    while True:
        note_map = {}
        backlinks_map = {}
        link_graph = {}
        for root, dirs, files in os.walk(VAULT_DIR):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, VAULT_DIR)
                    identifier = file[:-3].lower()
                    note_map[identifier] = full_path

                    # Collect links
                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()
                    links = re.findall(r'\[\[([^\]]+)\]\]', content)
                    link_graph[identifier] = [link.strip().lower() for link in links]

        # Reverse the links to create backlinks
        backlinks_map = {k: [] for k in note_map}
        for src, targets in link_graph.items():
            for tgt in targets:
                if tgt in backlinks_map:
                    backlinks_map[tgt].append(src)

        # Save JSON DB
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"notes": note_map, "backlinks": backlinks_map}, f, indent=2)

        time.sleep(INDEX_UPDATE_INTERVAL)

@app.route('/')
def index():
    notes = sorted(note_map.keys())
    return render_template('index.html', notes=notes)

@app.route('/note/<note_name>')
def note(note_name):
    content, backlinks = get_note_content(note_name)
    return render_template('note.html', note_name=note_name, content=content, backlinks=backlinks)

# Launch background thread on startup
note_map = {}
backlinks_map = {}
threading.Thread(target=update_vault_index, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True)
