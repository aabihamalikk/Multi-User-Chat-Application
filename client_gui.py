import socket
import threading
import json
import os
import struct
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

# Server configuration
HOST = '10.102.62.11'
PORT = 5555
UDP_PORT = 5556

class ChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Application")
        self.root.geometry("1200x700")
        self.root.minsize(900, 600)
        
        # Variables
        self.username = ""
        self.client_socket = None
        self.udp_socket = None
        self.current_room = "lobby"
        self.active_users = []
        self.rooms = {}
        self.in_call = False
        self.call_partner = ""
        self.selected_chat = None
        self.chat_type = "room"  # "room" or "user"
        self.pending_requests = []
        self.is_room_owner = False
        self.current_tab = "rooms"
        self.messages_area = None
        self.sidebar_list = None
        
        # Voice calling variables
        self.p_audio = None
        self.audio_stream_in = None
        self.audio_stream_out = None
        
        # Create downloads folder
        self.downloads_dir = 'downloads'
        if not os.path.exists(self.downloads_dir):
            os.makedirs(self.downloads_dir)
        
        # Colors (WhatsApp-inspired)
        self.bg_color = "#0b141a"
        self.sidebar_bg = "#202c33"
        self.chat_bg = "#0b141a"
        self.message_bg_sent = "#005c4b"
        self.message_bg_received = "#202c33"
        self.input_bg = "#2a3942"
        self.text_color = "#e9edef"
        self.secondary_text = "#8696a0"
        self.accent_color = "#00a884"
        
        self.setup_login_screen()
    
    def setup_login_screen(self):
        """Setup login screen"""
        login_frame = tk.Frame(self.root, bg=self.bg_color)
        login_frame.pack(expand=True, fill='both')
        
        # Center container
        center = tk.Frame(login_frame, bg=self.sidebar_bg, padx=40, pady=40)
        center.place(relx=0.5, rely=0.5, anchor='center')
        
        # Title
        title = tk.Label(center, text="Chat Application", font=("Segoe UI", 24, "bold"),
                        bg=self.sidebar_bg, fg=self.text_color)
        title.pack(pady=(0, 30))
        
        # Username label
        tk.Label(center, text="Enter your username:", font=("Segoe UI", 12),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=(0, 10))
        
        # Username entry
        self.username_entry = tk.Entry(center, font=("Segoe UI", 12), width=30,
                                      bg=self.input_bg, fg=self.text_color,
                                      insertbackground=self.text_color, relief='flat')
        self.username_entry.pack(pady=(0, 20), ipady=8)
        self.username_entry.bind('<Return>', lambda e: self.connect_to_server())
        self.username_entry.focus()
        
        # Connect button
        self.connect_btn = tk.Button(center, text="Connect", font=("Segoe UI", 12, "bold"),
                                     bg=self.accent_color, fg="white", relief='flat',
                                     cursor="hand2", command=self.connect_to_server,
                                     padx=40, pady=10)
        self.connect_btn.pack()
        
        # Status label
        self.status_label = tk.Label(center, text="", font=("Segoe UI", 10),
                                     bg=self.sidebar_bg, fg="#ff6b6b")
        self.status_label.pack(pady=(10, 0))
    
    def connect_to_server(self):
        """Connect to the chat server"""
        username = self.username_entry.get().strip()
        
        if not username:
            self.status_label.config(text="Username cannot be empty")
            return
        
        self.username = username
        self.connect_btn.config(state='disabled', text="Connecting...")
        
        # Connect in a separate thread
        threading.Thread(target=self._establish_connection, daemon=True).start()
    
    def _establish_connection(self):
        """Establish connection to server"""
        try:
            # Create TCP socket
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((HOST, PORT))
            
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(2.0)
            
            # Send login message
            login_msg = {"type": "login", "payload": self.username}
            self.send_json(login_msg)
            
            # Start receiving thread
            threading.Thread(target=self.receive_messages, daemon=True).start()
            
            # Switch to main chat screen
            self.root.after(100, self.setup_main_screen)
            
            # Request initial data
            self.root.after(200, self.request_initial_data)
            
        except ConnectionRefusedError:
            self.root.after(0, lambda: self.status_label.config(
                text=f"Could not connect to server at {HOST}:{PORT}"))
            self.root.after(0, lambda: self.connect_btn.config(state='normal', text="Connect"))
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            self.root.after(0, lambda: self.connect_btn.config(state='normal', text="Connect"))
    
    def setup_main_screen(self):
        """Setup main chat interface"""
        # Clear login screen
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Main container
        main_container = tk.Frame(self.root, bg=self.bg_color)
        main_container.pack(expand=True, fill='both')
        
        # Left sidebar (contacts/rooms)
        self.setup_sidebar(main_container)
        
        # Right chat area
        self.setup_chat_area(main_container)
    
    def setup_sidebar(self, parent):
        """Setup left sidebar with rooms and users"""
        sidebar = tk.Frame(parent, bg=self.sidebar_bg, width=350)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        
        # Header
        header = tk.Frame(sidebar, bg=self.sidebar_bg, height=60)
        header.pack(fill='x', padx=10, pady=10)
        
        # Username display
        tk.Label(header, text=f"👤 {self.username}", font=("Segoe UI", 14, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(side='left')
        
        # Menu button
        menu_btn = tk.Button(header, text="⋮", font=("Segoe UI", 16),
                            bg=self.sidebar_bg, fg=self.text_color, relief='flat',
                            cursor="hand2", command=self.show_menu)
        menu_btn.pack(side='right')
        
        # Search/Action bar
        action_bar = tk.Frame(sidebar, bg=self.sidebar_bg)
        action_bar.pack(fill='x', padx=10, pady=(0, 10))
        
        # Create Room button
        tk.Button(action_bar, text="➕ Create Room", font=("Segoe UI", 10),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=self.create_room_dialog).pack(side='left', padx=(0, 5))
        
        # Request Join button
        tk.Button(action_bar, text="📨 Request Join", font=("Segoe UI", 10),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=self.request_join_dialog).pack(side='left')
        
        # Tabs for Rooms and Users
        tab_frame = tk.Frame(sidebar, bg=self.sidebar_bg)
        tab_frame.pack(fill='x', padx=10)
        
        self.rooms_tab_btn = tk.Button(tab_frame, text="Rooms", font=("Segoe UI", 11),
                                       bg=self.accent_color, fg="white", relief='flat',
                                       cursor="hand2", command=lambda: self.switch_tab("rooms"))
        self.rooms_tab_btn.pack(side='left', fill='x', expand=True, pady=5, padx=(0, 2))
        
        self.users_tab_btn = tk.Button(tab_frame, text="Users", font=("Segoe UI", 11),
                                       bg=self.input_bg, fg=self.text_color, relief='flat',
                                       cursor="hand2", command=lambda: self.switch_tab("users"))
        self.users_tab_btn.pack(side='left', fill='x', expand=True, pady=5, padx=(2, 0))
        
        # List container
        list_container = tk.Frame(sidebar, bg=self.sidebar_bg)
        list_container.pack(fill='both', expand=True, padx=10, pady=(5, 10))
        
        # Scrollable list
        canvas = tk.Canvas(list_container, bg=self.sidebar_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.sidebar_list = tk.Frame(canvas, bg=self.sidebar_bg)
        
        self.sidebar_list.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sidebar_list, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.current_tab = "rooms"
        self.update_sidebar_list()
    
    def setup_chat_area(self, parent):
        """Setup right chat area"""
        chat_container = tk.Frame(parent, bg=self.chat_bg)
        chat_container.pack(side='right', fill='both', expand=True)
        
        # Chat header
        self.chat_header = tk.Frame(chat_container, bg=self.sidebar_bg, height=60)
        self.chat_header.pack(fill='x')
        
        self.chat_title = tk.Label(self.chat_header, text="Select a chat", 
                                   font=("Segoe UI", 14, "bold"),
                                   bg=self.sidebar_bg, fg=self.text_color)
        self.chat_title.pack(side='left', padx=20, pady=15)
        
        # Chat actions
        self.chat_actions = tk.Frame(self.chat_header, bg=self.sidebar_bg)
        self.chat_actions.pack(side='right', padx=20)
        
        # Messages area
        messages_frame = tk.Frame(chat_container, bg=self.chat_bg)
        messages_frame.pack(fill='both', expand=True)
        
        # Scrolled text for messages
        self.messages_area = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD,
                                                       font=("Segoe UI", 11),
                                                       bg=self.chat_bg, fg=self.text_color,
                                                       relief='flat', state='disabled',
                                                       cursor="arrow")
        self.messages_area.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Configure text tags for message styling
        self.messages_area.tag_config("sent", background=self.message_bg_sent, 
                                     foreground=self.text_color, justify='right',
                                     lmargin1=100, lmargin2=100, rmargin=10)
        self.messages_area.tag_config("received", background=self.message_bg_received,
                                     foreground=self.text_color, justify='left',
                                     lmargin1=10, lmargin2=10, rmargin=100)
        self.messages_area.tag_config("system", foreground=self.secondary_text,
                                     justify='center')
        self.messages_area.tag_config("time", foreground=self.secondary_text,
                                     font=("Segoe UI", 9))
        
        # Input area
        input_frame = tk.Frame(chat_container, bg=self.sidebar_bg)
        input_frame.pack(fill='x', padx=10, pady=10)
        
        # Attach button
        self.attach_btn = tk.Button(input_frame, text="📎", font=("Segoe UI", 14),
                                    bg=self.sidebar_bg, fg=self.text_color, relief='flat',
                                    cursor="hand2", command=self.send_file)
        self.attach_btn.pack(side='left', padx=(5, 5))
        
        # Message entry
        self.message_entry = tk.Text(input_frame, height=2, font=("Segoe UI", 11),
                                    bg=self.input_bg, fg=self.text_color,
                                    insertbackground=self.text_color, relief='flat',
                                    wrap='word')
        self.message_entry.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        self.message_entry.bind('<Return>', self.send_message)
        self.message_entry.bind('<Shift-Return>', lambda e: None)  # Allow shift+enter for newline
        
        # Send button
        self.send_btn = tk.Button(input_frame, text="▶", font=("Segoe UI", 14),
                                 bg=self.accent_color, fg="white", relief='flat',
                                 cursor="hand2", command=self.send_message)
        self.send_btn.pack(side='right', padx=5)
    
    def switch_tab(self, tab):
        """Switch between rooms and users tabs"""
        self.current_tab = tab
        
        if tab == "rooms":
            self.rooms_tab_btn.config(bg=self.accent_color, fg="white")
            self.users_tab_btn.config(bg=self.input_bg, fg=self.text_color)
        else:
            self.rooms_tab_btn.config(bg=self.input_bg, fg=self.text_color)
            self.users_tab_btn.config(bg=self.accent_color, fg="white")
        
        self.update_sidebar_list()
    
    def update_sidebar_list(self):
        """Update the sidebar list with rooms or users"""
        if not self.sidebar_list:
            return
        
        # Clear current list
        for widget in self.sidebar_list.winfo_children():
            widget.destroy()
        
        if self.current_tab == "rooms":
            # Show rooms - always show lobby first
            if 'lobby' not in self.rooms:
                self.rooms['lobby'] = []
            
            # Show lobby first
            if 'lobby' in self.rooms:
                self.create_room_item('lobby', self.rooms['lobby'])
            
            # Show other rooms
            for room, users in sorted(self.rooms.items()):
                if room != 'lobby':  # Skip lobby since we already showed it
                    self.create_room_item(room, users)
            
            # If only lobby exists, show a hint
            if len(self.rooms) <= 1:
                tk.Label(self.sidebar_list, text="\nCreate or request to join rooms",
                        font=("Segoe UI", 9, "italic"), bg=self.sidebar_bg,
                        fg=self.secondary_text).pack(pady=5)
        else:
            # Show users
            if not self.active_users:
                tk.Label(self.sidebar_list, text="No users online",
                        font=("Segoe UI", 10), bg=self.sidebar_bg,
                        fg=self.secondary_text).pack(pady=20)
            else:
                for user in self.active_users:
                    if user != self.username:
                        self.create_user_item(user)
    
    def create_room_item(self, room, users):
        """Create a room item in the sidebar"""
        item = tk.Frame(self.sidebar_list, bg=self.input_bg if room != self.current_room else self.accent_color,
                       cursor="hand2")
        item.pack(fill='x', pady=2)
        item.bind('<Button-1>', lambda e: self.select_room(room))
        
        content = tk.Frame(item, bg=item['bg'])
        content.pack(fill='x', padx=10, pady=10)
        content.bind('<Button-1>', lambda e: self.select_room(room))
        
        # Room icon and name
        name_label = tk.Label(content, text=f"🏠 {room}", font=("Segoe UI", 12, "bold"),
                            bg=content['bg'], fg=self.text_color, anchor='w')
        name_label.pack(anchor='w')
        name_label.bind('<Button-1>', lambda e: self.select_room(room))
        
        # User count
        count_label = tk.Label(content, text=f"{len(users)} members",
                             font=("Segoe UI", 9), bg=content['bg'],
                             fg=self.secondary_text, anchor='w')
        count_label.pack(anchor='w')
        count_label.bind('<Button-1>', lambda e: self.select_room(room))
    
    def create_user_item(self, user):
        """Create a user item in the sidebar"""
        item = tk.Frame(self.sidebar_list, bg=self.input_bg, cursor="hand2")
        item.pack(fill='x', pady=2)
        item.bind('<Button-1>', lambda e: self.select_user(user))
        
        content = tk.Frame(item, bg=item['bg'])
        content.pack(fill='x', padx=10, pady=10)
        content.bind('<Button-1>', lambda e: self.select_user(user))
        
        # User icon and name
        name_label = tk.Label(content, text=f"👤 {user}", font=("Segoe UI", 12),
                            bg=content['bg'], fg=self.text_color, anchor='w')
        name_label.pack(anchor='w')
        name_label.bind('<Button-1>', lambda e: self.select_user(user))
        
        # Online status
        status_label = tk.Label(content, text="🟢 Online",
                              font=("Segoe UI", 9), bg=content['bg'],
                              fg=self.accent_color, anchor='w')
        status_label.pack(anchor='w')
        status_label.bind('<Button-1>', lambda e: self.select_user(user))
    
    def select_room(self, room):
        """Select a room to chat in"""
        self.selected_chat = room
        self.chat_type = "room"
        self.chat_title.config(text=f"🏠 {room}")
        
        # Clear and update chat actions
        for widget in self.chat_actions.winfo_children():
            widget.destroy()
        
        # Add room info button
        tk.Button(self.chat_actions, text="ℹ️ Info", font=("Segoe UI", 10),
                 bg=self.sidebar_bg, fg=self.text_color, relief='flat',
                 cursor="hand2", command=self.show_room_info).pack(side='left', padx=5)
        
        # If not in this room, automatically join it
        if room != self.current_room:
            tk.Button(self.chat_actions, text="➡️ Join", font=("Segoe UI", 10),
                     bg=self.accent_color, fg="white", relief='flat',
                     cursor="hand2", command=lambda: self.join_room(room)).pack(side='left')
            # Auto-join if user clicks on the room
            self.join_room(room)
        
        self.display_system_message(f"Selected room: {room}")
    
    def select_user(self, user):
        """Select a user for private chat"""
        self.selected_chat = user
        self.chat_type = "user"
        self.chat_title.config(text=f"👤 {user}")
        
        # Clear and update chat actions
        for widget in self.chat_actions.winfo_children():
            widget.destroy()
        
        # Update call UI based on current state
        if self.call_partner == user and (self.in_call or self.call_partner):
            # Show hangup/cancel button (works during ringing or active call)
            tk.Button(self.chat_actions, text="📞 Hang Up", font=("Segoe UI", 10),
                     bg="#dc3545", fg="white", relief='flat',
                     cursor="hand2", command=self.hangup_call).pack(side='left')
        elif PYAUDIO_AVAILABLE:
            # Show call button
            tk.Button(self.chat_actions, text="📞 Call", font=("Segoe UI", 10),
                     bg=self.accent_color, fg="white", relief='flat',
                     cursor="hand2", command=lambda: self.start_call(user)).pack(side='left')
        
        self.display_system_message(f"Private chat with {user}")
    
    def send_message(self, event=None):
        """Send a message"""
        if event and event.state & 0x1:  # Shift key pressed
            return
        
        message = self.message_entry.get("1.0", "end-1c").strip()
        
        if not message:
            return "break"
        
        if not self.selected_chat:
            messagebox.showwarning("No chat selected", "Please select a room or user first")
            return "break"
        
        # Clear entry
        self.message_entry.delete("1.0", tk.END)
        
        if self.chat_type == "room":
            # Check if we're in the room
            if self.selected_chat != self.current_room:
                # Try to join the room first
                self.join_room(self.selected_chat)
                # Queue the message to send after join
                self.root.after(200, lambda: self._send_queued_message(message))
                return "break"
            
            # Send to room
            msg_dict = {"type": "message", "payload": message}
            self.send_json(msg_dict)
            self.display_message("You", message, sent=True)
        else:
            # Send private message
            msg_dict = {
                "type": "private_message",
                "target": self.selected_chat,
                "payload": message
            }
            self.send_json(msg_dict)
            self.display_message(f"You → {self.selected_chat}", message, sent=True)
        
        return "break"
    
    def _send_queued_message(self, message):
        """Send a message that was queued after room join"""
        if self.chat_type == "room" and self.selected_chat == self.current_room:
            msg_dict = {"type": "message", "payload": message}
            self.send_json(msg_dict)
            self.display_message("You", message, sent=True)
    
    def send_file(self):
        """Send a file"""
        if not self.selected_chat:
            messagebox.showwarning("No chat selected", "Please select a room or user first")
            return
        
        filepath = filedialog.askopenfilename(title="Select file to send")
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'rb') as f:
                filedata = f.read()
            
            filename = os.path.basename(filepath)
            filesize = len(filedata)
            
            if self.chat_type == "room":
                target = None
                self.display_system_message(f"Sending {filename} to room...")
            else:
                target = self.selected_chat
                self.display_system_message(f"Sending {filename} to {target}...")
            
            # Send file header
            file_header = {
                "type": "file_transfer",
                "filename": filename,
                "filesize": filesize,
                "target": target
            }
            self.send_json(file_header)
            
            # Wait briefly
            import time
            time.sleep(0.1)
            
            # Send file size
            self.client_socket.send(struct.pack('>I', filesize))
            
            # Send file data
            chunk_size = 4096
            for i in range(0, filesize, chunk_size):
                chunk = filedata[i:i + chunk_size]
                self.client_socket.send(chunk)
            
        except Exception as e:
            messagebox.showerror("File Send Error", f"Failed to send file: {e}")
    
    def create_room_dialog(self):
        """Show dialog to create a new room"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Room")
        dialog.geometry("400x200")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Create New Room", font=("Segoe UI", 16, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=20)
        
        tk.Label(dialog, text="Room Name:", font=("Segoe UI", 11),
                bg=self.sidebar_bg, fg=self.text_color).pack()
        
        entry = tk.Entry(dialog, font=("Segoe UI", 12), width=30,
                        bg=self.input_bg, fg=self.text_color,
                        insertbackground=self.text_color, relief='flat')
        entry.pack(pady=10, ipady=5)
        entry.focus()
        
        def create():
            room_name = entry.get().strip()
            if room_name:
                msg_dict = {"type": "create_room", "payload": room_name}
                self.send_json(msg_dict)
                dialog.destroy()
                # Request updated room list after a brief delay
                self.root.after(300, self.list_rooms)
        
        entry.bind('<Return>', lambda e: create())
        
        tk.Button(dialog, text="Create", font=("Segoe UI", 11, "bold"),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=create, padx=30, pady=8).pack(pady=10)
    
    def request_join_dialog(self):
        """Show dialog to request joining a room"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Request Join")
        dialog.geometry("400x200")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Request to Join Room", font=("Segoe UI", 16, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=20)
        
        tk.Label(dialog, text="Room Name:", font=("Segoe UI", 11),
                bg=self.sidebar_bg, fg=self.text_color).pack()
        
        entry = tk.Entry(dialog, font=("Segoe UI", 12), width=30,
                        bg=self.input_bg, fg=self.text_color,
                        insertbackground=self.text_color, relief='flat')
        entry.pack(pady=10, ipady=5)
        entry.focus()
        
        def request():
            room_name = entry.get().strip()
            if room_name:
                msg_dict = {"type": "request_join", "payload": room_name}
                self.send_json(msg_dict)
                dialog.destroy()
        
        entry.bind('<Return>', lambda e: request())
        
        tk.Button(dialog, text="Send Request", font=("Segoe UI", 11, "bold"),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=request, padx=30, pady=8).pack(pady=10)
    
    def join_room(self, room):
        """Join a room"""
        msg_dict = {"type": "join_room", "payload": room}
        self.send_json(msg_dict)
        # Optimistically update current room
        self.current_room = room
    
    def show_room_info(self):
        """Show room information"""
        if self.chat_type == "room" and self.selected_chat:
            msg_dict = {"type": "room_details", "payload": self.selected_chat}
            self.send_json(msg_dict)
    
    def start_call(self, user):
        """Start a voice call"""
        if not PYAUDIO_AVAILABLE:
            messagebox.showwarning("Voice Call", "PyAudio not installed. Voice calling disabled.\n\nInstall with: pip install pyaudio")
            return
        
        msg_dict = {"type": "call_request", "payload": user}
        self.send_json(msg_dict)
        self.call_partner = user
        self.display_system_message(f"📞 Calling {user}...")
        
        # Update chat actions to show hangup button
        self.update_call_ui(calling=True)
    
    def hangup_call(self):
        """Hang up current call"""
        if not self.in_call and not self.call_partner:
            messagebox.showinfo("No Call", "No active call to hang up")
            return
        
        msg_dict = {"type": "call_end", "payload": ""}
        self.send_json(msg_dict)
        self.stop_voice_call()
        self.call_partner = ""
        self.display_system_message("📞 Call ended")
        self.update_call_ui(calling=False)
    
    def update_call_ui(self, calling=False):
        """Update UI based on call status"""
        if self.chat_type != "user" or not self.selected_chat:
            return
        
        # Clear and update chat actions
        for widget in self.chat_actions.winfo_children():
            widget.destroy()
        
        if calling or self.in_call or (self.call_partner and self.call_partner == self.selected_chat):
            # Show hangup/cancel button (works during ringing or active call)
            tk.Button(self.chat_actions, text="📞 Hang Up", font=("Segoe UI", 10),
                     bg="#dc3545", fg="white", relief='flat',
                     cursor="hand2", command=self.hangup_call).pack(side='left')
        elif PYAUDIO_AVAILABLE:
            # Show call button
            tk.Button(self.chat_actions, text="📞 Call", font=("Segoe UI", 10),
                     bg=self.accent_color, fg="white", relief='flat',
                     cursor="hand2", command=lambda: self.start_call(self.selected_chat)).pack(side='left')
    
    def show_menu(self):
        """Show menu with options"""
        menu = tk.Menu(self.root, tearoff=0, bg=self.sidebar_bg, fg=self.text_color)
        menu.add_command(label="📋 View All Rooms", command=self.list_rooms)
        menu.add_command(label="ℹ️ Current Room Info", command=self.show_room_info)
        menu.add_separator()
        
        if self.chat_type == "room" and self.selected_chat == self.current_room:
            menu.add_command(label="➕ Add User to Room", command=self.add_user_dialog)
            menu.add_command(label="👢 Kick User from Room", command=self.kick_user_dialog)
            menu.add_separator()
        
        menu.add_command(label="📂 Broadcast File to All", command=self.broadcast_file)
        menu.add_separator()
        menu.add_command(label="🚪 Disconnect", command=self.disconnect)
        
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()
    
    def request_initial_data(self):
        """Request initial data after login"""
        # Request room list
        msg_dict = {"type": "list_rooms", "payload": ""}
        self.send_json(msg_dict)
    
    def list_rooms(self):
        """Request list of all rooms"""
        msg_dict = {"type": "list_rooms", "payload": ""}
        self.send_json(msg_dict)
    
    def add_user_dialog(self):
        """Show dialog to add user to current room"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add User")
        dialog.geometry("400x200")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Add User to Room", font=("Segoe UI", 16, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=20)
        
        tk.Label(dialog, text="Username:", font=("Segoe UI", 11),
                bg=self.sidebar_bg, fg=self.text_color).pack()
        
        entry = tk.Entry(dialog, font=("Segoe UI", 12), width=30,
                        bg=self.input_bg, fg=self.text_color,
                        insertbackground=self.text_color, relief='flat')
        entry.pack(pady=10, ipady=5)
        entry.focus()
        
        def add():
            username = entry.get().strip()
            if username:
                msg_dict = {
                    "type": "add_user",
                    "payload": {"user": username, "room": self.current_room}
                }
                self.send_json(msg_dict)
                dialog.destroy()
        
        entry.bind('<Return>', lambda e: add())
        
        tk.Button(dialog, text="Add User", font=("Segoe UI", 11, "bold"),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=add, padx=30, pady=8).pack(pady=10)
    
    def kick_user_dialog(self):
        """Show dialog to kick user from current room"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Kick User")
        dialog.geometry("400x200")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Kick User from Room", font=("Segoe UI", 16, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=20)
        
        tk.Label(dialog, text="Username:", font=("Segoe UI", 11),
                bg=self.sidebar_bg, fg=self.text_color).pack()
        
        entry = tk.Entry(dialog, font=("Segoe UI", 12), width=30,
                        bg=self.input_bg, fg=self.text_color,
                        insertbackground=self.text_color, relief='flat')
        entry.pack(pady=10, ipady=5)
        entry.focus()
        
        def kick():
            username = entry.get().strip()
            if username:
                msg_dict = {
                    "type": "kick_user",
                    "payload": {"user": username, "room": self.current_room}
                }
                self.send_json(msg_dict)
                dialog.destroy()
        
        entry.bind('<Return>', lambda e: kick())
        
        tk.Button(dialog, text="Kick User", font=("Segoe UI", 11, "bold"),
                 bg="#dc3545", fg="white", relief='flat',
                 cursor="hand2", command=kick, padx=30, pady=8).pack(pady=10)
    
    def broadcast_file(self):
        """Broadcast file to all users on server"""
        filepath = filedialog.askopenfilename(title="Select file to broadcast to all users")
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'rb') as f:
                filedata = f.read()
            
            filename = os.path.basename(filepath)
            filesize = len(filedata)
            
            self.display_system_message(f"📡 Broadcasting {filename} to ALL users...")
            
            # Send file header
            file_header = {
                "type": "file_broadcast",
                "filename": filename,
                "filesize": filesize
            }
            self.send_json(file_header)
            
            # Wait briefly
            import time
            time.sleep(0.1)
            
            # Send file size
            self.client_socket.send(struct.pack('>I', filesize))
            
            # Send file data
            chunk_size = 4096
            for i in range(0, filesize, chunk_size):
                chunk = filedata[i:i + chunk_size]
                self.client_socket.send(chunk)
            
        except Exception as e:
            messagebox.showerror("File Broadcast Error", f"Failed to broadcast file: {e}")
    
    def audio_send_thread(self):
        """Thread to capture and send audio via UDP"""
        if not PYAUDIO_AVAILABLE or not self.p_audio:
            return
        
        try:
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000
            
            stream = self.p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                       input=True, frames_per_buffer=CHUNK)
            
            while self.in_call:
                try:
                    audio_data = stream.read(CHUNK, exception_on_overflow=False)
                    username_bytes = self.username.encode('utf-8')
                    username_len = struct.pack('>H', len(username_bytes))
                    packet = username_len + username_bytes + audio_data
                    self.udp_socket.sendto(packet, (HOST, UDP_PORT))
                except Exception as e:
                    if self.in_call:
                        print(f"Voice send error: {e}")
                    break
            
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Audio capture error: {e}")
    
    def audio_receive_thread(self):
        """Thread to receive and play audio via UDP"""
        if not PYAUDIO_AVAILABLE or not self.p_audio:
            return
        
        try:
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000
            
            stream = self.p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                       output=True, frames_per_buffer=CHUNK)
            
            while self.in_call:
                try:
                    data, addr = self.udp_socket.recvfrom(8192)
                    if data and self.in_call:
                        stream.write(data)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.in_call:
                        print(f"Voice receive error: {e}")
                    break
            
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Audio playback error: {e}")
    
    def start_voice_call(self):
        """Start voice call audio streams"""
        if not PYAUDIO_AVAILABLE:
            self.display_system_message("⚠️ PyAudio not available. Voice calling disabled.")
            return
        
        self.in_call = True
        
        try:
            if self.p_audio is None:
                self.p_audio = pyaudio.PyAudio()
            
            send_thread = threading.Thread(target=self.audio_send_thread, daemon=True)
            receive_thread = threading.Thread(target=self.audio_receive_thread, daemon=True)
            
            send_thread.start()
            receive_thread.start()
            
        except Exception as e:
            self.display_system_message(f"❌ Failed to start call: {e}")
            self.in_call = False
    
    def stop_voice_call(self):
        """Stop voice call audio streams"""
        self.in_call = False
        import time
        time.sleep(0.2)
    
    def display_message(self, sender, message, sent=False):
        """Display a message in the chat area"""
        if not self.messages_area:
            return
        
        self.messages_area.config(state='normal')
        
        timestamp = datetime.now().strftime("%H:%M")
        
        if sent:
            self.messages_area.insert(tk.END, f"\n{message}\n", "sent")
            self.messages_area.insert(tk.END, f"{timestamp}\n", "time")
        else:
            self.messages_area.insert(tk.END, f"\n{sender}\n{message}\n", "received")
            self.messages_area.insert(tk.END, f"{timestamp}\n", "time")
        
        self.messages_area.config(state='disabled')
        self.messages_area.see(tk.END)
    
    def display_system_message(self, message):
        """Display a system message"""
        if not self.messages_area:
            return
        
        self.messages_area.config(state='normal')
        self.messages_area.insert(tk.END, f"\n{message}\n", "system")
        self.messages_area.config(state='disabled')
        self.messages_area.see(tk.END)
    
    def send_json(self, message_dict):
        """Send JSON message to server"""
        try:
            message = json.dumps(message_dict) + "\n"
            self.client_socket.send(message.encode('utf-8'))
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def receive_messages(self):
        """Receive messages from server"""
        buffer = ""
        file_receiving_mode = False
        file_info = {}
        
        while True:
            try:
                if file_receiving_mode:
                    # Receive file
                    try:
                        size_data = self.client_socket.recv(4)
                        if len(size_data) != 4:
                            file_receiving_mode = False
                            continue
                        
                        expected_size = struct.unpack('>I', size_data)[0]
                        filename = file_info.get('filename', 'unknown_file')
                        sender = file_info.get('sender', 'Unknown')
                        
                        filedata = b''
                        remaining = expected_size
                        
                        while remaining > 0:
                            chunk_size = min(4096, remaining)
                            chunk = self.client_socket.recv(chunk_size)
                            if not chunk:
                                break
                            filedata += chunk
                            remaining -= len(chunk)
                        
                        if len(filedata) == expected_size:
                            safe_filename = os.path.basename(filename)
                            filepath = os.path.join(self.downloads_dir, safe_filename)
                            
                            counter = 1
                            base_name, ext = os.path.splitext(safe_filename)
                            while os.path.exists(filepath):
                                filepath = os.path.join(self.downloads_dir, f"{base_name}_{counter}{ext}")
                                counter += 1
                            
                            with open(filepath, 'wb') as f:
                                f.write(filedata)
                            
                            self.root.after(0, lambda: self.display_system_message(
                                f"📎 File received: {filename} from {sender}"))
                        
                    except Exception as e:
                        print(f"File receive error: {e}")
                    finally:
                        file_receiving_mode = False
                        file_info = {}
                    continue
                
                data = self.client_socket.recv(1024).decode('utf-8')
                if not data:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Disconnected", "Connection to server lost"))
                    break
                
                buffer += data
                
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    try:
                        message = json.loads(line)
                        self.handle_message(message)
                        
                        if message.get("type") == "file_incoming":
                            file_receiving_mode = True
                            file_info = {
                                'filename': message.get('filename'),
                                'filesize': message.get('filesize'),
                                'sender': message.get('sender')
                            }
                    
                    except json.JSONDecodeError:
                        print(f"Invalid JSON: {line}")
            
            except Exception as e:
                print(f"Receive error: {e}")
                break
    
    def handle_message(self, message):
        """Handle incoming messages from server"""
        msg_type = message.get("type")
        payload = message.get("payload")
        
        if msg_type == "login_success":
            self.root.after(0, lambda: self.display_system_message(payload))
        
        elif msg_type == "error":
            self.root.after(0, lambda: messagebox.showerror("Error", payload))
        
        elif msg_type == "notification":
            self.root.after(0, lambda: self.display_system_message(f"ℹ️ {payload}"))
            # If it's a join approval notification, refresh room list
            if "approved" in payload.lower() and "join" in payload.lower():
                self.root.after(100, self.list_rooms)
        
        elif msg_type == "message":
            sender = message.get("sender", "Unknown")
            self.root.after(0, lambda: self.display_message(sender, payload, sent=False))
        
        elif msg_type == "private_message":
            sender = message.get("sender", "Unknown")
            self.root.after(0, lambda: self.display_message(f"{sender} (private)", payload, sent=False))
        
        elif msg_type == "private_sent":
            target = message.get("target", "Unknown")
            # Already displayed when sending, just confirm
            pass
        
        elif msg_type == "user_list":
            self.active_users = payload
            if self.current_tab == "users":
                self.root.after(0, self.update_sidebar_list)
        
        elif msg_type == "room_list":
            self.rooms = payload
            if self.current_tab == "rooms":
                self.root.after(0, self.update_sidebar_list)
        
        elif msg_type == "room_info":
            room_data = payload
            self.current_room = room_data['room']
            self.root.after(0, lambda: self.display_system_message(
                f"📍 Current room: {self.current_room}"))
        
        elif msg_type == "join_request":
            request_data = payload
            requester = request_data.get('user')
            room = request_data.get('room')
            self.root.after(0, lambda: self.show_join_request(requester, room))
        
        elif msg_type == "room_details":
            self.root.after(0, lambda: self.show_room_details(payload))
        
        elif msg_type == "file_sent_confirm":
            self.root.after(0, lambda: self.display_system_message(f"✅ {payload}"))
        
        elif msg_type == "call_incoming":
            caller = payload
            self.call_partner = caller
            self.root.after(0, lambda: self.show_call_notification(caller))
        
        elif msg_type == "call_ringing":
            self.root.after(0, lambda: self.display_system_message(f"📞 {payload}"))
        
        elif msg_type == "call_started":
            partner = payload
            self.call_partner = partner
            self.root.after(0, lambda: self.display_system_message(f"📞 Call connected with {partner}"))
            if PYAUDIO_AVAILABLE:
                self.root.after(0, self.start_voice_call)
            # Update UI if we're on that user's chat, or switch to it
            if self.selected_chat != partner or self.chat_type != "user":
                self.root.after(0, lambda: self.select_user(partner))
            else:
                self.root.after(0, lambda: self.update_call_ui(calling=True))
        
        elif msg_type == "call_rejected":
            self.call_partner = ""
            self.root.after(0, lambda: self.display_system_message(f"❌ {payload}"))
            self.root.after(0, lambda: self.update_call_ui(calling=False))
        
        elif msg_type == "call_ended":
            self.root.after(0, lambda: self.display_system_message(f"📞 {payload}"))
            self.root.after(0, self.stop_voice_call)
            partner = self.call_partner
            self.call_partner = ""
            # Update UI if we're on that user's chat
            if self.selected_chat == partner and self.chat_type == "user":
                self.root.after(0, lambda: self.update_call_ui(calling=False))
    
    def show_join_request(self, requester, room):
        """Show join request notification"""
        response = messagebox.askyesno("Join Request",
                                      f"{requester} wants to join '{room}'.\n\nApprove?")
        
        if response:
            msg_dict = {
                "type": "approve_user",
                "payload": {"user": requester, "room": room}
            }
        else:
            msg_dict = {
                "type": "reject_user",
                "payload": {"user": requester, "room": room}
            }
        
        self.send_json(msg_dict)
    
    def show_room_details(self, details):
        """Show detailed room information"""
        room = details.get('room')
        owner = details.get('owner')
        members = details.get('members', [])
        current_users = details.get('current_users', [])
        pending = details.get('pending_requests', [])
        
        # Create custom dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Room Details - {room}")
        dialog.geometry("500x400")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        
        tk.Label(dialog, text=f"🏠 {room}", font=("Segoe UI", 18, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=15)
        
        info_frame = tk.Frame(dialog, bg=self.sidebar_bg)
        info_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        tk.Label(info_frame, text=f"Owner: {owner}", font=("Segoe UI", 12),
                bg=self.sidebar_bg, fg=self.text_color, anchor='w').pack(fill='x', pady=5)
        
        tk.Label(info_frame, text=f"\nMembers ({len(members)}):", font=("Segoe UI", 12, "bold"),
                bg=self.sidebar_bg, fg=self.text_color, anchor='w').pack(fill='x', pady=5)
        
        members_text = scrolledtext.ScrolledText(info_frame, height=5, font=("Segoe UI", 10),
                                                 bg=self.input_bg, fg=self.text_color, relief='flat')
        members_text.pack(fill='x', pady=5)
        members_text.insert('1.0', ', '.join(members) if members else 'No members')
        members_text.config(state='disabled')
        
        tk.Label(info_frame, text=f"\nCurrently Online ({len(current_users)}):", font=("Segoe UI", 12, "bold"),
                bg=self.sidebar_bg, fg=self.text_color, anchor='w').pack(fill='x', pady=5)
        
        online_text = scrolledtext.ScrolledText(info_frame, height=3, font=("Segoe UI", 10),
                                                bg=self.input_bg, fg=self.text_color, relief='flat')
        online_text.pack(fill='x', pady=5)
        online_text.insert('1.0', ', '.join(current_users) if current_users else 'No one online')
        online_text.config(state='disabled')
        
        if pending:
            tk.Label(info_frame, text=f"\nPending Requests ({len(pending)}):", font=("Segoe UI", 12, "bold"),
                    bg=self.sidebar_bg, fg="#ffa500", anchor='w').pack(fill='x', pady=5)
            
            pending_text = scrolledtext.ScrolledText(info_frame, height=2, font=("Segoe UI", 10),
                                                     bg=self.input_bg, fg=self.text_color, relief='flat')
            pending_text.pack(fill='x', pady=5)
            pending_text.insert('1.0', ', '.join(pending))
            pending_text.config(state='disabled')
            
            # Add approve/reject buttons if owner
            if owner == self.username and pending:
                btn_frame = tk.Frame(info_frame, bg=self.sidebar_bg)
                btn_frame.pack(pady=10)
                
                for user in pending:
                    user_frame = tk.Frame(btn_frame, bg=self.input_bg)
                    user_frame.pack(fill='x', pady=2)
                    
                    tk.Label(user_frame, text=user, font=("Segoe UI", 10),
                            bg=self.input_bg, fg=self.text_color).pack(side='left', padx=10, pady=5)
                    
                    tk.Button(user_frame, text="✅", font=("Segoe UI", 10),
                             bg=self.accent_color, fg="white", relief='flat',
                             cursor="hand2",
                             command=lambda u=user: self.approve_request(u, room, dialog)).pack(side='right', padx=2)
                    
                    tk.Button(user_frame, text="❌", font=("Segoe UI", 10),
                             bg="#dc3545", fg="white", relief='flat',
                             cursor="hand2",
                             command=lambda u=user: self.reject_request(u, room, dialog)).pack(side='right', padx=2)
        
        tk.Button(dialog, text="Close", font=("Segoe UI", 11),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=dialog.destroy, padx=30, pady=8).pack(pady=15)
    
    def approve_request(self, user, room, dialog):
        """Approve a join request"""
        msg_dict = {
            "type": "approve_user",
            "payload": {"user": user, "room": room}
        }
        self.send_json(msg_dict)
        dialog.destroy()
        # Refresh room info
        import time
        time.sleep(0.2)
        self.show_room_info()
    
    def reject_request(self, user, room, dialog):
        """Reject a join request"""
        msg_dict = {
            "type": "reject_user",
            "payload": {"user": user, "room": room}
        }
        self.send_json(msg_dict)
        dialog.destroy()
    
    def show_call_notification(self, caller):
        """Show incoming call notification"""
        if not PYAUDIO_AVAILABLE:
            messagebox.showinfo("Call", f"{caller} is calling, but PyAudio is not installed.")
            msg_dict = {"type": "call_reject", "payload": caller}
            self.send_json(msg_dict)
            return
        
        # Create custom dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Incoming Call")
        dialog.geometry("350x200")
        dialog.configure(bg=self.sidebar_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="📞 Incoming Call", font=("Segoe UI", 18, "bold"),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=20)
        
        tk.Label(dialog, text=f"{caller} is calling you", font=("Segoe UI", 14),
                bg=self.sidebar_bg, fg=self.text_color).pack(pady=10)
        
        button_frame = tk.Frame(dialog, bg=self.sidebar_bg)
        button_frame.pack(pady=20)
        
        def accept():
            msg_dict = {"type": "call_accept", "payload": caller}
            self.send_json(msg_dict)
            dialog.destroy()
        
        def reject():
            msg_dict = {"type": "call_reject", "payload": caller}
            self.send_json(msg_dict)
            self.call_partner = ""
            dialog.destroy()
        
        tk.Button(button_frame, text="✅ Accept", font=("Segoe UI", 12, "bold"),
                 bg=self.accent_color, fg="white", relief='flat',
                 cursor="hand2", command=accept, padx=20, pady=10).pack(side='left', padx=10)
        
        tk.Button(button_frame, text="❌ Reject", font=("Segoe UI", 12, "bold"),
                 bg="#dc3545", fg="white", relief='flat',
                 cursor="hand2", command=reject, padx=20, pady=10).pack(side='left', padx=10)
    
    def disconnect(self):
        """Disconnect from server"""
        if messagebox.askyesno("Disconnect", "Are you sure you want to disconnect?"):
            # Stop any active call
            self.stop_voice_call()
            
            # Clean up PyAudio
            if self.p_audio:
                try:
                    self.p_audio.terminate()
                except:
                    pass
            
            # Close sockets
            try:
                if self.client_socket:
                    self.client_socket.close()
            except:
                pass
            try:
                if self.udp_socket:
                    self.udp_socket.close()
            except:
                pass
            
            self.root.quit()
    
    def on_closing(self):
        """Handle window closing"""
        self.disconnect()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
