import json
import os
import re
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request
from src.models.note import Note, db

note_bp = Blueprint('note', __name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ALLOWED_TARGETS = {
    'Simplified Chinese',
    'English',
    'Japanese',
    'Korean',
    'French',
    'German',
    'Spanish',
    'Portuguese',
    'Russian',
    'Arabic',
}

def _load_translate_config():
    api_key = os.environ.get('TRANSLATE_API_KEY', '').strip()
    endpoint = os.environ.get('TRANSLATE_ENDPOINT', '').strip()
    model = os.environ.get('TRANSLATE_MODEL', '').strip()
    if not (api_key and endpoint and model):
        try:
            with open(os.path.join(ROOT_DIR, '.env'), encoding='utf-8') as env_file:
                for line in env_file:
                    line = line.strip()
                    if line.startswith('API key:') and not api_key:
                        api_key = line.split(':', 1)[1].strip()
                    elif line.startswith('Endpoint:') and not endpoint:
                        endpoint = line.split(':', 1)[1].strip()
                    elif line.startswith('Model name:') and not model:
                        model = line.split(':', 1)[1].strip()
        except OSError as exc:
            raise RuntimeError('Translation is not configured') from exc
    if not api_key or not endpoint or not model:
        raise RuntimeError('Translation is not configured')
    return api_key, endpoint, model

def _load_prompt(target, title, content):
    path = os.path.join(ROOT_DIR, 'prompt', 'translate.md')
    try:
        with open(path, encoding='utf-8') as prompt_file:
            template = prompt_file.read()
    except OSError as exc:
        raise RuntimeError('Translation prompt is missing') from exc
    values = {'{target}': target, '{title}': title, '{content}': content}
    parts = re.split(r'(\{target\}|\{title\}|\{content\})', template)
    return ''.join(values.get(part, part) for part in parts)

def _parse_translation(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Translation response was not valid JSON') from exc
    if not isinstance(data, dict):
        raise RuntimeError('Translation response was not valid JSON')
    title = data.get('title', '')
    content = data.get('content', '')
    if not isinstance(title, str) or not isinstance(content, str):
        raise RuntimeError('Translation response was not valid JSON')
    return {'title': title, 'content': content}

def _call_model(prompt):
    api_key, endpoint, model = _load_translate_config()
    body = json.dumps({
        'model': model,
        'temperature': 0,
        'stream': False,
        'messages': [{'role': 'user', 'content': prompt}],
    }).encode()
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Translation service returned {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError('Translation service is unavailable') from exc
    try:
        text = payload['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError('Translation response was incomplete') from exc
    return _parse_translation(text)

@note_bp.route('/notes', methods=['GET'])
def get_notes():
    """Get all notes, ordered by most recently updated"""
    notes = Note.query.order_by(Note.updated_at.desc()).all()
    return jsonify([note.to_dict() for note in notes])

@note_bp.route('/notes', methods=['POST'])
def create_note():
    """Create a new note"""
    try:
        data = request.json
        if not data or 'title' not in data or 'content' not in data:
            return jsonify({'error': 'Title and content are required'}), 400
        
        note = Note(title=data['title'], content=data['content'])
        db.session.add(note)
        db.session.commit()
        return jsonify(note.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """Get a specific note by ID"""
    note = Note.query.get_or_404(note_id)
    return jsonify(note.to_dict())

@note_bp.route('/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Update a specific note"""
    try:
        note = Note.query.get_or_404(note_id)
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        note.title = data.get('title', note.title)
        note.content = data.get('content', note.content)
        db.session.commit()
        return jsonify(note.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a specific note"""
    try:
        note = Note.query.get_or_404(note_id)
        db.session.delete(note)
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/search', methods=['GET'])
def search_notes():
    """Search notes by title or content"""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    notes = Note.query.filter(
        (Note.title.contains(query)) | (Note.content.contains(query))
    ).order_by(Note.updated_at.desc()).all()
    
    return jsonify([note.to_dict() for note in notes])

@note_bp.route('/translate', methods=['POST'])
def translate_note():
    """Translate the open note title and content. Does not save the note."""
    data = request.json or {}
    target = data.get('target')
    if target not in ALLOWED_TARGETS:
        return jsonify({'error': 'Unsupported target language'}), 400
    title = data.get('title') or ''
    content = data.get('content') or ''
    if not isinstance(title, str) or not isinstance(content, str):
        return jsonify({'error': 'Title and content must be text'}), 400
    if not title.strip() and not content.strip():
        return jsonify({'error': 'Title and content are required'}), 400
    try:
        return jsonify(_call_model(_load_prompt(target, title, content)))
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 502

