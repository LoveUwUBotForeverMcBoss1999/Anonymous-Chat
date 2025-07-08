from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import random
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Configure for Vercel - polling only, no WebSocket
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    transport=['polling'],  # Only polling, no websocket
                    async_mode='threading')

# Store active users
active_users = {}
waiting_queue = []
matching_lock = threading.Lock()


def generate_random_name():
    """Generate a random username"""
    adjectives = ['Cool', 'Fast', 'Smart', 'Funny', 'Wild', 'Brave', 'Quick', 'Sharp', 'Bright', 'Swift']
    nouns = ['Tiger', 'Eagle', 'Wolf', 'Fox', 'Bear', 'Lion', 'Shark', 'Falcon', 'Panther', 'Hawk']
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(10, 99)}"


def auto_match_users():
    """Auto-match users every 2 seconds"""
    while True:
        time.sleep(2)
        with matching_lock:
            if len(waiting_queue) >= 2:
                # Get two users from queue
                user1_sid = waiting_queue.pop(0)
                user2_sid = waiting_queue.pop(0)

                # Check if both users still exist
                if user1_sid in active_users and user2_sid in active_users:
                    user1 = active_users[user1_sid]
                    user2 = active_users[user2_sid]

                    # Create room
                    room_id = str(uuid.uuid4())

                    # Join room
                    with app.test_request_context():
                        socketio.server.enter_room(user1_sid, room_id)
                        socketio.server.enter_room(user2_sid, room_id)

                    # Update user info
                    user1['room'] = room_id
                    user2['room'] = room_id

                    # Notify both users
                    socketio.emit('stranger_found', {
                        'room_id': room_id,
                        'partner': user2['username']
                    }, room=user1_sid)

                    socketio.emit('stranger_found', {
                        'room_id': room_id,
                        'partner': user1['username']
                    }, room=user2_sid)


# Start auto-matching thread
matching_thread = threading.Thread(target=auto_match_users, daemon=True)
matching_thread.start()


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    try:
        user_id = str(uuid.uuid4())
        username = generate_random_name()

        active_users[request.sid] = {
            'id': user_id,
            'username': username,
            'room': None
        }

        emit('user_connected', {
            'username': username,
            'user_id': user_id,
            'total_users': len(active_users)
        })

        # Auto-start looking for stranger
        with matching_lock:
            if request.sid not in waiting_queue:
                waiting_queue.append(request.sid)
                emit('waiting_for_stranger', {
                    'message': 'Looking for someone to chat with...'
                })

        # Broadcast user count
        socketio.emit('user_count_update', {'count': len(active_users)})

    except Exception as e:
        print(f"Connect error: {e}")


@socketio.on('disconnect')
def handle_disconnect():
    try:
        if request.sid in active_users:
            user = active_users[request.sid]

            # Remove from waiting queue
            with matching_lock:
                if request.sid in waiting_queue:
                    waiting_queue.remove(request.sid)

            # Leave room if in one
            if user['room']:
                socketio.emit('user_left', {
                    'username': user['username'],
                    'message': f"{user['username']} left the chat"
                }, room=user['room'])

            del active_users[request.sid]

            # Broadcast user count
            socketio.emit('user_count_update', {'count': len(active_users)})

    except Exception as e:
        print(f"Disconnect error: {e}")


@socketio.on('find_stranger')
def handle_find_stranger():
    try:
        current_user = active_users.get(request.sid)
        if not current_user:
            return

        # Leave current room
        if current_user['room']:
            socketio.emit('user_left', {
                'username': current_user['username'],
                'message': f"{current_user['username']} left the chat"
            }, room=current_user['room'])
            current_user['room'] = None

        # Add to waiting queue
        with matching_lock:
            if request.sid not in waiting_queue:
                waiting_queue.append(request.sid)
                emit('waiting_for_stranger', {
                    'message': 'Looking for someone to chat with...'
                })

    except Exception as e:
        print(f"Find stranger error: {e}")


@socketio.on('send_message')
def handle_message(data):
    try:
        user = active_users.get(request.sid)
        if not user or not user['room']:
            return

        message_data = {
            'username': user['username'],
            'message': data['message'],
            'timestamp': data.get('timestamp', ''),
            'user_id': user['id']
        }

        socketio.emit('receive_message', message_data, room=user['room'])

    except Exception as e:
        print(f"Message error: {e}")


@socketio.on('typing')
def handle_typing(data):
    try:
        user = active_users.get(request.sid)
        if not user or not user['room']:
            return

        socketio.emit('user_typing', {
            'username': user['username'],
            'typing': data['typing']
        }, room=user['room'], include_self=False)

    except Exception as e:
        print(f"Typing error: {e}")


@socketio.on('leave_chat')
def handle_leave_chat():
    try:
        user = active_users.get(request.sid)
        if not user or not user['room']:
            return

        room_id = user['room']

        socketio.emit('user_left', {
            'username': user['username'],
            'message': f"{user['username']} left the chat"
        }, room=room_id)

        user['room'] = None

        # Auto-join waiting queue again
        with matching_lock:
            if request.sid not in waiting_queue:
                waiting_queue.append(request.sid)
                emit('waiting_for_stranger', {
                    'message': 'Looking for someone new to chat with...'
                })

    except Exception as e:
        print(f"Leave chat error: {e}")


if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)