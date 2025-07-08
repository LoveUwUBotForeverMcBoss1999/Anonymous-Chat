from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import time
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Optimized SocketIO configuration
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25
)

# Efficient user management
users = {}  # {session_id: {'username': str, 'last_seen': float}}
user_lock = threading.Lock()


def cleanup_inactive_users():
    """Remove users who haven't been seen for 30 seconds"""
    while True:
        current_time = time.time()
        with user_lock:
            inactive_users = [
                sid for sid, user in users.items()
                if current_time - user['last_seen'] > 30
            ]
            for sid in inactive_users:
                if sid in users:
                    del users[sid]
        time.sleep(10)


# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_inactive_users, daemon=True)
cleanup_thread.start()


@app.route('/')
def index():
    # Serve the HTML directly
    with open('index.html', 'r') as f:
        return f.read()


@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    print(f'User connected: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnection"""
    with user_lock:
        if request.sid in users:
            username = users[request.sid]['username']
            del users[request.sid]

            # Broadcast updated user list
            user_list = [user['username'] for user in users.values()]
            emit('user_list', user_list, broadcast=True)

            print(f'User disconnected: {username}')


@socketio.on('join')
def handle_join(data):
    """Handle user joining the chat"""
    username = data['username']

    with user_lock:
        # Check if username already exists
        existing_usernames = [user['username'] for user in users.values()]
        if username in existing_usernames:
            original_username = username
            counter = 1
            while username in existing_usernames:
                username = f"{original_username}_{counter}"
                counter += 1

        # Add user
        users[request.sid] = {
            'username': username,
            'last_seen': time.time()
        }

        # Send updated user list to everyone
        user_list = [user['username'] for user in users.values()]
        emit('user_list', user_list, broadcast=True)

        print(f'User joined: {username}')


@socketio.on('message')
def handle_message(data):
    """Handle chat messages"""
    if request.sid not in users:
        return

    with user_lock:
        users[request.sid]['last_seen'] = time.time()
        username = users[request.sid]['username']

    message_data = {
        'username': username,
        'message': data['message'],
        'timestamp': time.time()
    }

    emit('message', message_data, broadcast=True)


@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators"""
    if request.sid not in users:
        return

    with user_lock:
        users[request.sid]['last_seen'] = time.time()
        username = users[request.sid]['username']

    emit('user_typing', {
        'username': username,
        'typing': data['typing']
    }, broadcast=True, include_self=False)


@socketio.on('ping')
def handle_ping():
    """Handle latency ping"""
    emit('pong')


if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)