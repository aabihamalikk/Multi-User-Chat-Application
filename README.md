# Multi-User-Chat-Application
This project is a high-performance, real-time communication platform built using Python’s socket library. It facilitates multi-user text chat, private messaging, dynamic room management, binary file transfers, and low-latency voice calling.The system utilizes a hybrid networking model, employing TCP for reliable message delivery and UDP for real-time voice data streaming.
2. System Architecture
The application follows a Client-Server Architecture:
•	Centralized Server: Acts as a traffic controller, managing user states, room permissions, and relaying data between clients.
•	GUI Client: A thread-safe Tkinter application that allows users to interact with the server through a modern, dark-themed interface.
Network Protocols:
•	TCP (Port 5555): Used for "Control Signals"—Login, text messages, room management, and file transfer headers. This ensures no data loss for critical information.
•	UDP (Port 5556): Used for "Voice Streaming"—Low-latency transmission of audio packets. Since voice data is time-sensitive, UDP is preferred over TCP to prevent lag.
3. Core Functionalities
1.	Advanced User Management
•	Unique Identity: Users login with a unique username. The server prevents duplicate logins.
•	Presence Tracking: The server broadcasts an "Active Users" list to all clients whenever someone joins or leaves.
2.	Dynamic Room & Group Chat
•	Public Lobby: Every user starts in a default "Lobby" room.
•	Private Rooms: Users can create custom rooms. The creator is assigned Owner status.
•	Isolation: Messages sent in one room are only visible to members of that specific room.
•	Permission System: Owners can:
o	Approve or Reject join requests.
o	Manually add users to a room.
o	Kick users from a room.
3.	Private Messaging
•	Users can select an individual from the "Users" tab to initiate a secure one-on-one chat, bypassing the public rooms.


4.	Header-Body File Transfer Protocol
•	The project implements a custom protocol to handle binary data:
•	JSON Header: Contains metadata (filename, size, target).
•	Binary Size Packet: A 4-byte packed integer representing the file size.
•	Data Chunks: The file is sent in 4KB chunks to maintain stability.
•	Support: Supports private file transfers, room-wide file sharing, and global broadcasts.
•	Auto-Save: The client automatically saves files into a downloads/ folder, handling name collisions by appending numbers (e.g., image_1.png).
5.	Real-Time Voice Calling (VoIP)
•	Audio Capture: Uses the PyAudio library to capture microphone input.
•	UDP Relay: The server receives audio packets prefixed with the sender's identity and intelligently routes them to the call partner.
•	Threaded Processing: Separate threads for capturing and playing audio ensure the GUI remains responsive during a call.
4. Technical Implementation Details
Server-Side Logic
•	Concurrency: Utilizes the threading module to handle hundreds of simultaneous connections. Each client is assigned a dedicated thread.
•	Thread Safety: Employs threading.Lock() on critical resources like the clients dictionary and rooms list to prevent data corruption.
•	JSON Serialization: All control messages are sent as JSON objects for easy extensibility and structured data handling.
Client-Side Logic
•	GUI Architecture: Built with Tkinter, using a WhatsApp-inspired dark mode theme with custom message bubbles.
•	State Management: The client tracks current_room and selected_chat to ensure the UI updates dynamically.
•	Asynchronous Receiving: A background thread constantly listens for server updates so that incoming messages don't freeze the user interface.

6.	How to Run
•	Dependencies: Install PyAudio: pip install pyaudio.
•	Start Server: Run python server.py.
•	Start Clients: Run python client.py (multiple instances allowed).
7.	Conclusion & Future Enhancements
This project successfully demonstrates the power of Python sockets in building complex, multi-modal communication tools.
Future Improvements:
•	End-to-End Encryption: Using RSA/AES to secure messages and files.
•	Database Integration: Using SQLite or PostgreSQL to store chat history and user accounts.
•	Media Support: Implementing image previews within the chat window.

