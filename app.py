from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Store active users (no chat history saved)
active_users = {}
waiting_queue = []


def generate_random_name():
    """Generate a random username for anonymous users"""
    adjectives = ['Cool', 'Fast', 'Smart', 'Funny', 'Wild', 'Brave', 'Quick', 'Sharp', 'Bright', 'Swift']
    nouns = ['Tiger', 'Eagle', 'Wolf', 'Fox', 'Bear', 'Lion', 'Shark', 'Falcon', 'Panther', 'Hawk']
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(10, 99)}"


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
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

    # Broadcast updated user count
    socketio.emit('user_count_update', {'count': len(active_users)})


@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_users:
        user = active_users[request.sid]

        # Remove from waiting queue if present
        if request.sid in waiting_queue:
            waiting_queue.remove(request.sid)

        # Leave room if in one
        if user['room']:
            leave_room(user['room'])
            socketio.to(user['room']).emit('user_left', {
                'username': user['username'],
                'message': f"{user['username']} left the chat"
            })

        del active_users[request.sid]

        # Broadcast updated user count
        socketio.emit('user_count_update', {'count': len(active_users)})


@socketio.on('find_stranger')
def handle_find_stranger():
    current_user = active_users.get(request.sid)
    if not current_user:
        return

    # If already in a room, leave it first
    if current_user['room']:
        leave_room(current_user['room'])
        socketio.to(current_user['room']).emit('user_left', {
            'username': current_user['username'],
            'message': f"{current_user['username']} left the chat"
        })
        current_user['room'] = None

    # Check if someone is waiting
    if waiting_queue and waiting_queue[0] != request.sid:
        # Match with the first person in queue
        partner_sid = waiting_queue.pop(0)

        if partner_sid in active_users:
            partner = active_users[partner_sid]

            # Create a room for both users
            room_id = str(uuid.uuid4())

            # Add both users to the room
            join_room(room_id)
            socketio.server.enter_room(partner_sid, room_id)

            # Update their room info
            current_user['room'] = room_id
            partner['room'] = room_id

            # Notify both users they're connected
            emit('stranger_found', {
                'room_id': room_id,
                'message': f"You're now chatting with {partner['username']}!"
            })

            socketio.to(partner_sid).emit('stranger_found', {
                'room_id': room_id,
                'message': f"You're now chatting with {current_user['username']}!"
            })
    else:
        # Add to waiting queue
        if request.sid not in waiting_queue:
            waiting_queue.append(request.sid)

        emit('waiting_for_stranger', {
            'message': 'Looking for a stranger to chat with...'
        })


@socketio.on('send_message')
def handle_message(data):
    user = active_users.get(request.sid)
    if not user or not user['room']:
        return

    message_data = {
        'username': user['username'],
        'message': data['message'],
        'timestamp': data.get('timestamp', ''),
        'user_id': user['id']
    }

    # Send to everyone in the room
    socketio.to(user['room']).emit('receive_message', message_data)


@socketio.on('typing')
def handle_typing(data):
    user = active_users.get(request.sid)
    if not user or not user['room']:
        return

    # Send typing indicator to others in room (not to self)
    socketio.to(user['room']).emit('user_typing', {
        'username': user['username'],
        'typing': data['typing']
    }, include_self=False)


@socketio.on('leave_chat')
def handle_leave_chat():
    user = active_users.get(request.sid)
    if not user or not user['room']:
        return

    room_id = user['room']
    leave_room(room_id)

    # Notify others in room
    socketio.to(room_id).emit('user_left', {
        'username': user['username'],
        'message': f"{user['username']} left the chat"
    })

    user['room'] = None

    emit('chat_left', {
        'message': 'You left the chat'
    })


if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)