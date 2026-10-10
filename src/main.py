import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.note import note_bp
from src.models.note import Note

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Enable CORS for all routes
CORS(app)

# register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(note_bp, url_prefix='/api')
ROOT_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

def _database_url():
    raw = None
    try:
        with open(os.path.join(ROOT_DIR, '.env'), encoding='utf-8') as env_file:
            for line in env_file:
                line = line.strip()
                if line.startswith('Database URL:'):
                    raw = line.split(':', 1)[1].strip()
                    break
    except OSError as exc:
        raise RuntimeError('Database URL is not configured') from exc
    if not raw:
        raise RuntimeError('Database URL is not configured')
    if raw.startswith('postgresql+psycopg://'):
        return raw
    if raw.startswith('postgresql://'):
        return 'postgresql+psycopg://' + raw[len('postgresql://'):]
    if raw.startswith('postgres://'):
        return 'postgresql+psycopg://' + raw[len('postgres://'):]
    raise RuntimeError('Database URL must start with postgresql://')

app.config['SQLALCHEMY_DATABASE_URI'] = _database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
