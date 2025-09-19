# 🚢 Ship Proxy System

## 📖 Overview
This project implements the **Ship Proxy System** as described in *The ship.pdf*.  
The system reduces satellite internet costs by using a **single persistent TCP connection** between the ship (client proxy) and an offshore proxy (server).

- All HTTP/HTTPS requests from clients onboard the ship go through the **ship proxy**.  
- The ship proxy sends requests sequentially through one TCP connection to the **offshore server**.  
- The offshore server forwards requests to the actual internet and sends responses back.  

---

## ✨ Features
- Single persistent TCP connection (ship → offshore).  
- Configurable as a standard HTTP/HTTPS proxy (works with browsers & curl).  
- **Sequential request handling** (FIFO).  
- Supports all HTTP methods: GET, POST, PUT, DELETE, PATCH, OPTIONS, etc.  
- Supports HTTPS **CONNECT tunneling**.  
- Fully **Dockerized** client and server.  

---

## 📂 Project Structure
ship-proxy-system/
│
├── client/
│ ├── client.py
│ └── Dockerfile
│
├── server/
│ ├── server.py
│ └── Dockerfile
│
└── README.md


---

## 🐳 Docker Setup

### 1. Build Images
```bash
# Build offshore server image
docker build -t ship-proxy-server ./server

# Build ship proxy client image
docker build -t ship-proxy-client ./client
```
### 2. Run Containers

Start the offshore server:
```bash
docker run -d --name proxy-server -p 9999:9999 ship-proxy-server
```

Start the ship proxy client:
```bash
docker run -d --name proxy-client -p 8080:8080 --link proxy-server ship-proxy-client
```
## 🧪 Testing
### HTTP Test
```bash
curl -x http://localhost:8080 http://httpforever.com/
```

Expected output:

<html>
Server is up and running.
</html>

### HTTPS Test
```bash
curl -x http://localhost:8080 https://example.com/
```

Expected output: full HTML page of Example Domain.

### Sequential Requests
```bash
curl -x http://localhost:8080 http://httpforever.com/ &
curl -x http://localhost:8080 http://httpforever.com/ &
curl -x http://localhost:8080 http://httpforever.com/ &
wait
```

All requests succeed and are processed one after another.

## ⚙️ Configuration

Client listen port: 8080 (exposed in Docker).

Offshore server port: 9999 (exposed in Docker).

Can be modified in client.py and server.py if needed.
