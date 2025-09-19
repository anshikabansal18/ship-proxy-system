import socket
import threading
import http.client
import urllib.parse

HOST = "0.0.0.0"
PORT = 9999

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

def relay(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.shutdown(socket.SHUT_RD)
        except: pass
        try: dst.shutdown(socket.SHUT_WR)
        except: pass

def handle_client(conn):
    print("[server] Connection from ship proxy established.")
    try:
        while True:
            msg_type, payload = read_message(conn)
            if msg_type != 0:
                continue

            request_text = payload.decode("iso-8859-1", errors="ignore")
            first_line = request_text.split("\r\n", 1)[0]
            print(f"[server] Received: {first_line}")

            if first_line.startswith("CONNECT"):
                # HTTPS tunneling
                _, target, _ = first_line.split()
                host, port = (target.split(":") + ["443"])[:2]
                port = int(port)

                try:
                    remote = socket.create_connection((host, port))
                except Exception as e:
                    send_message(conn, 1, f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
                    continue

                send_message(conn, 1, b"HTTP/1.1 200 Connection Established\r\n\r\n")
                print(f"[server] CONNECT to {host}:{port}")

                t1 = threading.Thread(target=relay, args=(conn, remote), daemon=True)
                t2 = threading.Thread(target=relay, args=(remote, conn), daemon=True)
                t1.start(); t2.start()
                t1.join(); t2.join()
                print("[server] CONNECT tunnel closed")

            else:
                # Normal HTTP
                head, _, body_part = request_text.partition("\r\n\r\n")
                lines = head.split("\r\n")
                method, raw_path, version = lines[0].split(" ", 2)

                headers = {}
                for line in lines[1:]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip()] = v.strip()

                parsed = urllib.parse.urlsplit(raw_path)
                if parsed.scheme and parsed.netloc:
                    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query or "", ""))
                    target_host = parsed.hostname
                    target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    is_https = (parsed.scheme == "https")
                else:
                    path = raw_path
                    host_header = headers.get("Host", "")
                    target_host, target_port = (host_header.split(":") + ["80"])[:2]
                    target_port = int(target_port)
                    is_https = False

                body = body_part.encode("iso-8859-1") if body_part else b""

                try:
                    conn_out = (http.client.HTTPSConnection if is_https else http.client.HTTPConnection)(
                        target_host, target_port, timeout=20
                    )
                    hop_by_hop = ["Connection","Proxy-Connection","Keep-Alive","Transfer-Encoding",
                                  "TE","Trailer","Upgrade"]
                    headers_to_send = {k: v for k, v in headers.items() if k not in hop_by_hop}
                    conn_out.request(method, path, body=body, headers=headers_to_send)
                    resp = conn_out.getresponse()
                    resp_body = resp.read()
                except Exception as e:
                    send_message(conn, 1, f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
                    continue

                status_line = f"HTTP/1.1 {resp.status} {resp.reason}\r\n"
                headers_out = "".join(
                    f"{k}: {v}\r\n" for k, v in resp.getheaders()
                    if k not in ["Connection","Keep-Alive","Proxy-Connection","Transfer-Encoding",
                                 "TE","Trailer","Upgrade"]
                )
                if "Content-Length" not in dict(resp.getheaders()) and resp_body:
                    headers_out += f"Content-Length: {len(resp_body)}\r\n"

                response_bytes = (status_line + headers_out + "\r\n").encode("iso-8859-1") + resp_body
                send_message(conn, 1, response_bytes)
                print(f"[server] Sent {resp.status} for {method} {path}")
    except Exception as e:
        print("[server] Error:", e)
    finally:
        conn.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[server] Listening on {HOST}:{PORT}")
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    main()

