import re

import pytest
from werkzeug.security import check_password_hash

from app import Note, User, create_app, db


@pytest.fixture
def app(tmp_path):
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'unit-test-key-only',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'test.db'),
    })
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def post(client, path, data=None, page='/login'):
    html = client.get(page).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    return client.post(path, data={**(data or {}), 'csrf_token': token}, follow_redirects=True)


def register(client, username):
    return post(client, '/register', {'username': username, 'password': 'Lab-test-password-123'}, '/register')


def test_authentication_persistence_and_hashing(app):
    client = app.test_client()
    assert client.get('/').status_code == 302
    assert b'Your account is ready' in register(client, 'gadeer').data
    result = post(client, '/notes', {'title': 'Cloud lab', 'body': 'Persistent note'}, '/')
    assert b'Persistent note' in result.data
    post(client, '/logout', page='/')
    wrong = post(client, '/login', {'username': 'gadeer', 'password': 'wrong'})
    assert b'Incorrect username or password' in wrong.data
    new_client = app.test_client()
    result = post(new_client, '/login', {'username': 'gadeer', 'password': 'Lab-test-password-123'})
    assert b'Persistent note' in result.data
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.password_hash != 'Lab-test-password-123'
        assert check_password_hash(user.password_hash, 'Lab-test-password-123')


def test_cross_user_access_is_denied(app):
    alice, bob = app.test_client(), app.test_client()
    register(alice, 'alice')
    post(alice, '/notes', {'title': 'Private note', 'body': 'Only Alice'}, '/')
    register(bob, 'bobby')
    assert b'Only Alice' not in bob.get('/').data
    with app.app_context():
        note_id = db.session.scalar(db.select(Note.id))
    assert post(bob, f'/notes/{note_id}/delete', page='/').status_code == 404
    assert b'Only Alice' in alice.get('/').data
    assert b'Note deleted' in post(alice, f'/notes/{note_id}/delete', page='/').data


def test_csrf_and_escaping(app):
    client = app.test_client()
    assert client.post('/register', data={'username': 'missingtoken'}).status_code == 400
    register(client, 'gadeer')
    result = post(client, '/notes', {'title': '<script>alert(1)</script>', 'body': '<img src=x onerror=alert(1)>'}, '/')
    assert b'<script>alert(1)</script>' not in result.data
    assert b'&lt;script&gt;' in result.data
    assert b'&lt;img' in result.data
    assert b'Note saved' in result.data


def test_validation_and_duplicate_accounts(app):
    client = app.test_client()
    assert b'Use a password' in post(client, '/register', {'username': 'gadeer', 'password': 'short'}, '/register').data
    register(client, 'gadeer')
    assert b'Add a title' in post(client, '/notes', {'title': ' ', 'body': 'text'}, '/').data
    post(client, '/logout', page='/')
    assert b'already taken' in register(client, 'gadeer').data


def test_https_cookie_setting(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'secure.db'), 'SESSION_COOKIE_SECURE': True})
    response = app.test_client().get('/register', base_url='https://example.test')
    assert 'Secure' in response.headers['Set-Cookie']
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert 'SameSite=Lax' in response.headers['Set-Cookie']
