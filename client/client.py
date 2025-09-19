import socket
import threading
import queue
from http.server import BaseHTTPRequestHandler, HTTPServer

OFFSHORE_HOST = "localhost"
OFFSHORE_PORT = 9999
LISTEN_PORT = 8080   # expose 8080 as per assignment

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        more = sock.recv(length - len(data))
        if not more:
            raise ConnectionError("Socket closed prematurely")
        data += more
    return data

def read_message(sock):
    header = recv_all(sock, 5)
    length = int.from_bytes(header[:4], "big")
    msg_type = header[4]
    payload = recv_all(sock, length)
    return msg_type, payload

def send_message(sock, msg_type, payload):
    header = len(payload).to_bytes(4, "big") + msg_type.to_bytes(1, "big")
    sock.sendall(header + payload)

# --- Persistent connection to offshore server ---
tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.connect((OFFSHORE_HOST, OFFSHORE_PORT))
print(f"[client] Connected to offshore {OFFSHORE_HOST}:{OFFSHORE_PORT}")

tcp_lock = threading.Lock()
job_queue = queue.Queue()

class ProxyJob:
    def __init__(self, raw_request, handler, is_connect=False):
        self.raw_request = raw_request
        self.handler = handler
        self.is_connect = is_connect
        self.event = threading.Event()
        self.response = b""
        self.error = None

def worker():
    while True:
        job = job_queue.get()
        try:
            with tcp_lock:
                send_message(tcp_sock, 0, job.raw_request)

                if job.is_connect:
                    # Expect a framed HTTP/1.1 200 from offshore
                    msg_type, payload = read_message(tcp_sock)
                    if msg_type != 1:
                        job.error = "Bad CONNECT response"
                        job.event.set()
                        continue

                    # Write raw 200 response directly back to curl/browser
                    job.handler.connection.sendall(payload)
                    print("[client] CONNECT established, tunneling started")

                    # Start tunneling raw bytes
                    def forward(src, dst):
                        try:
                            while True:
                                data = src.recv(4096)
                                if not data:
                                    break
                                dst.sendall(data)
                        except: 
                            pass

                    t1 = threading.Thread(target=forward, args=(job.handler.connection, tcp_sock), daemon=True)
                    t2 = threading.Thread(target=forward, args=(tcp_sock, job.handler.connection), daemon=True)
                    t1.start(); t2.start()
                    t1.join(); t2.join()
                    print("[client] CONNECT tunnel closed")

                    job.event.set()

                else:
                    # Normal HTTP
                    msg_type, payload = read_message(tcp_sock)
                    if msg_type == 1:
                        job.response = payload
                    else:
                        job.error = "Bad response type"
                    job.event.set()

        except Exception as e:
            job.error = str(e)
            job.event.set()
        finally:
            job_queue.task_done()

# Start worker thread
threading.Thread(target=worker, daemon=True).start()

class ProxyHandler(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        raw_request = f"{self.command} {self.path} {self.request_version}\r\n".encode() + \
                      f"Host: {self.path}\r\n\r\n".encode()
        job = ProxyJob(raw_request, self, is_connect=True)
        job_queue.put(job)
        job.event.wait()
        return

    def forward_request(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        request_line = self.requestline + "\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        raw_request = (request_line + headers + "\r\n").encode("iso-8859-1") + body

        job = ProxyJob(raw_request, self, is_connect=False)
        job_queue.put(job)
        job.event.wait()
        if job.error:
            self.send_error(502, job.error)
        else:
            self.connection.sendall(job.response)

    def do_GET(self): self.forward_request()
    def do_POST(self): self.forward_request()
    def do_PUT(self): self.forward_request()
    def do_DELETE(self): self.forward_request()
    def do_HEAD(self): self.forward_request()
    def do_OPTIONS(self): self.forward_request()
    def do_PATCH(self): self.forward_request()

def run():
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    print(f"[client] Ship proxy listening on port {LISTEN_PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()


