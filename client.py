import socket
import threading
import sys
import json
import os
import struct
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("[WARNING] PyAudio not installed. Voice calling disabled.")
    print("Install with: pip install pyaudio")

# Server configuration
HOST = '10.102.62.11'
PORT = 5555
UDP_PORT = 5556

# Global variables
username = ""
active_users = []
current_room = "lobby"
file_receiving_mode = False
file_info = {}

# Voice calling variables
client_socket_tcp = None
udp_socket = None
in_call = False
call_partner = ""
audio_stream_in = None
audio_stream_out = None
p_audio = None

# Create downloads folder
downloads_dir = 'downloads'
if not os.path.exists(downloads_dir):
    os.makedirs(downloads_dir)


def audio_send_thread():
    """Thread to capture and send audio via UDP"""
    global in_call, udp_socket, username
    
    if not PYAUDIO_AVAILABLE or not p_audio:
        return
    
    try:
        # Audio stream configuration
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        stream = p_audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
        
        print("[VOICE] Microphone active")
        
        while in_call:
            try:
                # Read audio data
                audio_data = stream.read(CHUNK, exception_on_overflow=False)
                
                # Prepend username for server routing
                username_bytes = username.encode('utf-8')
                username_len = struct.pack('>H', len(username_bytes))
                packet = username_len + username_bytes + audio_data
                
                # Send via UDP
                udp_socket.sendto(packet, (HOST, UDP_PORT))
            except Exception as e:
                if in_call:
                    print(f"[VOICE ERROR] Send: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        
    except Exception as e:
        print(f"[VOICE ERROR] Audio capture: {e}")


def audio_receive_thread():
    """Thread to receive and play audio via UDP"""
    global in_call, udp_socket, p_audio
    
    if not PYAUDIO_AVAILABLE or not p_audio:
        return
    
    try:
        # Audio stream configuration
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        stream = p_audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            output=True,
                            frames_per_buffer=CHUNK)
        
        print("[VOICE] Speaker active")
        
        while in_call:
            try:
                # Receive audio data
                data, addr = udp_socket.recvfrom(8192)
                
                # Play audio
                if data and in_call:
                    stream.write(data)
            except socket.timeout:
                # Timeout is normal when no audio is being sent
                continue
            except Exception as e:
                if in_call:
                    print(f"[VOICE ERROR] Receive: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        
    except Exception as e:
        print(f"[VOICE ERROR] Audio playback: {e}")


def start_voice_call():
    """Start voice call audio streams"""
    global in_call, p_audio, udp_socket
    
    if not PYAUDIO_AVAILABLE:
        print("[VOICE] PyAudio not available. Voice calling disabled.")
        return
    
    in_call = True
    
    try:
        # Initialize PyAudio only once if not already initialized
        if p_audio is None:
            p_audio = pyaudio.PyAudio()
        
        # Start audio threads
        send_thread = threading.Thread(target=audio_send_thread, daemon=True)
        receive_thread = threading.Thread(target=audio_receive_thread, daemon=True)
        
        send_thread.start()
        receive_thread.start()
        
    except Exception as e:
        print(f"[VOICE ERROR] Failed to start call: {e}")
        in_call = False


def stop_voice_call():
    """Stop voice call audio streams"""
    global in_call
    
    # Set flag to false to stop audio threads
    in_call = False
    
    # Give threads time to finish gracefully
    import time
    time.sleep(0.2)


def receive_messages(client_socket):
    """Thread function to receive messages from server"""
    global active_users, file_receiving_mode, file_info, call_partner
    buffer = ""
    
    while True:
        try:
            # Check if we're in file receiving mode
            if file_receiving_mode:
                try:
                    # Read file size header (4 bytes)
                    size_data = client_socket.recv(4)
                    if len(size_data) != 4:
                        print("\r[ERROR] Invalid file size header")
                        file_receiving_mode = False
                        print("You: ", end='', flush=True)
                        continue
                    
                    expected_size = struct.unpack('>I', size_data)[0]
                    filename = file_info.get('filename', 'unknown_file')
                    sender = file_info.get('sender', 'Unknown')
                    
                    # Receive raw binary data
                    filedata = b''
                    remaining = expected_size
                    
                    print(f"\r[FILE] Receiving {filename} ({expected_size} bytes) from {sender}...")
                    
                    while remaining > 0:
                        chunk_size = min(4096, remaining)
                        chunk = client_socket.recv(chunk_size)
                        
                        if not chunk:
                            print("\r[ERROR] Connection lost during file transfer")
                            break
                        
                        filedata += chunk
                        remaining -= len(chunk)
                    
                    # Save file to downloads folder
                    if len(filedata) == expected_size:
                        safe_filename = os.path.basename(filename)
                        
                        # Create downloads directory if it doesn't exist
                        downloads_dir = 'downloads'
                        if not os.path.exists(downloads_dir):
                            os.makedirs(downloads_dir)
                        
                        filepath = os.path.join(downloads_dir, safe_filename)
                        
                        # Handle duplicate filenames
                        counter = 1
                        base_name, ext = os.path.splitext(safe_filename)
                        while os.path.exists(filepath):
                            filepath = os.path.join(downloads_dir, f"{base_name}_{counter}{ext}")
                            counter += 1
                        
                        with open(filepath, 'wb') as f:
                            f.write(filedata)
                        
                        # Use forward slashes for display
                        display_path = filepath.replace('\\', '/')
                        print(f"\r[FILE RECEIVED] {filename} saved to {display_path}")
                    else:
                        print(f"\r[ERROR] File transfer incomplete ({len(filedata)}/{expected_size} bytes)")
                    
                except Exception as e:
                    print(f"\r[ERROR] File receive error: {e}")
                
                finally:
                    file_receiving_mode = False
                    file_info = {}
                    print("You: ", end='', flush=True)
                    continue
            
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                # Server closed connection
                print("\n[DISCONNECTED] Connection to server lost.")
                client_socket.close()
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
                    
                    if msg_type == "login_success":
                        print(f"\r{payload}")
                        print("You: ", end='', flush=True)
                        
                    elif msg_type == "error":
                        print(f"\r[ERROR] {payload}")
                        # Don't exit for non-critical errors
                        print("You: ", end='', flush=True)
                        
                    elif msg_type == "notification":
                        print(f"\r[NOTIFICATION] {payload}")
                        print("You: ", end='', flush=True)
                        
                    elif msg_type == "message":
                        sender = message.get("sender", "Unknown")
                        print(f"\r[{sender}] {payload}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "private_message":
                        sender = message.get("sender", "Unknown")
                        print(f"\r[PRIVATE from {sender}] {payload}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "private_sent":
                        target = message.get("target", "Unknown")
                        print(f"\r[PRIVATE to {target}] {payload}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "room_list":
                        print(f"\r\n{'='*50}")
                        print("AVAILABLE ROOMS:")
                        print('='*50)
                        for room, users in payload.items():
                            print(f"  Room: {room}")
                            print(f"    Users: {', '.join(users)}")
                        print('='*50)
                        print("You: ", end='', flush=True)
                        
                    elif msg_type == "user_list":
                        active_users = payload
                        print(f"\r[ACTIVE USERS] {', '.join(active_users)}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "file_incoming":
                        file_receiving_mode = True
                        file_info = {
                            'filename': message.get('filename'),
                            'filesize': message.get('filesize'),
                            'sender': message.get('sender')
                        }
                        # File will be received in next iteration
                        continue
                    
                    elif msg_type == "file_transfer_ready":
                        # Server is ready to receive file
                        print(f"\r[FILE] Server ready, starting transfer...")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "file_sent_confirm":
                        print(f"\r[FILE] {payload}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "call_incoming":
                        caller = payload
                        print(f"\r\n{'='*50}")
                        print(f"📞 INCOMING CALL from {caller}")
                        print(f"{'='*50}")
                        print("Type '/accept' to answer or '/reject' to decline")
                        print("You: ", end='', flush=True)
                        global call_partner
                        call_partner = caller
                    
                    elif msg_type == "call_ringing":
                        print(f"\r{payload}")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "call_started":
                        partner = payload
                        call_partner = partner
                        print(f"\r\n{'='*50}")
                        print(f"📞 CALL CONNECTED with {partner}")
                        print(f"{'='*50}")
                        print("Type '/hangup' to end call")
                        print("You: ", end='', flush=True)
                        
                        if PYAUDIO_AVAILABLE:
                            start_voice_call()
                    
                    elif msg_type == "call_rejected":
                        print(f"\r[CALL] {payload}")
                        print("You: ", end='', flush=True)
                        call_partner = ""
                    
                    elif msg_type == "call_ended":
                        print(f"\r\n{'='*50}")
                        print(f"📞 CALL ENDED: {payload}")
                        print(f"{'='*50}")
                        print("You: ", end='', flush=True)
                        stop_voice_call()
                        call_partner = ""
                    
                    elif msg_type == "room_info":
                        global current_room
                        room_data = payload
                        current_room = room_data['room']
                        members = room_data['members']
                        
                        print(f"\r{'='*50}")
                        print(f"CURRENT ROOM: {current_room}")
                        print(f"MEMBERS: {', '.join(members)}")
                        print('='*50)
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "join_request":
                        request_data = payload
                        requester = request_data.get('user')
                        room = request_data.get('room')
                        
                        print(f"\r\n{'='*50}")
                        print(f"📥 JOIN REQUEST")
                        print(f"User '{requester}' wants to join '{room}'")
                        print(f"{'='*50}")
                        print(f"Type '/approve {requester}' or '/reject {requester}'")
                        print("You: ", end='', flush=True)
                    
                    elif msg_type == "room_details":
                        details = payload
                        room = details.get('room')
                        owner = details.get('owner')
                        members = details.get('members', [])
                        current_users = details.get('current_users', [])
                        pending = details.get('pending_requests', [])
                        
                        print(f"\r\n{'='*50}")
                        print(f"ROOM: {room}")
                        print(f"{'='*50}")
                        print(f"Owner: {owner}")
                        print(f"Members ({len(members)}): {', '.join(members) if members else 'None'}")
                        print(f"Currently Online ({len(current_users)}): {', '.join(current_users) if current_users else 'None'}")
                        if pending:
                            print(f"Pending Requests ({len(pending)}): {', '.join(pending)}")
                        print('='*50)
                        print("You: ", end='', flush=True)
                        
                except json.JSONDecodeError:
                    print(f"\r[ERROR] Invalid message from server")
                    continue
                    
        except Exception as e:
            print(f"\n[ERROR] {e}")
            client_socket.close()
            break


def send_messages(client_socket):
    """Thread function to send messages to server"""
    global call_partner, in_call
    while True:
        try:
            print("You: ", end='', flush=True)
            message = input()
            
            if not message.strip():
                continue
            
            # Handle commands
            if message.lower() == '/quit':
                print("[INFO] Disconnecting...")
                client_socket.close()
                sys.exit(0)
            
            elif message.lower() == '/help':
                print("\r\n" + "="*50)
                print("AVAILABLE COMMANDS:")
                print("="*50)
                print("  /help                        - Show this help menu")
                print("  /pm <user> <message>         - Send private message")
                print("\nRoom Management:")
                print("  /createroom <name>           - Create a new private room (you become owner)")
                print("  /join <room>                 - Join a room (if you have access)")
                print("  /requestjoin <room>          - Request to join a private room")
                print("  /rooms                       - List all rooms and users")
                print("  /roominfo [room]             - Show room details and members")
                print("\nRoom Owner Commands:")
                print("  /adduser <user>              - Add user to your room")
                print("  /kickuser <user>             - Remove user from your room")
                print("  /approve <user>              - Approve pending join request")
                print("  /reject <user>               - Reject pending join request")
                print("\nFile Transfer:")
                print("  /sendfile <path>             - Send file to everyone in current room")
                print("  /sendfile <path> <user>      - Send file to specific user privately")
                print("  /broadcastfile <path>        - Send file to ALL users (entire server)")
                print("\nVoice Calling:")
                print("  /call <user>                 - Start voice call")
                print("  /accept                      - Accept incoming call")
                print("  /reject                      - Reject incoming call")
                print("  /hangup                      - End current call")
                print("\nOther:")
                print("  /quit                        - Disconnect from server")
                print("="*50)
                print("Files are saved to 'downloads/' folder")
                print("Note: 'lobby' is public, all other rooms require permission")
                if not PYAUDIO_AVAILABLE:
                    print("⚠️  PyAudio not installed - Voice calling disabled")
                print("="*50)
                continue
            
            elif message.startswith('/call '):
                # Start voice call
                if not PYAUDIO_AVAILABLE:
                    print("\r[ERROR] PyAudio not installed. Install with: pip install pyaudio")
                    continue
                
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /call <username>")
                    continue
                
                target_user = parts[1].strip()
                
                msg_dict = {
                    "type": "call_request",
                    "payload": target_user
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.lower() == '/accept':
                # Accept incoming call
                if not call_partner:
                    print("\r[ERROR] No incoming call")
                    continue
                
                msg_dict = {
                    "type": "call_accept",
                    "payload": call_partner
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.lower() == '/reject':
                # Reject incoming call
                if not call_partner:
                    print("\r[ERROR] No incoming call")
                    continue
                
                msg_dict = {
                    "type": "call_reject",
                    "payload": call_partner
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
                
                call_partner = ""
            
            elif message.lower() == '/hangup':
                # End current call
                if not in_call:
                    print("\r[ERROR] No active call")
                    continue
                
                msg_dict = {
                    "type": "call_end",
                    "payload": ""
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
                
                stop_voice_call()
            
            elif message.startswith('/pm '):
                # Private message: /pm username message
                parts = message.split(' ', 2)
                if len(parts) < 3:
                    print("\r[ERROR] Usage: /pm <username> <message>")
                    continue
                
                target_user = parts[1]
                private_msg = parts[2]
                
                msg_dict = {
                    "type": "private_message",
                    "target": target_user,
                    "payload": private_msg
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/createroom '):
                # Create room: /createroom roomname
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /createroom <room_name>")
                    continue
                
                room_name = parts[1].strip()
                
                msg_dict = {
                    "type": "create_room",
                    "payload": room_name
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/join '):
                # Join room: /join roomname
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /join <room_name>")
                    continue
                
                room_name = parts[1].strip()
                
                msg_dict = {
                    "type": "join_room",
                    "payload": room_name
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/requestjoin '):
                # Request to join room: /requestjoin roomname
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /requestjoin <room_name>")
                    continue
                
                room_name = parts[1].strip()
                
                msg_dict = {
                    "type": "request_join",
                    "payload": room_name
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.lower() == '/rooms':
                # List all rooms
                msg_dict = {
                    "type": "list_rooms",
                    "payload": ""
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/roominfo'):
                # Show room details: /roominfo [roomname]
                parts = message.split(' ', 1)
                room_name = parts[1].strip() if len(parts) > 1 else ""
                
                msg_dict = {
                    "type": "room_details",
                    "payload": room_name
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/adduser '):
                # Add user to room: /adduser username
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /adduser <username>")
                    continue
                
                target_user = parts[1].strip()
                
                msg_dict = {
                    "type": "add_user",
                    "payload": {
                        "user": target_user,
                        "room": current_room
                    }
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/kickuser '):
                # Kick user from room: /kickuser username
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /kickuser <username>")
                    continue
                
                target_user = parts[1].strip()
                
                msg_dict = {
                    "type": "kick_user",
                    "payload": {
                        "user": target_user,
                        "room": current_room
                    }
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/approve '):
                # Approve join request: /approve username
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /approve <username>")
                    continue
                
                target_user = parts[1].strip()
                
                msg_dict = {
                    "type": "approve_user",
                    "payload": {
                        "user": target_user,
                        "room": current_room
                    }
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/reject ') and not message.lower() == '/reject':
                # Reject join request: /reject username (but not /reject for calls)
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /reject <username>")
                    continue
                
                target_user = parts[1].strip()
                
                msg_dict = {
                    "type": "reject_user",
                    "payload": {
                        "user": target_user,
                        "room": current_room
                    }
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
            elif message.startswith('/sendfile '):
                # Send file: /sendfile filepath [target_user]
                parts = message.split(' ', 2)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /sendfile <filepath> [target_user]")
                    continue
                
                filepath = parts[1].strip()
                target_user = parts[2].strip() if len(parts) > 2 else None
                
                if not os.path.exists(filepath):
                    print(f"\r[ERROR] File not found: {filepath}")
                    continue
                
                if not os.path.isfile(filepath):
                    print(f"\r[ERROR] Not a file: {filepath}")
                    continue
                
                # Read file in binary mode
                try:
                    with open(filepath, 'rb') as f:
                        filedata = f.read()
                    
                    filename = os.path.basename(filepath)
                    filesize = len(filedata)
                    
                    if target_user:
                        print(f"\r[FILE] Sending {filename} ({filesize} bytes) to {target_user}...")
                    else:
                        print(f"\r[FILE] Sending {filename} ({filesize} bytes) to room...")
                    
                    # Send file transfer header
                    file_header = {
                        "type": "file_transfer",
                        "filename": filename,
                        "filesize": filesize,
                        "target": target_user
                    }
                    header_json = json.dumps(file_header) + "\n"
                    client_socket.send(header_json.encode('utf-8'))
                    
                    # Wait for server ready confirmation (brief pause)
                    import time
                    time.sleep(0.1)
                    
                    # Send file size as 4-byte integer
                    client_socket.send(struct.pack('>I', filesize))
                    
                    # Send raw binary data in chunks
                    chunk_size = 4096
                    for i in range(0, filesize, chunk_size):
                        chunk = filedata[i:i + chunk_size]
                        client_socket.send(chunk)
                    
                    print(f"\r[FILE] Transfer complete, waiting for confirmation...")
                    
                except Exception as e:
                    print(f"\r[ERROR] Failed to send file: {e}")
                    continue
            
            elif message.startswith('/broadcastfile '):
                # Broadcast file to ALL users: /broadcastfile filepath
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("\r[ERROR] Usage: /broadcastfile <filepath>")
                    continue
                
                filepath = parts[1].strip()
                
                if not os.path.exists(filepath):
                    print(f"\r[ERROR] File not found: {filepath}")
                    continue
                
                if not os.path.isfile(filepath):
                    print(f"\r[ERROR] Not a file: {filepath}")
                    continue
                
                # Read file in binary mode
                try:
                    with open(filepath, 'rb') as f:
                        filedata = f.read()
                    
                    filename = os.path.basename(filepath)
                    filesize = len(filedata)
                    
                    print(f"\r[FILE] Broadcasting {filename} ({filesize} bytes) to ALL users...")
                    
                    # Send file broadcast header
                    file_header = {
                        "type": "file_broadcast",
                        "filename": filename,
                        "filesize": filesize
                    }
                    header_json = json.dumps(file_header) + "\n"
                    client_socket.send(header_json.encode('utf-8'))
                    
                    # Wait for server ready confirmation (brief pause)
                    import time
                    time.sleep(0.1)
                    
                    # Send file size as 4-byte integer
                    client_socket.send(struct.pack('>I', filesize))
                    
                    # Send raw binary data in chunks
                    chunk_size = 4096
                    for i in range(0, filesize, chunk_size):
                        chunk = filedata[i:i + chunk_size]
                        client_socket.send(chunk)
                    
                    print(f"\r[FILE] Broadcast complete, waiting for confirmation...")
                    
                except Exception as e:
                    print(f"\r[ERROR] Failed to broadcast file: {e}")
                    continue
            
            else:
                # Regular group message to current room
                msg_dict = {
                    "type": "message",
                    "payload": message
                }
                json_message = json.dumps(msg_dict) + "\n"
                client_socket.send(json_message.encode('utf-8'))
            
        except Exception as e:
            print(f"\n[ERROR] {e}")
            client_socket.close()
            break


def start_client():
    """Initialize and connect to the server"""
    global username, client_socket_tcp, udp_socket
    
    try:
        # Create TCP socket and connect to server
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((HOST, PORT))
        client_socket_tcp = client
        
        # Create UDP socket for voice
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(2.0)  # Non-blocking with timeout
        
        print("=" * 50)
        print("Connected to Chat Server")
        print("TCP: Chat | UDP: Voice Calling")
        print("=" * 50)
        
        # Get username from user
        while True:
            username = input("Enter your username: ").strip()
            if username:
                break
            print("Username cannot be empty. Please try again.")
        
        # Send login message
        login_msg = {
            "type": "login",
            "payload": username
        }
        json_message = json.dumps(login_msg) + "\n"
        client.send(json_message.encode('utf-8'))
        
        print("\nType your messages and press Enter to send.")
        print("Type '/help' for available commands.")
        print("You are in room: lobby\n")
        
        # Create threads for receiving and sending
        receive_thread = threading.Thread(target=receive_messages, args=(client,))
        receive_thread.daemon = True
        receive_thread.start()
        
        send_thread = threading.Thread(target=send_messages, args=(client,))
        send_thread.daemon = True
        send_thread.start()
        
        # Keep main thread alive
        send_thread.join()
        
    except ConnectionRefusedError:
        print(f"[ERROR] Could not connect to server at {HOST}:{PORT}")
        print("Make sure the server is running first.")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        # Stop any active call
        stop_voice_call()
        
        # Clean up PyAudio
        global p_audio
        if p_audio:
            try:
                p_audio.terminate()
            except:
                pass
        
        # Close sockets
        try:
            client.close()
        except:
            pass
        try:
            if udp_socket:
                udp_socket.close()
        except:
            pass


if __name__ == "__main__":
    start_client()
