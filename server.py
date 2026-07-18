import socket
import threading
import json
import os
import struct

# Server configuration
HOST = '0.0.0.0'
PORT = 5555
UDP_PORT = 5556  # UDP port for voice data

# Dictionary to keep track of all connected clients: {username: {'socket': socket, 'room': room_name, 'udp_addr': (ip, port)}}
clients = {}
clients_lock = threading.Lock()

# Dictionary to track active calls: {caller: callee}
active_calls = {}
calls_lock = threading.Lock()

# Default room for new users (public room anyone can join)
DEFAULT_ROOM = "lobby"

# Room management: {room_name: {'owner': username, 'members': [usernames], 'pending_requests': [usernames]}}
rooms = {
    DEFAULT_ROOM: {'owner': None, 'members': [], 'pending_requests': []}  # Lobby is public
}
rooms_lock = threading.Lock()

# UDP socket for voice data
udp_socket = None


def send_json(client_socket, message_dict):
    """Send JSON message to a client"""
    try:
        message = json.dumps(message_dict) + "\n"
        client_socket.send(message.encode('utf-8'))
    except:
        pass


def broadcast(message_dict, sender_username=None, room=None):
    """Send JSON message to clients in a specific room or all clients"""
    with clients_lock:
        for username, user_info in list(clients.items()):
            # Skip sender
            if username == sender_username:
                continue
            
            # If room is specified, only send to users in that room
            if room is not None:
                if user_info['room'] == room:
                    send_json(user_info['socket'], message_dict)
            else:
                # Send to all users (for global notifications)
                send_json(user_info['socket'], message_dict)


def broadcast_active_users():
    """Send the list of active users to all connected clients"""
    with clients_lock:
        user_list = list(clients.keys())
    
    user_list_message = {
        "type": "user_list",
        "payload": user_list
    }
    
    with clients_lock:
        for user_info in clients.values():
            send_json(user_info['socket'], user_list_message)


def send_room_info(client_socket, username):
    """Send current room info and room members to a specific client"""
    with clients_lock:
        if username not in clients:
            return
        
        user_room = clients[username]['room']
        room_members = [uname for uname, info in clients.items() if info['room'] == user_room]
    
    room_info_msg = {
        "type": "room_info",
        "payload": {
            "room": user_room,
            "members": room_members
        }
    }
    send_json(client_socket, room_info_msg)


def send_private_message(sender, target, message):
    """Send a private message from sender to target"""
    with clients_lock:
        if target in clients:
            private_msg = {
                "type": "private_message",
                "sender": sender,
                "payload": message
            }
            send_json(clients[target]['socket'], private_msg)
            return True
        return False


def change_user_room(username, new_room):
    """Change a user's room"""
    with clients_lock:
        if username in clients:
            old_room = clients[username]['room']
            clients[username]['room'] = new_room
            return old_room
        return None


def get_room_users(room):
    """Get list of users in a specific room"""
    with clients_lock:
        return [username for username, info in clients.items() if info['room'] == room]


def create_room(room_name, owner):
    """Create a new room with an owner"""
    with rooms_lock:
        if room_name in rooms:
            return False, "Room already exists"
        rooms[room_name] = {
            'owner': owner,
            'members': [owner],
            'pending_requests': []
        }
        return True, "Room created successfully"


def is_room_owner(username, room_name):
    """Check if user is the owner of a room"""
    with rooms_lock:
        if room_name in rooms and rooms[room_name]['owner'] == username:
            return True
        return False


def is_user_in_room(username, room_name):
    """Check if user is a member of a room"""
    with rooms_lock:
        if room_name == DEFAULT_ROOM:
            return True  # Lobby is always accessible
        if room_name in rooms and username in rooms[room_name]['members']:
            return True
        return False


def add_user_to_room(username, room_name):
    """Add a user to a room's member list"""
    with rooms_lock:
        if room_name in rooms:
            if username not in rooms[room_name]['members']:
                rooms[room_name]['members'].append(username)
            # Remove from pending requests if present
            if username in rooms[room_name]['pending_requests']:
                rooms[room_name]['pending_requests'].remove(username)
            return True
        return False


def remove_user_from_room(username, room_name):
    """Remove a user from a room's member list"""
    with rooms_lock:
        if room_name in rooms and username in rooms[room_name]['members']:
            rooms[room_name]['members'].remove(username)
            return True
        return False


def add_join_request(username, room_name):
    """Add a join request for a room"""
    with rooms_lock:
        if room_name not in rooms:
            return False, "Room does not exist"
        if room_name == DEFAULT_ROOM:
            return False, "Lobby is open to everyone"
        if username in rooms[room_name]['members']:
            return False, "You are already a member"
        if username in rooms[room_name]['pending_requests']:
            return False, "Request already pending"
        rooms[room_name]['pending_requests'].append(username)
        return True, "Join request sent"


def get_pending_requests(room_name):
    """Get list of pending join requests for a room"""
    with rooms_lock:
        if room_name in rooms:
            return rooms[room_name]['pending_requests'].copy()
        return []


def approve_join_request(username, room_name):
    """Approve a user's join request"""
    with rooms_lock:
        if room_name in rooms and username in rooms[room_name]['pending_requests']:
            rooms[room_name]['pending_requests'].remove(username)
            if username not in rooms[room_name]['members']:
                rooms[room_name]['members'].append(username)
            return True
        return False


def reject_join_request(username, room_name):
    """Reject a user's join request"""
    with rooms_lock:
        if room_name in rooms and username in rooms[room_name]['pending_requests']:
            rooms[room_name]['pending_requests'].remove(username)
            return True
        return False


def send_file_to_user(target_socket, sender, filename, filedata, target_user=None):
    """Send file to a specific user with header-body protocol"""
    try:
        # Send file header as JSON
        file_header = {
            "type": "file_incoming",
            "sender": sender,
            "filename": filename,
            "filesize": len(filedata),
            "target": target_user
        }
        header_json = json.dumps(file_header) + "\n"
        target_socket.send(header_json.encode('utf-8'))
        
        # Send file size as 4-byte integer (for binary mode verification)
        target_socket.send(struct.pack('>I', len(filedata)))
        
        # Send raw binary file data in chunks
        chunk_size = 4096
        for i in range(0, len(filedata), chunk_size):
            chunk = filedata[i:i + chunk_size]
            target_socket.send(chunk)
        
        print(f"[FILE SENT] {filename} ({len(filedata)} bytes) to {target_user or 'room'}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send file: {e}")
        return False


def broadcast_file(filedata, filename, sender, room):
    """Broadcast file to all users in a room except sender"""
    with clients_lock:
        for username, user_info in list(clients.items()):
            if username != sender and user_info['room'] == room:
                send_file_to_user(user_info['socket'], sender, filename, filedata, username)


def handle_udp_voice():
    """Handle UDP voice packets and forward them"""
    global udp_socket
    print(f"[UDP] Voice server listening on {HOST}:{UDP_PORT}")
    
    while True:
        try:
            # Receive voice data (username prefix + audio data)
            data, addr = udp_socket.recvfrom(8192)
            
            if len(data) < 2:
                continue
            
            # First 2 bytes: username length
            username_len = struct.unpack('>H', data[:2])[0]
            
            if len(data) < 2 + username_len:
                continue
            
            # Extract username
            username = data[2:2+username_len].decode('utf-8')
            
            # Update client's UDP address
            with clients_lock:
                if username in clients:
                    clients[username]['udp_addr'] = addr
            
            # Get call partner
            with calls_lock:
                target = active_calls.get(username)
            
            if target:
                # Forward audio to call partner
                with clients_lock:
                    if target in clients and 'udp_addr' in clients[target]:
                        target_addr = clients[target]['udp_addr']
                        # Send only the audio data (skip username header)
                        audio_data = data[2+username_len:]
                        udp_socket.sendto(audio_data, target_addr)
        
        except Exception as e:
            print(f"[UDP ERROR] {e}")
            continue


def handle_client(client_socket, client_address):
    """Handle individual client connection"""
    global active_calls, calls_lock
    print(f"[NEW CONNECTION] {client_address} connected.")
    username = None
    
    try:
        # Wait for login message with username
        client_socket.settimeout(30)  # 30 second timeout for login
        data = client_socket.recv(1024).decode('utf-8')
        
        if not data:
            client_socket.close()
            return
        
        # Parse login message
        try:
            message = json.loads(data.strip())
            if message.get("type") == "login":
                username = message.get("payload", "").strip()
                
                if not username:
                    error_msg = {"type": "error", "payload": "Username cannot be empty"}
                    send_json(client_socket, error_msg)
                    client_socket.close()
                    return
                
                # Check if username already exists
                with clients_lock:
                    if username in clients:
                        error_msg = {"type": "error", "payload": "Username already taken"}
                        send_json(client_socket, error_msg)
                        client_socket.close()
                        return
                    
                    # Add client to dictionary with default room
                    clients[username] = {
                        'socket': client_socket,
                        'room': DEFAULT_ROOM
                    }
                
                # Add user to lobby (public room)
                with rooms_lock:
                    if username not in rooms[DEFAULT_ROOM]['members']:
                        rooms[DEFAULT_ROOM]['members'].append(username)
                
                print(f"[LOGIN] {username} ({client_address}) logged in.")
                
                # Send success message
                success_msg = {"type": "login_success", "payload": f"Welcome, {username}!"}
                send_json(client_socket, success_msg)
                
                # Send initial room info to the new user
                send_room_info(client_socket, username)
                
                # Notify all clients in the same room about new user
                join_msg = {"type": "notification", "payload": f"{username} joined the chat!"}
                broadcast(join_msg, username, DEFAULT_ROOM)
                
                # Broadcast updated active users list
                broadcast_active_users()
                
            else:
                client_socket.close()
                return
        except json.JSONDecodeError:
            client_socket.close()
            return
        
        # Remove timeout for regular messaging
        client_socket.settimeout(None)
        
        # Handle messages from client
        buffer = ""
        while True:
            data = client_socket.recv(1024).decode('utf-8')
            
            if not data:
                break
            
            buffer += data
            
            # Process complete JSON messages (separated by newlines)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    msg_type = message.get("type")
                    payload = message.get("payload")
                    
                    if msg_type == "message" and payload:
                        # Get user's current room
                        with clients_lock:
                            user_room = clients[username]['room']
                        
                        print(f"[{username}@{user_room}] {payload}")
                        
                        # Broadcast chat message to users in the same room
                        chat_msg = {
                            "type": "message",
                            "sender": username,
                            "room": user_room,
                            "payload": payload
                        }
                        broadcast(chat_msg, username, user_room)
                    
                    elif msg_type == "private_message":
                        target = message.get("target")
                        msg = message.get("payload")
                        
                        if target and msg:
                            print(f"[PRIVATE] {username} -> {target}: {msg}")
                            
                            if send_private_message(username, target, msg):
                                # Send confirmation to sender
                                confirm_msg = {
                                    "type": "private_sent",
                                    "target": target,
                                    "payload": msg
                                }
                                send_json(client_socket, confirm_msg)
                            else:
                                # User not found
                                error_msg = {
                                    "type": "error",
                                    "payload": f"User '{target}' not found or offline"
                                }
                                send_json(client_socket, error_msg)
                    
                    elif msg_type == "create_room":
                        room_name = payload.strip() if payload else None
                        
                        if not room_name:
                            error_msg = {"type": "error", "payload": "Room name cannot be empty"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        success, message = create_room(room_name, username)
                        
                        if success:
                            print(f"[ROOM] {username} created room '{room_name}'")
                            
                            # Move user to the new room
                            old_room = change_user_room(username, room_name)
                            
                            # Notify old room
                            if old_room:
                                leave_notif = {
                                    "type": "notification",
                                    "payload": f"{username} left the room"
                                }
                                broadcast(leave_notif, username, old_room)
                            
                            # Send success message
                            success_msg = {
                                "type": "notification",
                                "payload": f"Room '{room_name}' created successfully! You are the owner."
                            }
                            send_json(client_socket, success_msg)
                            
                            # Send room info
                            send_room_info(client_socket, username)
                            broadcast_active_users()
                        else:
                            error_msg = {"type": "error", "payload": message}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "join_room":
                        new_room = payload.strip() if payload else DEFAULT_ROOM
                        
                        if not new_room:
                            error_msg = {"type": "error", "payload": "Room name cannot be empty"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        # Check if room exists
                        with rooms_lock:
                            room_exists = new_room in rooms
                        
                        if not room_exists:
                            error_msg = {"type": "error", "payload": f"Room '{new_room}' does not exist. Use /createroom to create it."}
                            send_json(client_socket, error_msg)
                            continue
                        
                        # Check if user has permission to join
                        if not is_user_in_room(username, new_room):
                            error_msg = {
                                "type": "error",
                                "payload": f"Access denied. Use /requestjoin {new_room} to request access."
                            }
                            send_json(client_socket, error_msg)
                            continue
                        
                        old_room = change_user_room(username, new_room)
                        
                        if old_room:
                            print(f"[ROOM] {username} moved from '{old_room}' to '{new_room}'")
                            
                            # Remove from old room members if not lobby
                            if old_room != DEFAULT_ROOM:
                                remove_user_from_room(username, old_room)
                            
                            # Notify old room that user left
                            if old_room != new_room:
                                leave_notif = {
                                    "type": "notification",
                                    "payload": f"{username} left the room"
                                }
                                broadcast(leave_notif, username, old_room)
                            
                            # Notify new room that user joined
                            join_notif = {
                                "type": "notification",
                                "payload": f"{username} joined the room"
                            }
                            broadcast(join_notif, username, new_room)
                            
                            # Send room info to the user who joined
                            send_room_info(client_socket, username)
                            
                            # Broadcast updated user list to everyone
                            broadcast_active_users()
                    
                    elif msg_type == "request_join":
                        room_name = payload.strip() if payload else None
                        
                        if not room_name:
                            error_msg = {"type": "error", "payload": "Room name cannot be empty"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        success, message = add_join_request(username, room_name)
                        
                        if success:
                            print(f"[ROOM] {username} requested to join '{room_name}'")
                            
                            # Notify room owner
                            with rooms_lock:
                                if room_name in rooms:
                                    owner = rooms[room_name]['owner']
                            
                            if owner:
                                with clients_lock:
                                    if owner in clients:
                                        notif = {
                                            "type": "join_request",
                                            "payload": {
                                                "user": username,
                                                "room": room_name
                                            }
                                        }
                                        send_json(clients[owner]['socket'], notif)
                            
                            success_msg = {"type": "notification", "payload": message}
                            send_json(client_socket, success_msg)
                        else:
                            error_msg = {"type": "error", "payload": message}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "approve_user":
                        data = payload
                        target_user = data.get("user") if isinstance(data, dict) else None
                        room_name = data.get("room") if isinstance(data, dict) else None
                        
                        if not target_user or not room_name:
                            error_msg = {"type": "error", "payload": "Invalid approve request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if not is_room_owner(username, room_name):
                            error_msg = {"type": "error", "payload": "Only room owner can approve users"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if approve_join_request(target_user, room_name):
                            print(f"[ROOM] {username} approved {target_user} for '{room_name}'")
                            
                            # Notify the approved user
                            with clients_lock:
                                if target_user in clients:
                                    notif = {
                                        "type": "notification",
                                        "payload": f"Your request to join '{room_name}' was approved! Use /join {room_name}"
                                    }
                                    send_json(clients[target_user]['socket'], notif)
                            
                            success_msg = {"type": "notification", "payload": f"Approved {target_user}"}
                            send_json(client_socket, success_msg)
                        else:
                            error_msg = {"type": "error", "payload": "Failed to approve user"}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "reject_user":
                        data = payload
                        target_user = data.get("user") if isinstance(data, dict) else None
                        room_name = data.get("room") if isinstance(data, dict) else None
                        
                        if not target_user or not room_name:
                            error_msg = {"type": "error", "payload": "Invalid reject request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if not is_room_owner(username, room_name):
                            error_msg = {"type": "error", "payload": "Only room owner can reject users"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if reject_join_request(target_user, room_name):
                            print(f"[ROOM] {username} rejected {target_user} for '{room_name}'")
                            
                            # Notify the rejected user
                            with clients_lock:
                                if target_user in clients:
                                    notif = {
                                        "type": "notification",
                                        "payload": f"Your request to join '{room_name}' was rejected"
                                    }
                                    send_json(clients[target_user]['socket'], notif)
                            
                            success_msg = {"type": "notification", "payload": f"Rejected {target_user}"}
                            send_json(client_socket, success_msg)
                        else:
                            error_msg = {"type": "error", "payload": "Failed to reject user"}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "add_user":
                        data = payload
                        target_user = data.get("user") if isinstance(data, dict) else None
                        room_name = data.get("room") if isinstance(data, dict) else None
                        
                        if not target_user or not room_name:
                            error_msg = {"type": "error", "payload": "Invalid add user request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if not is_room_owner(username, room_name):
                            error_msg = {"type": "error", "payload": "Only room owner can add users"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        # Check if target user exists
                        with clients_lock:
                            user_exists = target_user in clients
                        
                        if not user_exists:
                            error_msg = {"type": "error", "payload": f"User '{target_user}' not found"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if add_user_to_room(target_user, room_name):
                            print(f"[ROOM] {username} added {target_user} to '{room_name}'")
                            
                            # Notify the added user
                            with clients_lock:
                                if target_user in clients:
                                    notif = {
                                        "type": "notification",
                                        "payload": f"You've been added to room '{room_name}' by {username}. Use /join {room_name}"
                                    }
                                    send_json(clients[target_user]['socket'], notif)
                            
                            success_msg = {"type": "notification", "payload": f"Added {target_user} to the room"}
                            send_json(client_socket, success_msg)
                        else:
                            error_msg = {"type": "error", "payload": "Failed to add user"}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "kick_user":
                        data = payload
                        target_user = data.get("user") if isinstance(data, dict) else None
                        room_name = data.get("room") if isinstance(data, dict) else None
                        
                        if not target_user or not room_name:
                            error_msg = {"type": "error", "payload": "Invalid kick request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if not is_room_owner(username, room_name):
                            error_msg = {"type": "error", "payload": "Only room owner can kick users"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if target_user == username:
                            error_msg = {"type": "error", "payload": "Cannot kick yourself"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        if remove_user_from_room(target_user, room_name):
                            print(f"[ROOM] {username} kicked {target_user} from '{room_name}'")
                            
                            # If user is currently in the room, move them to lobby
                            with clients_lock:
                                if target_user in clients and clients[target_user]['room'] == room_name:
                                    clients[target_user]['room'] = DEFAULT_ROOM
                                    
                                    # Notify kicked user
                                    notif = {
                                        "type": "notification",
                                        "payload": f"You've been kicked from '{room_name}' by {username}"
                                    }
                                    send_json(clients[target_user]['socket'], notif)
                                    
                                    # Send them room info for lobby
                                    send_room_info(clients[target_user]['socket'], target_user)
                            
                            # Notify room
                            kick_notif = {
                                "type": "notification",
                                "payload": f"{target_user} was kicked from the room"
                            }
                            broadcast(kick_notif, username, room_name)
                            
                            success_msg = {"type": "notification", "payload": f"Kicked {target_user}"}
                            send_json(client_socket, success_msg)
                            
                            broadcast_active_users()
                        else:
                            error_msg = {"type": "error", "payload": "User not in room"}
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "room_details":
                        room_name = payload.strip() if payload else None
                        
                        if not room_name:
                            # Show current room details
                            with clients_lock:
                                room_name = clients[username]['room']
                        
                        with rooms_lock:
                            if room_name not in rooms:
                                error_msg = {"type": "error", "payload": f"Room '{room_name}' does not exist"}
                                send_json(client_socket, error_msg)
                                continue
                            
                            room_data = rooms[room_name]
                            owner = room_data['owner'] or "None (Public)"
                            members = room_data['members']
                            pending = room_data['pending_requests']
                        
                        # Get current users in room
                        current_users = get_room_users(room_name)
                        
                        details = {
                            "type": "room_details",
                            "payload": {
                                "room": room_name,
                                "owner": owner,
                                "members": members,
                                "current_users": current_users,
                                "pending_requests": pending if is_room_owner(username, room_name) else []
                            }
                        }
                        send_json(client_socket, details)
                    
                    elif msg_type == "list_rooms":
                        # Get all unique rooms
                        with clients_lock:
                            room_list = {}
                            for uname, info in clients.items():
                                room = info['room']
                                if room not in room_list:
                                    room_list[room] = []
                                room_list[room].append(uname)
                        
                        room_list_msg = {
                            "type": "room_list",
                            "payload": room_list
                        }
                        send_json(client_socket, room_list_msg)
                    
                    elif msg_type == "call_request":
                        # Handle voice call request
                        target = payload
                        
                        if not target:
                            error_msg = {"type": "error", "payload": "Invalid call request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        with clients_lock:
                            if target not in clients:
                                error_msg = {"type": "error", "payload": f"User '{target}' not found"}
                                send_json(client_socket, error_msg)
                                continue
                            
                            target_socket = clients[target]['socket']
                        
                        # Check if either user is already in a call
                        with calls_lock:
                            if username in active_calls or target in active_calls:
                                error_msg = {"type": "error", "payload": "User is already in a call"}
                                send_json(client_socket, error_msg)
                                continue
                        
                        print(f"[CALL] {username} calling {target}")
                        
                        # Send call request to target
                        call_notif = {
                            "type": "call_incoming",
                            "payload": username
                        }
                        send_json(target_socket, call_notif)
                        
                        # Send confirmation to caller
                        call_confirm = {
                            "type": "call_ringing",
                            "payload": f"Calling {target}..."
                        }
                        send_json(client_socket, call_confirm)
                    
                    elif msg_type == "call_accept":
                        # Handle call acceptance
                        caller = payload
                        
                        with clients_lock:
                            if caller not in clients:
                                error_msg = {"type": "error", "payload": "Caller not found"}
                                send_json(client_socket, error_msg)
                                continue
                            
                            caller_socket = clients[caller]['socket']
                        
                        # Establish call
                        with calls_lock:
                            active_calls[username] = caller
                            active_calls[caller] = username
                        
                        print(f"[CALL] {username} accepted call from {caller}")
                        
                        # Notify both users
                        call_started = {
                            "type": "call_started",
                            "payload": username
                        }
                        send_json(caller_socket, call_started)
                        
                        call_started_self = {
                            "type": "call_started",
                            "payload": caller
                        }
                        send_json(client_socket, call_started_self)
                    
                    elif msg_type == "call_reject":
                        # Handle call rejection
                        caller = payload
                        
                        with clients_lock:
                            if caller in clients:
                                caller_socket = clients[caller]['socket']
                                call_rejected = {
                                    "type": "call_rejected",
                                    "payload": f"{username} declined the call"
                                }
                                send_json(caller_socket, call_rejected)
                        
                        print(f"[CALL] {username} rejected call from {caller}")
                    
                    elif msg_type == "call_end":
                        # Handle call termination
                        with calls_lock:
                            partner = active_calls.get(username)
                            if partner:
                                del active_calls[username]
                                if username in active_calls.values():
                                    # Remove reverse mapping
                                    active_calls = {k: v for k, v in active_calls.items() if v != username}
                        
                        if partner:
                            with clients_lock:
                                if partner in clients:
                                    partner_socket = clients[partner]['socket']
                                    call_ended = {
                                        "type": "call_ended",
                                        "payload": f"{username} ended the call"
                                    }
                                    send_json(partner_socket, call_ended)
                            
                            print(f"[CALL] Call ended between {username} and {partner}")
                        
                        # Confirm to sender
                        call_ended_self = {
                            "type": "call_ended",
                            "payload": "Call ended"
                        }
                        send_json(client_socket, call_ended_self)
                    
                    elif msg_type == "file_transfer":
                        # Handle file transfer with header-body protocol
                        filename = message.get("filename")
                        filesize = message.get("filesize")
                        target = message.get("target")  # None for room, username for private
                        
                        if not filename or not filesize:
                            error_msg = {"type": "error", "payload": "Invalid file transfer request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        print(f"[FILE TRANSFER] {username} sending {filename} ({filesize} bytes)")
                        
                        # Send acknowledgment to start binary transfer
                        ack_msg = {"type": "file_transfer_ready", "payload": "Ready to receive"}
                        send_json(client_socket, ack_msg)
                        
                        # Read binary file size header (4 bytes)
                        size_data = client_socket.recv(4)
                        if len(size_data) != 4:
                            print(f"[ERROR] Invalid file size header from {username}")
                            continue
                        
                        expected_size = struct.unpack('>I', size_data)[0]
                        
                        if expected_size != filesize:
                            print(f"[ERROR] File size mismatch from {username}")
                            continue
                        
                        # Receive raw binary data in chunks
                        filedata = b''
                        remaining = filesize
                        
                        while remaining > 0:
                            chunk_size = min(4096, remaining)
                            chunk = client_socket.recv(chunk_size)
                            
                            if not chunk:
                                print(f"[ERROR] Connection lost during file transfer from {username}")
                                break
                            
                            filedata += chunk
                            remaining -= len(chunk)
                        
                        if len(filedata) == filesize:
                            print(f"[FILE RECEIVED] {filename} ({len(filedata)} bytes) from {username}")
                            
                            # Send confirmation to sender
                            confirm_msg = {
                                "type": "file_sent_confirm",
                                "payload": f"File '{filename}' sent successfully"
                            }
                            send_json(client_socket, confirm_msg)
                            
                            # Forward file to target or room
                            if target:
                                # Private file transfer
                                with clients_lock:
                                    if target in clients:
                                        send_file_to_user(
                                            clients[target]['socket'],
                                            username,
                                            filename,
                                            filedata,
                                            target
                                        )
                                    else:
                                        error_msg = {
                                            "type": "error",
                                            "payload": f"User '{target}' not found"
                                        }
                                        send_json(client_socket, error_msg)
                            else:
                                # Broadcast to room
                                with clients_lock:
                                    user_room = clients[username]['room']
                                broadcast_file(filedata, filename, username, user_room)
                        else:
                            print(f"[ERROR] File transfer incomplete from {username}")
                            error_msg = {
                                "type": "error",
                                "payload": "File transfer failed - incomplete data"
                            }
                            send_json(client_socket, error_msg)
                    
                    elif msg_type == "file_broadcast":
                        # Handle broadcast file to ALL users
                        filename = message.get("filename")
                        filesize = message.get("filesize")
                        
                        if not filename or not filesize:
                            error_msg = {"type": "error", "payload": "Invalid file broadcast request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        print(f"[FILE BROADCAST] {username} broadcasting {filename} ({filesize} bytes) to ALL users")
                        
                        # Send acknowledgment to start binary transfer
                        ack_msg = {"type": "file_transfer_ready", "payload": "Ready to receive"}
                        send_json(client_socket, ack_msg)
                        
                        # Read binary file size header (4 bytes)
                        size_data = client_socket.recv(4)
                        if len(size_data) != 4:
                            print(f"[ERROR] Invalid file size header from {username}")
                            continue
                        
                        expected_size = struct.unpack('>I', size_data)[0]
                        
                        if expected_size != filesize:
                            print(f"[ERROR] File size mismatch from {username}")
                            continue
                        
                        # Receive raw binary data in chunks
                        filedata = b''
                        remaining = filesize
                        
                        while remaining > 0:
                            chunk_size = min(4096, remaining)
                            chunk = client_socket.recv(chunk_size)
                            
                            if not chunk:
                                print(f"[ERROR] Connection lost during file broadcast from {username}")
                                break
                            
                            filedata += chunk
                            remaining -= len(chunk)
                        
                        if len(filedata) == filesize:
                            print(f"[FILE RECEIVED] {filename} ({len(filedata)} bytes) from {username} - Broadcasting to all users")
                            
                            # Send confirmation to sender
                            confirm_msg = {
                                "type": "file_sent_confirm",
                                "payload": f"File '{filename}' broadcast to all users successfully"
                            }
                            send_json(client_socket, confirm_msg)
                            
                            # Broadcast to ALL users except sender
                            with clients_lock:
                                for uname, user_info in list(clients.items()):
                                    if uname != username:
                                        send_file_to_user(
                                            user_info['socket'],
                                            username,
                                            filename,
                                            filedata,
                                            uname
                                        )
                        else:
                            print(f"[ERROR] File broadcast incomplete from {username}")
                            error_msg = {
                                "type": "error",
                                "payload": "File broadcast failed - incomplete data"
                            }
                            send_json(client_socket, error_msg)
                        
                except json.JSONDecodeError:
                    print(f"[ERROR] Invalid JSON from {username}")
                    continue
                
    except socket.timeout:
        print(f"[TIMEOUT] {client_address} did not login in time.")
    except Exception as e:
        print(f"[ERROR] {client_address}: {e}")
    
    finally:
        # Remove client from dictionary and close connection
        if username:
            # End any active call
            with calls_lock:
                partner = active_calls.get(username)
                if partner:
                    del active_calls[username]
                    if partner in active_calls:
                        del active_calls[partner]
                    
                    # Notify partner
                    with clients_lock:
                        if partner in clients:
                            partner_socket = clients[partner]['socket']
                            call_ended = {
                                "type": "call_ended",
                                "payload": f"{username} disconnected"
                            }
                            send_json(partner_socket, call_ended)
            
            # Remove from current room's member list
            with clients_lock:
                if username in clients:
                    user_room = clients[username]['room']
                    del clients[username]
            
            # Clean up room membership
            with rooms_lock:
                for room_name, room_data in rooms.items():
                    if username in room_data['members']:
                        room_data['members'].remove(username)
                    if username in room_data['pending_requests']:
                        room_data['pending_requests'].remove(username)
            
            print(f"[DISCONNECTED] {username} ({client_address}) left the chat.")
            
            # Notify other clients
            leave_msg = {"type": "notification", "payload": f"{username} left the chat!"}
            broadcast(leave_msg, username)
            
            # Broadcast updated active users list
            broadcast_active_users()
        
        try:
            client_socket.close()
        except:
            pass


def start_server():
    """Initialize and start the TCP server"""
    global udp_socket
    
    # Setup TCP server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    
    print(f"[LISTENING] TCP Server is listening on {HOST}:{PORT}")
    
    # Setup UDP server for voice
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST, UDP_PORT))
    
    # Start UDP handler thread
    udp_thread = threading.Thread(target=handle_udp_voice, daemon=True)
    udp_thread.start()
    
    try:
        while True:
            # Accept new connection
            client_socket, client_address = server.accept()
            
            # Create new thread for this client
            thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            thread.daemon = True
            thread.start()
            
            print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
    
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down...")
    finally:
        server.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Multi-Threaded Chat Server with Voice Calling")
    print("TCP Port: 5555 | UDP Port: 5556")
    print("=" * 50)
    start_server()
