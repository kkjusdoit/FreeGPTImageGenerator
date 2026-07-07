#!/usr/bin/env python3
"""
从已登录的 Chrome 浏览器抓取 OpenAI 账号 Token 并导入 openai-cpa 数据库。

用法：
  cd ~/openai-cpa && .venv/bin/python scripts/extract_tokens.py

前提：
  1. Chrome 已打开并登录了 OpenAI 账号 (chat.openai.com)
  2. Chrome 需要开启远程调试端口（脚本会自动处理）
"""

import json
import sqlite3
import sys
import time
import urllib.request
import subprocess
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "data.db")
CHROME_DEBUG_PORT = 9222
OPENAI_ORIGIN = "https://chatgpt.com"

def get_chrome_ws_url():
    """连接 Chrome DevTools Protocol"""
    try:
        url = f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("webSocketDebuggerUrl")
    except Exception:
        return None

def launch_chrome_debug():
    """启动带调试端口的 Chrome"""
    import platform
    system = platform.system()
    
    if system == "Darwin":
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        chrome_paths = ["google-chrome", "chromium-browser", "chromium"]
    
    for chrome in chrome_paths:
        if os.path.exists(chrome) or shutil_which(chrome):
            profile_dir = os.path.expanduser(f"~/.openai-cpa-chrome-debug")
            os.makedirs(profile_dir, exist_ok=True)
            cmd = [
                chrome,
                f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            print(f"[*] 启动 Chrome 调试模式: {chrome}")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            return True
    return False

def shutil_which(name):
    """简易 which"""
    for p in os.environ.get("PATH", "").split(":"):
        fp = os.path.join(p, name)
        if os.path.exists(fp):
            return fp
    return None

def get_cookies_via_cdp(ws_url):
    """通过 CDP 获取所有 cookies"""
    try:
        import websocket
    except ImportError:
        print("[*] 安装 websocket-client...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
        import websocket
    
    ws = websocket.create_connection(ws_url, timeout=10)
    
    # 获取所有 cookies
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    result = json.loads(ws.recv())
    ws.close()
    
    return result.get("result", {}).get("cookies", [])

def extract_session_token(cookies):
    """从 cookies 中提取 OpenAI session token"""
    session_tokens = []
    for cookie in cookies:
        domain = cookie.get("domain", "")
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        
        # 匹配 OpenAI session token
        if ("chatgpt.com" in domain or "openai.com" in domain) and \
           "__Secure-next-auth.session-token" in name:
            session_tokens.append({
                "domain": domain,
                "token": value,
                "expires": cookie.get("expires", 0),
            })
    
    return session_tokens

def token_to_jwt_data(session_token):
    """将 session token 转换为可用的 token_data"""
    # session token 本身就是 base64 编码的 JWT
    # 解析 payload 获取邮箱等信息
    try:
        parts = session_token.split(".")
        if len(parts) >= 2:
            # 添加 padding
            payload = parts[1]
            payload += "=" * (4 - len(payload) % 4)
            import base64
            claims = json.loads(base64.urlsafe_b64decode(payload))
            
            email = claims.get("email", "")
            
            # 构造 token_data
            token_data = {
                "id_token": session_token,
                "access_token": "",
                "refresh_token": "",
                "email": email,
                "type": "browser_extracted",
            }
            return token_data, email
    except Exception as e:
        print(f"[!] 解析 JWT 失败: {e}")
    
    return {"id_token": session_token, "type": "browser_extracted"}, ""

def refresh_via_openai_api(session_token):
    """用 session token 调用 OpenAPI API 刷新获取完整 token"""
    try:
        # 调用 OpenAI session API
        url = "https://chatgpt.com/api/auth/session"
        req = urllib.request.Request(url, headers={
            "Cookie": f"__Secure-next-auth.session-token={session_token}",
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            
            access_token = data.get("accessToken", "")
            user = data.get("user", {})
            email = user.get("email", "")
            
            return {
                "id_token": session_token,
                "access_token": access_token,
                "refresh_token": "",
                "email": email,
                "name": user.get("name", ""),
                "picture": user.get("image", ""),
                "type": "browser_extracted",
            }, email
    except Exception as e:
        print(f"[!] 刷新 token 失败: {e}")
    
    return None, ""

def import_to_db(accounts):
    """导入账号到数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    imported = 0
    skipped = 0
    
    for acc in accounts:
        email = acc["email"]
        token_data = json.dumps(acc["token_data"], ensure_ascii=False)
        
        # 检查是否已存在
        c.execute("SELECT id FROM accounts WHERE email = ?", (email,))
        if c.fetchone():
            # 更新已有记录
            c.execute("UPDATE accounts SET token_data = ? WHERE email = ?", (token_data, email))
            print(f"  [更新] {email}")
            imported += 1
        else:
            c.execute(
                "INSERT INTO accounts (email, password, token_data) VALUES (?, ?, ?)",
                (email, "", token_data)
            )
            print(f"  [新增] {email}")
            imported += 1
    
    conn.commit()
    conn.close()
    return imported, skipped

def main():
    print("=" * 50)
    print("  OpenAI Token 采集器")
    print("=" * 50)
    
    # 1. 检查 Chrome 调试连接
    ws_url = get_chrome_ws_url()
    if not ws_url:
        print("[*] Chrome 调试端口未开启，尝试自动启动...")
        if not launch_chrome_debug():
            print("[✗] 无法启动 Chrome，请手动开启：")
            print("    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
            sys.exit(1)
        ws_url = get_chrome_ws_url()
        if not ws_url:
            print("[✗] Chrome 调试连接失败")
            sys.exit(1)
    
    print(f"[✓] Chrome 调试连接成功")
    
    # 2. 获取 cookies
    print("[*] 正在扫描 cookies...")
    cookies = get_cookies_via_cdp(ws_url)
    print(f"[*] 共发现 {len(cookies)} 个 cookie")
    
    # 3. 提取 session tokens
    session_tokens = extract_session_token(cookies)
    print(f"[✓] 找到 {len(session_tokens)} 个 OpenAI session token")
    
    if not session_tokens:
        print("[!] 未找到 OpenAI 登录 token")
        print("    请确保在 Chrome 中打开了 chatgpt.com 并已登录")
        sys.exit(0)
    
    # 4. 刷新获取完整信息
    accounts = []
    for st in session_tokens:
        print(f"[*] 处理: {st['domain']}...")
        
        # 先尝试 API 刷新
        token_data, email = refresh_via_openai_api(st["token"])
        
        if not token_data or not email:
            # 回退到 JWT 解析
            token_data, email = token_to_jwt_data(st["token"])
        
        if email:
            accounts.append({
                "email": email,
                "token_data": token_data,
            })
            print(f"  [✓] {email}")
        else:
            print(f"  [!] 无法提取邮箱，跳过")
    
    if not accounts:
        print("[!] 没有有效账号可导入")
        sys.exit(0)
    
    # 5. 导入数据库
    print(f"\n[*] 导入 {len(accounts)} 个账号到数据库...")
    imported, skipped = import_to_db(accounts)
    
    print(f"\n{'=' * 50}")
    print(f"  完成！导入: {imported}，跳过: {skipped}")
    print(f"  数据库: {DB_PATH}")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
