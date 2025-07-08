from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import time
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Optimized SocketIO configuration for Vercel
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    transports=['polling'],  # Only polling for Vercel
    ping_timeout=30,
    ping_interval=10
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
    # Serve the HTML directly embedded in the Python file
    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat Room</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .login-container {
            background: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            backdrop-filter: blur(10px);
            width: 400px;
        }

        .chat-container {
            display: none;
            background: rgba(255, 255, 255, 0.95);
            width: 100vw;
            height: 100vh;
            backdrop-filter: blur(10px);
        }

        .header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .status-info {
            display: flex;
            gap: 20px;
            font-size: 14px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .online-dot {
            width: 8px;
            height: 8px;
            background: #4CAF50;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .main-content {
            display: flex;
            height: calc(100vh - 70px);
        }

        .sidebar {
            width: 250px;
            background: rgba(255, 255, 255, 0.8);
            border-right: 1px solid rgba(0,0,0,0.1);
            padding: 20px;
            overflow-y: auto;
        }

        .sidebar h3 {
            margin-bottom: 15px;
            color: #333;
        }

        .user-list {
            list-style: none;
        }

        .user-item {
            padding: 8px 12px;
            margin: 5px 0;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .user-item.current-user {
            background: rgba(76, 175, 80, 0.2);
            font-weight: bold;
        }

        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: rgba(255, 255, 255, 0.5);
        }

        .message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 15px;
            max-width: 70%;
            word-wrap: break-word;
            position: relative;
        }

        .message.own {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            margin-left: auto;
            border-bottom-right-radius: 5px;
        }

        .message.other {
            background: rgba(255, 255, 255, 0.9);
            color: #333;
            border-bottom-left-radius: 5px;
        }

        .message-header {
            font-size: 12px;
            opacity: 0.7;
            margin-bottom: 5px;
        }

        .input-area {
            padding: 20px;
            background: rgba(255, 255, 255, 0.9);
            display: flex;
            gap: 10px;
            border-top: 1px solid rgba(0,0,0,0.1);
        }

        .message-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid rgba(102, 126, 234, 0.3);
            border-radius: 25px;
            outline: none;
            font-size: 14px;
            transition: all 0.3s ease;
        }

        .message-input:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .send-btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s ease;
        }

        .send-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
        }

        .username-input {
            width: 100%;
            padding: 15px;
            border: 2px solid rgba(102, 126, 234, 0.3);
            border-radius: 15px;
            font-size: 16px;
            margin-bottom: 20px;
            outline: none;
            transition: all 0.3s ease;
        }

        .username-input:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .join-btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 15px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s ease;
            width: 100%;
        }

        .join-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }

        .typing-indicator {
            padding: 10px 20px;
            font-style: italic;
            color: #667eea;
            font-size: 14px;
        }

        @media (max-width: 768px) {
            .main-content { flex-direction: column; }
            .sidebar { width: 100%; height: 200px; }
            .message { max-width: 90%; }
        }
    </style>
</head>
<body>
    <div class="login-container" id="loginContainer">
        <h2 style="margin-bottom: 30px; color: #333;">Join Chat Room</h2>
        <input type="text" id="usernameInput" class="username-input" placeholder="Enter your username..." maxlength="20">
        <button class="join-btn" onclick="joinChat()">Join Chat</button>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="header">
            <div class="logo">💬 Chat Room</div>
            <div class="status-info">
                <div class="status-item">
                    <div class="online-dot"></div>
                    <span>Online</span>
                </div>
                <div class="status-item">
                    <span id="latency">0ms</span>
                </div>
                <div class="status-item">
                    <span id="userCount">0</span> users
                </div>
            </div>
        </div>

        <div class="main-content">
            <div class="sidebar">
                <h3>Online Users</h3>
                <ul class="user-list" id="userList"></ul>
            </div>

            <div class="chat-area">
                <div class="messages" id="messages"></div>
                <div class="typing-indicator" id="typingIndicator" style="display: none;"></div>
                <div class="input-area">
                    <input type="text" class="message-input" id="messageInput" placeholder="Type a message..." maxlength="500">
                    <button class="send-btn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let socket;
        let username = '';
        let lastPing = Date.now();
        let typingTimeout;

        function joinChat() {
            const input = document.getElementById('usernameInput');
            username = input.value.trim();

            if (!username) {
                alert('Please enter a username');
                return;
            }

            document.getElementById('loginContainer').style.display = 'none';
            document.getElementById('chatContainer').style.display = 'block';

            // Initialize socket connection - optimized for Vercel
            socket = io({
                transports: ['polling'],
                upgrade: false,
                rememberUpgrade: false
            });

            setupSocketHandlers();
            startLatencyMonitor();
        }

        function setupSocketHandlers() {
            socket.on('connect', () => {
                socket.emit('join', { username });
            });

            socket.on('user_list', (users) => {
                updateUserList(users);
                document.getElementById('userCount').textContent = users.length;
            });

            socket.on('message', (data) => {
                addMessage(data.username, data.message, data.username === username);
            });

            socket.on('user_typing', (data) => {
                if (data.username !== username) {
                    showTyping(data.username, data.typing);
                }
            });

            socket.on('pong', () => {
                const latency = Date.now() - lastPing;
                document.getElementById('latency').textContent = latency + 'ms';
            });
        }

        function updateUserList(users) {
            const userList = document.getElementById('userList');
            userList.innerHTML = '';

            users.forEach(user => {
                const li = document.createElement('li');
                li.className = 'user-item';
                if (user === username) {
                    li.classList.add('current-user');
                }
                li.innerHTML = `
                    <div class="online-dot"></div>
                    <span>${user}</span>
                `;
                userList.appendChild(li);
            });
        }

        function addMessage(user, message, isOwn) {
            const messages = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = `message ${isOwn ? 'own' : 'other'}`;

            div.innerHTML = `
                <div class="message-header">${isOwn ? 'You' : user}</div>
                <div>${message}</div>
            `;

            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();

            if (message && socket) {
                socket.emit('message', { message });
                input.value = '';
                stopTyping();
            }
        }

        function showTyping(user, isTyping) {
            const indicator = document.getElementById('typingIndicator');
            if (isTyping) {
                indicator.textContent = `${user} is typing...`;
                indicator.style.display = 'block';
            } else {
                indicator.style.display = 'none';
            }
        }

        function startTyping() {
            if (socket) {
                socket.emit('typing', { typing: true });
                clearTimeout(typingTimeout);
                typingTimeout = setTimeout(stopTyping, 3000);
            }
        }

        function stopTyping() {
            if (socket) {
                socket.emit('typing', { typing: false });
                clearTimeout(typingTimeout);
            }
        }

        function startLatencyMonitor() {
            setInterval(() => {
                lastPing = Date.now();
                socket.emit('ping');
            }, 2000);
        }

        // Event listeners
        document.getElementById('usernameInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') joinChat();
        });

        document.getElementById('messageInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage();
            } else {
                startTyping();
            }
        });

        document.getElementById('messageInput').addEventListener('input', () => {
            if (document.getElementById('messageInput').value.length > 0) {
                startTyping();
            } else {
                stopTyping();
            }
        });
    </script>
</body>
</html>''')


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