from flask import Flask, render_template, abort, url_for
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

# Global variables to hold vault data
note_map = {}       # note identifier (lowercase) -> full path to .md file
backlinks_map = {}  # note identifier -> list of notes that link here
link_graph = {}     # note identifier -> list of notes this note links to

def parse_links(content):
    # Replace [[note]] with <a href="/note/note">note</a>
    return re.sub(r'\[\[([^\]]+)\]\]', r'<a href="/note/\1">\1</a>', content)

def parse_tags_links(content):
    # Replace #tag with markdown-style link [#tag](/tag/tag)
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

    # First replace [[note]] with HTML links
    md_content = parse_links(md_content)

    # Then replace #tags with markdown links
    md_content = parse_tags_links(md_content)

    html = markdown.markdown(md_content, extensions=['fenced_code', 'tables', 'toc'])
    backlinks = backlinks_map.get(note_name.lower(), [])
    forwardlinks = link_graph.get(note_name.lower(), [])
    return html, backlinks, forwardlinks

def update_vault_index():
    global note_map, backlinks_map, link_graph
    while True:
        temp_note_map = {}
        temp_link_graph = {}

        # Scan vault for .md files
        for root, dirs, files in os.walk(VAULT_DIR):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    identifier = file[:-3].lower()  # remove .md and lowercase
                    temp_note_map[identifier] = full_path

                    # Read file content to find links
                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()
                    links = re.findall(r'\[\[([^\]]+)\]\]', content)
                    temp_link_graph[identifier] = [link.strip().lower() for link in links]

        # Build backlinks map by reversing the links
        temp_backlinks_map = {k: [] for k in temp_note_map}
        for src, targets in temp_link_graph.items():
            for tgt in targets:
                if tgt in temp_backlinks_map:
                    temp_backlinks_map[tgt].append(src)

        # Atomically replace globals
        note_map = temp_note_map
        link_graph = temp_link_graph
        backlinks_map = temp_backlinks_map

        # Save to JSON database (optional)
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "notes": note_map,
                "forwardlinks": link_graph,
                "backlinks": backlinks_map
            }, f, indent=2)

        time.sleep(INDEX_UPDATE_INTERVAL)

@app.route('/')
def index():
    notes = sorted(note_map.keys())
    return render_template('index.html', notes=notes)
def extract_tags_from_content(content):
    return re.findall(r'(?<!\w)#([\w/-]+)', content)
@app.route('/note/<note_name>')
def note(note_name):
    note_file = note_map.get(note_name.lower())
    if not note_file:
        abort(404)
    with open(note_file, encoding='utf-8') as f:
        raw_md = f.read()

    tags = extract_tags_from_content(raw_md)
    content, backlinks, forwardlinks = get_note_content(note_name)

    # Combine backlinks and forwardlinks for graph
    # We make a dict of neighbors: note -> list of linked notes (both directions)
    graph_nodes = set(backlinks + forwardlinks + [note_name.lower()])
    edges = []

    for src in backlinks:
        edges.append({"from": src, "to": note_name.lower()})  # backlink edge

    for tgt in forwardlinks:
        edges.append({"from": note_name.lower(), "to": tgt})  # forwardlink edge

    return render_template('note.html',
                           note_name=note_name,
                           content=content,
                           backlinks=backlinks,
                           forwardlinks=forwardlinks,
                           tags=tags,
                           graph_nodes=list(graph_nodes),
                           graph_edges=edges)


@app.route('/tag/<path:tag>')
def tag_view(tag):
    # Load DB from file
    try:
        with open(DB_PATH, encoding='utf-8') as f:
            db = json.load(f)
    except Exception:
        db = {"notes": {}, "backlinks": {}, "forwardlinks": {}}

    notes_with_tag = []
    for note_id, path in db.get("notes", {}).items():
        # read the note content and check for #tag (simple)
        try:
            with open(path, encoding='utf-8') as nf:
                content = nf.read()
                if re.search(r'(?<!\w)#' + re.escape(tag) + r'(?!\w)', content):
                    notes_with_tag.append(note_id)
        except Exception:
            continue

    return render_template('tag_view.html', tag=tag, notes=notes_with_tag)


# Start background thread for vault indexing
threading.Thread(target=update_vault_index, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True)
