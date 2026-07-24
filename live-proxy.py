import requests
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
# We use a service that returns the request's IP address in JSON format.
IP_CHECK_URL = "https://api.ipify.org?format=json"
# Maximum time in seconds to wait for a response from the proxy.
TIMEOUT = 10
# The number of threads to use for checking proxies concurrently.
MAX_THREADS = 100
# File to save working proxies to.
OUTPUT_FILE = "working_proxies.txt"

# --- Thread-safe counters for the summary ---
lock = threading.Lock()
working_proxies_count = 0
dead_proxies_count = 0

def get_real_ip():
    """Fetches the user's current public IP address without a proxy."""
    try:
        print("🔍 Determining your real IP address...")
        response = requests.get(IP_CHECK_URL, timeout=TIMEOUT)
        response.raise_for_status() # Raise an exception for bad status codes
        ip = response.json().get("ip")
        if ip:
            print(f"✅ Your real IP is: {ip}")
            return ip
        else:
            print("\n[!] Could not determine real IP. The IP checking service may be down.")
            return None
    except requests.RequestException as e:
        print(f"\n[!] Error fetching real IP: {e}")
        print("[!] Cannot continue without it. Please check your internet connection.")
        return None

def check_proxy(proxy_url, real_ip):
    """
    Tests a single proxy by routing a request through it and comparing the resulting IP.

    Args:
        proxy_url (str): The proxy to test, in format like 'http://ip:port'.
        real_ip (str): The user's actual public IP address for comparison.

    Returns:
        tuple: A tuple containing the proxy_url and a boolean indicating if it's working.
    """
    global working_proxies_count, dead_proxies_count

    proxy_dict = {
        "http": proxy_url,
        "https": proxy_url,
    }

    try:
        # Make the request through the proxy
        response = requests.get(IP_CHECK_URL, proxies=proxy_dict, timeout=TIMEOUT)
        response.raise_for_status()

        # Check the IP returned by the service
        proxy_ip = response.json().get("ip")

        # A proxy is only "working" if it successfully connects AND hides your real IP.
        if proxy_ip and proxy_ip != real_ip:
            with lock:
                working_proxies_count += 1
                # Green text for working, and show the new IP as proof
                print(f"\033[92m[+] Working: {proxy_url.ljust(30)} (IP: {proxy_ip})\033[0m")
            return proxy_url, True
        else:
            # This case covers transparent proxies or misconfigurations where your real IP is leaked.
            raise Exception("Proxy is transparent or not hiding IP.")

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout, requests.exceptions.SSLError,
            requests.exceptions.RequestException, Exception):
        # Any exception here means the proxy is dead or failed the test.
        with lock:
            dead_proxies_count += 1
            # Grey text for dead proxies to make them less prominent
            print(f"\033[90m[-] Dead:    {proxy_url}\033[0m")
        return proxy_url, False

def main():
    """Main function to run the proxy checker."""
    if len(sys.argv) != 2:
        print("Usage: python3 proxy_checker.py <proxy_file.txt>")
        sys.exit(1)

    # --- Step 1: Get the real IP address ---
    real_ip = get_real_ip()
    if not real_ip:
        sys.exit(1)

    # --- Step 2: Read proxies from the file ---
    proxy_file = sys.argv[1]
    try:
        with open(proxy_file, "r") as f:
            proxy_list = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Ensure the proxy URL has a scheme (e.g., http://) for requests
                if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                    proxy_list.append(f"http://{line}")
                else:
                    proxy_list.append(line)
    except FileNotFoundError:
        print(f"\n[!] Error: The file '{proxy_file}' was not found.")
        sys.exit(1)

    if not proxy_list:
        print("\n[!] Error: The proxy file is empty or contains no valid entries.")
        sys.exit(1)

    total_proxies = len(proxy_list)
    print(f"\n🚀 Starting check of {total_proxies} proxies from '{proxy_file}'...")
    print("-" * 60)

    # --- Step 3: Check proxies concurrently ---
    working_proxies = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Create a future for each proxy check, passing the real_ip for comparison
        future_to_proxy = {executor.submit(check_proxy, p, real_ip): p for p in proxy_list}

        for future in as_completed(future_to_proxy):
            proxy, is_working = future.result()
            if is_working:
                working_proxies.append(proxy)

    # --- Step 4: Print summary and save results ---
    print("-" * 60)
    print("\n✅ Check Complete. Summary:")
    print(f"  - \033[92mWorking: {working_proxies_count}\033[0m")
    print(f"  - \033[90mDead/Failed: {dead_proxies_count}\033[0m")

    if working_proxies:
        print(f"\n💾 Saving {len(working_proxies)} working proxies to '{OUTPUT_FILE}'...")
        with open(OUTPUT_FILE, "w") as f:
            for proxy in working_proxies:
                f.write(proxy + "\n")
        print("Done.")
    else:
        print("\nNo working proxies were found that could hide your IP.")

if __name__ == "__main__":
    main()
