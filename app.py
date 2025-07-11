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

note_map = {}
backlinks_map = {}

def parse_links(content):
    return re.sub(r'\[\[([^\]]+)\]\]', r'<a href="/note/\1">\1</a>', content)

def extract_tags(markdown_text):
    return list(set(re.findall(r'(?<![\w/])#(\w[\w/-]*)', markdown_text)))
def escape_tags(md_content):
    # Escape # at the start of words unless it's a markdown header line (start of line)
    # We'll replace tags like #label with \#label only if not at line start.
    # Safer to replace all standalone #tags with \#tag
    return re.sub(r'(?<!^)#(\w[\w/-]*)', r'\\#\1', md_content)

def parse_tags_links(content):
    # Replace #tagname with markdown links to /tag/tagname
    # Match #tagname preceded by non-word or line start, so not inside words
    # We'll avoid matching markdown headers (lines starting with # followed by space)
    # So we match only #tagname that are not at line start or followed by space (header)
    
    # This regex matches #tagname where tagname is letters, numbers, dash, or slash
    pattern = re.compile(r'(?<!\w)#(\w[\w/-]*)')

    def replacer(match):
        tag = match.group(1)
        return f'[#{tag}](/tag/{tag})'

    return pattern.sub(replacer, content)
def get_note_content(note_name):
    note_file = note_map.get(note_name.lower())
    if not note_file:
        abort(404)
    with open(note_file, encoding='utf-8') as f:
        md_content = f.read()

    md_content = parse_links(md_content)       # existing [[note]] links to HTML
    md_content = parse_tags_links(md_content)  # new #tag links to markdown links

    html = markdown.markdown(md_content, extensions=['fenced_code', 'tables', 'toc'])
    return html, backlinks_map.get(note_name.lower(), [])

def load_vault_db():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def update_vault_index():
    global note_map, backlinks_map
    while True:
        note_map = {}
        backlinks_map = {}
        link_graph = {}
        tag_map = {}

        for root, dirs, files in os.walk(VAULT_DIR):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, VAULT_DIR)
                    identifier = file[:-3].lower()
                    note_map[identifier] = full_path

                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()

                    links = re.findall(r'\[\[([^\]]+)\]\]', content)
                    tags = extract_tags(content)

                    link_graph[identifier] = [link.strip().lower() for link in links]
                    tag_map[identifier] = tags

        backlinks_map = {k: [] for k in note_map}
        for src, targets in link_graph.items():
            for tgt in targets:
                if tgt in backlinks_map:
                    backlinks_map[tgt].append(src)

        db = {
            "notes": note_map,
            "backlinks": backlinks_map,
            "tags": tag_map
        }

        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)

        time.sleep(INDEX_UPDATE_INTERVAL)

@app.route('/')
def index():
    notes = sorted(note_map.keys())
    return render_template('index.html', notes=notes)

@app.route('/note/<note_name>')
def note(note_name):
    content, backlinks = get_note_content(note_name)
    db = load_vault_db()
    tags = db.get("tags", {}).get(note_name.lower(), [])
    return render_template('note.html', note_name=note_name, content=content, backlinks=backlinks, tags=tags)

@app.route('/tag/<tag>')
def tag_view(tag):
    db = load_vault_db()
    tag_map = db.get("tags", {})
    notes = db.get("notes", {})
    notes_with_tag = {k: notes[k] for k, v in tag_map.items() if tag in v}
    return render_template('tag_view.html', tag=tag, notes=notes_with_tag)

# Background thread to build and refresh vault index
threading.Thread(target=update_vault_index, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True)
