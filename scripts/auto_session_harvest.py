#!/usr/bin/env python3
"""
auto_session_harvest.py
=======================
批量自动化：登录 ChatGPT → 收邮件验证码 → 获取 Session JSON → 写入数据库

流程：
  1. 用 Playwright 打开 chatgpt.com 登录页
  2. 输入邮箱，触发 OpenAI 发送 6 位验证码邮件
  3. 用 Cloudflare Temp Email Admin API 查询收件箱拿验证码
     API: {GPTMAIL_BASE}/admin/mails?address={email}
     Auth: x-admin-auth: {ADMIN_AUTH}
     (配置自动从项目 config.yaml 读取)
  4. 填入验证码完成登录
  5. 访问 https://chatgpt.com/api/auth/session 取 JSON
  6. 提取 accessToken + email → 写入 data/data.db

用法：
  cd ~/openai-cpa
  .venv/bin/pip install playwright httpx -q
  .venv/bin/playwright install chromium

  .venv/bin/python scripts/auto_session_harvest.py           # 内置账号
  .venv/bin/python scripts/auto_session_harvest.py --accounts accounts.txt
  .venv/bin/python scripts/auto_session_harvest.py --headless
  .venv/bin/python scripts/auto_session_harvest.py --only lqwrk938@mail.fzd-fans.com
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
import argparse
import httpx
from datetime import datetime
from typing import Optional

# ──────────────────────────────────────────────
# 路径 & 配置（直接读 config.yaml 保持与项目一致）
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "data", "data.db")

_cfg_path = os.path.join(BASE_DIR, "data", "config.yaml")
if not os.path.exists(_cfg_path):
    _cfg_path = os.path.join(BASE_DIR, "config.yaml")

def _load_yaml_cfg():
    try:
        import yaml
        with open(_cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

_yaml = _load_yaml_cfg()
GPTMAIL_BASE  = (_yaml.get("gptmail_base") or "https://emailbot.kkjusdoit.workers.dev").rstrip("/")
ADMIN_AUTH    = _yaml.get("admin_auth") or "fzd-admin-2026"
MAIL_DOMAIN   = (_yaml.get("mail_domains") or "mail.fzd-fans.com").split(",")[0].strip()
DEFAULT_PROXY = _yaml.get("default_proxy") or None

# ── 行为参数 ──
HEADLESS           = False   # 命令行 --headless 会覆盖
INTER_DELAY_SEC    = 5       # 账号间隔（秒）
EMAIL_POLL_TIMEOUT = 90      # 最多等待验证码的秒数
EMAIL_POLL_INTERVAL= 4       # 轮询间隔（秒）
BROWSER_TIMEOUT_MS = 30_000  # 页面操作超时（毫秒）

# ──────────────────────────────────────────────
# 内置账号列表（也可 --accounts 文件覆盖）
# ──────────────────────────────────────────────
BUILTIN_ACCOUNTS = """
lqwrk938@mail.fzd-fans.com----Takeover_NoPassword
lphhx870@mail.fzd-fans.com----3yUw#@ZF$AHDab2CklwI
fwnjw046@mail.fzd-fans.com----Takeover_NoPassword
gjrpx195@mail.fzd-fans.com----Takeover_NoPassword
qhtfa584@mail.fzd-fans.com----Takeover_NoPassword
ddnoa323@mail.fzd-fans.com----4cy7&mR5uAV4Llz#4drZ
wmvqh485@mail.fzd-fans.com----Lee%5q5wsOfJtt&4NXg*
xtdjs148@mail.fzd-fans.com----bquI&BWy!z%mz5J*AV6h
xadck285@mail.fzd-fans.com----wU!*2qp3#QmssSydt@0p
lqlgo964@mail.fzd-fans.com----k$&wws00tT!q6xyS8rVb
huyin686@mail.fzd-fans.com----K0KKx0F#TY6Yi%7tPei#
gluso038@mail.fzd-fans.com----x#qh8t6mR%kbCp&2Rgws
telis290@mail.fzd-fans.com----iY2$3%Zva7Fvhf#1t3e@
tergy737@mail.fzd-fans.com----bh4kV5KY&wj*WCFUlzw3
mnrsq151@mail.fzd-fans.com----jIO80k!9x0CvPE%@q4CX
xfmyf990@mail.fzd-fans.com----$UL3&TQXc5kbyPU&nVWU
fkpao773@mail.fzd-fans.com----UO&#2JzbE3N2*3&v6TO0
pqhfc724@mail.fzd-fans.com----xZd$!AwXr&88B2#$qHfk
aepet692@mail.fzd-fans.com----li1lp&0#2Y7KCfH&Leso
hhcff619@mail.fzd-fans.com----4MQh*qVj78wl#B23Eq6j
secvx224@mail.fzd-fans.com----H4XI0t$mNqxp0v*OebaF
xpvcf739@mail.fzd-fans.com----4ynax%iCs2rh!BUJ7%Rj
slyhn209@mail.fzd-fans.com----jizJA0r*7ckj9D6lUg*q
""".strip()


# ══════════════════════════════════════════════
# 1. 邮件 API：拿验证码
# ══════════════════════════════════════════════
def _extract_otp_from_text(text: str) -> Optional[str]:
    """从邮件正文提取 6 位数字 OTP"""
    patterns = [
        r"enter this code[:\s]+(\d{6})",
        r"verification code to continue[:\s]+(\d{6})",
        r"Your (?:ChatGPT|OpenAI) code is[:\s]+(\d{6})",
        r"Your login code is[:\s]+(\d{6})",
        r"\b(\d{6})\b",  # 最宽泛兜底
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            code = m.group(1)
            # 排除明显是年份 / 端口号的数字
            if not re.match(r"^(19|20)\d{2}$", code):
                return code
    return None


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ")


def _parse_cf_mail_body(raw_mail: dict) -> str:
    """解析 cloudflare_temp_email 返回的单封邮件结构，拼接出纯文本
    API 返回的字段名是 'raw'（不是 'message'）
    """
    # CF temp email admin API 返回 'raw' 字段（标准 MIME）
    raw = raw_mail.get("raw", "") or raw_mail.get("message", "") or ""

    # 提取 Subject 行
    subj_m = re.search(r"^Subject:\s*(.+)$", raw, re.I | re.M)
    subject = subj_m.group(1).strip() if subj_m else ""

    # 尝试找 text/plain 部分
    text_match = re.search(
        r"Content-Type:\s*text/plain[^\n]*\n(?:.*\n)*?\n([\s\S]+?)(?=\n--|\Z)",
        raw, re.I
    )
    body = text_match.group(1).strip() if text_match else ""

    # 若 text/plain 没拿到，找 text/html
    if not body:
        html_match = re.search(
            r"Content-Type:\s*text/html[^\n]*\n(?:.*\n)*?\n([\s\S]+?)(?=\n--|\Z)",
            raw, re.I
        )
        if html_match:
            body = _strip_html(html_match.group(1))

    # 实在没有就把整个 raw 当正文
    if not body:
        body = _strip_html(raw)

    return f"{subject}\n{body}"


def _make_http_client() -> "httpx.Client":
    """创建带代理的 httpx 客户端（Cloudflare Workers API 需要走代理才能访问）"""
    proxy = DEFAULT_PROXY or None
    try:
        return httpx.Client(proxy=proxy, verify=False, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return httpx.Client(verify=False, timeout=15)


def _get_known_ids(email: str) -> set:
    """预先拉取已有邮件 ID，避免捡到旧验证码"""
    known: set = set()
    try:
        with _make_http_client() as cli:
            r = cli.get(
                f"{GPTMAIL_BASE}/admin/mails",
                params={"limit": 50, "offset": 0, "address": email},
                headers={"x-admin-auth": ADMIN_AUTH}
            )
            if r.status_code == 200:
                for m in r.json().get("results", []):
                    if m.get("id"):
                        known.add(m["id"])
    except Exception as e:
        print(f"    [⚠] 预取邮件 ID 失败: {e}")
    return known


def fetch_otp_from_cf_email(email: str, known_ids: set, timeout: int = EMAIL_POLL_TIMEOUT) -> Optional[str]:
    """
    轮询 Cloudflare Temp Email Admin API，等待来自 OpenAI 的验证码邮件。
    API: GET {GPTMAIL_BASE}/admin/mails?limit=20&offset=0&address={email}
    Auth header: x-admin-auth: {ADMIN_AUTH}
    邮件内容在 'raw' 字段（标准 MIME 格式）
    """
    deadline = time.time() + timeout
    attempt  = 0

    with _make_http_client() as cli:
        while time.time() < deadline:
            attempt += 1
            try:
                r = cli.get(
                    f"{GPTMAIL_BASE}/admin/mails",
                    params={"limit": 20, "offset": 0, "address": email},
                    headers={"x-admin-auth": ADMIN_AUTH}
                )
                if r.status_code != 200:
                    print(f"    [⚠] 邮件 API 返回 {r.status_code}")
                    time.sleep(EMAIL_POLL_INTERVAL)
                    continue

                data  = r.json()
                mails = data.get("results", [])
                for mail in mails:
                    mail_id = mail.get("id")
                    if not mail_id or mail_id in known_ids:
                        continue

                    # raw 是标准 MIME 邮件
                    raw_msg  = mail.get("raw", "") or mail.get("message", "") or ""
                    sender_m = re.search(r"^From:\s*(.+)$", raw_msg, re.I | re.M)
                    sender   = sender_m.group(1).lower() if sender_m else ""
                    subj_m   = re.search(r"^Subject:\s*(.+)$", raw_msg, re.I | re.M)
                    subject  = subj_m.group(1) if subj_m else ""

                    # 只处理 OpenAI/ChatGPT 发来的邮件
                    if ("openai" not in sender and
                            "openai" not in subject.lower() and
                            "chatgpt" not in subject.lower()):
                        known_ids.add(mail_id)
                        continue

                    # 解析邮件正文并提取 OTP
                    body = _parse_cf_mail_body(mail)
                    code = _extract_otp_from_text(body)

                    if code:
                        known_ids.add(mail_id)
                        print(f"    [✓] 验证码到达: {code}  (from: {sender or 'n/a'}, attempt {attempt})")
                        return code
                    else:
                        known_ids.add(mail_id)  # 有 OpenAI 邮件但无验证码，跳过

            except Exception as e:
                print(f"    [⚠] 邮件 API 查询异常: {e}")

            remaining = int(deadline - time.time())
            print(f"    [⏳] 等待验证码... ({remaining}s 剩余)", end="\r", flush=True)
            time.sleep(EMAIL_POLL_INTERVAL)

    print()
    return None



# ══════════════════════════════════════════════
# 2. 数据库写入
# ══════════════════════════════════════════════
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password TEXT,
                token_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_to_db(email: str, password: str, session_data: dict) -> str:
    """写入 token，返回 'inserted'/'updated'/'error:...'"""
    at = session_data.get("accessToken", "")
    user = session_data.get("user") or {}
    token_json = json.dumps({
        "email": email,
        "name":  user.get("name", ""),
        "picture": user.get("image", "") or user.get("picture", ""),
        "access_token":  at,
        "id_token":      at,
        "refresh_token": "",
        "type":   "session_json_import",
        "source": "auto_session_harvest",
        "harvested_at": datetime.now().isoformat(),
    }, ensure_ascii=False)

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, password FROM accounts WHERE LOWER(TRIM(email))=LOWER(TRIM(?))",
                (email,)
            )
            row = cur.fetchone()
            if row:
                orig_pwd = row[1] or ""
                cur.execute("UPDATE accounts SET token_data=?, password=? WHERE email=?",
                            (token_json, orig_pwd or password, email))
                res = "updated"
            else:
                cur.execute("INSERT INTO accounts (email, password, token_data) VALUES (?,?,?)",
                            (email, password, token_json))
                res = "inserted"

        # 对接 chatgpt2api 项目
        try:
            sys.path.append(BASE_DIR)
            from utils.db_manager import sync_token_to_chatgpt2api
            sync_token_to_chatgpt2api(email, at)
        except Exception as sync_err:
            print(f"    [⚠] 对接 chatgpt2api 失败: {sync_err}")

        return res
    except Exception as e:
        return f"error: {e}"


# ══════════════════════════════════════════════
# 3. Playwright 核心：登录 + 取 session
# ══════════════════════════════════════════════
async def harvest_one(email: str, password: str, context) -> dict:
    """
    完整流程：
      登录页 → 输入邮箱 → (密码 或 等验证码) → 拿 /api/auth/session JSON → 存库
    """
    result = {"email": email, "status": "failed", "db": "", "message": ""}
    page = await context.new_page()

    # 预抓现有邮件 ID（用 _get_known_ids 走 httpx+proxy），避免捡到旧验证码
    known_ids: set = await asyncio.to_thread(_get_known_ids, email)
    print(f"  [i] 已有 {len(known_ids)} 封旧邮件，将忽略")


    try:
        # ── Step 1: 打开登录页 ──
        print(f"  [1] 打开登录页...")
        await page.goto("https://chatgpt.com/auth/login",
                        wait_until="domcontentloaded",
                        timeout=BROWSER_TIMEOUT_MS)
        await asyncio.sleep(3)

        # ── Step 2: 输入邮箱 ──
        print(f"  [2] 输入邮箱...")
        email_input = page.locator(
            "input[name='email'], input[type='email'], "
            "input[name='username'], input[id*='email']"
        ).first
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(email)
        await asyncio.sleep(0.5)

        # 直接按回车提交（避免误点“Continue with Google”等社交登录按钮）
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)

        # ── Step 3: 密码 or 验证码 ──
        is_no_pwd = password.strip().upper() == "TAKEOVER_NOPASSWORD"

        if not is_no_pwd:
            # 有密码账号：填密码
            print(f"  [3] 填写密码...")
            try:
                pwd_input = page.locator(
                    "input[name='password'], input[type='password']"
                ).first
                await pwd_input.wait_for(state="visible", timeout=10000)
                await pwd_input.fill(password)
                await asyncio.sleep(0.5)
                try:
                    sub = page.locator(
                        "button[type='submit'], button:has-text('Continue'), "
                        "button:has-text('Sign in'), button:has-text('Log in')"
                    ).first
                    await sub.click(timeout=5000)
                except Exception:
                    await page.keyboard.press("Enter")
                await asyncio.sleep(3)

                # 密码账号也可能触发 email verification
                # 判断是否出现验证码输入框
                otp_visible = await page.locator(
                    "input[name='code'], input[maxlength='6'], "
                    "input[autocomplete='one-time-code']"
                ).count() > 0

                if otp_visible:
                    print(f"  [3b] 密码登录也触发了邮件验证码，等待收信...")
                    is_no_pwd = True  # 走验证码流程
            except Exception as e:
                result["message"] = f"密码填写失败: {e}"
                return result

        if is_no_pwd:
            # 等待并填写验证码
            print(f"  [3] 等待邮件验证码 (最多 {EMAIL_POLL_TIMEOUT}s)...")
            otp = await asyncio.to_thread(
                fetch_otp_from_cf_email, email, known_ids, EMAIL_POLL_TIMEOUT
            )
            if not otp:
                result["message"] = "超时未收到验证码邮件"
                return result

            # 填入验证码
            print(f"  [4] 填入验证码 {otp}...")
            try:
                code_input = page.locator(
                    "input[name='code'], input[maxlength='6'], "
                    "input[autocomplete='one-time-code'], "
                    "input[type='text']:near(button, 200)"
                ).first
                await code_input.wait_for(state="visible", timeout=12000)
                await code_input.fill(otp)
                await asyncio.sleep(0.5)
                try:
                    sub = page.locator(
                        "button[type='submit'], "
                        "button:has-text('Continue'), "
                        "button:has-text('Verify')"
                    ).first
                    await sub.click(timeout=5000)
                except Exception:
                    await page.keyboard.press("Enter")
            except Exception as e:
                result["message"] = f"验证码填写失败: {e}"
                return result
            await asyncio.sleep(3)

        # ── Step 4: 等待跳转到 chatgpt.com 主页 ──
        print(f"  [5] 等待登录完成...")
        try:
            await page.wait_for_url(
                re.compile(r"chatgpt\.com(?!/auth)"),
                timeout=20000
            )
        except Exception:
            cur_url = page.url
            if "chatgpt.com" not in cur_url:
                result["message"] = f"登录后页面跳转异常: {cur_url}"
                return result

        await asyncio.sleep(2)

        # ── Step 5: 访问 session API ──
        print(f"  [6] 访问 /api/auth/session...")
        await page.goto("https://chatgpt.com/api/auth/session",
                        wait_until="networkidle",
                        timeout=20000)
        await asyncio.sleep(1.5)

        body_text = (await page.inner_text("body")).strip()
        if not body_text or body_text in ("{}", "null", ""):
            result["message"] = "session 返回空，可能未登录成功"
            return result

        try:
            session_data = json.loads(body_text)
        except Exception:
            result["message"] = f"session JSON 解析失败: {body_text[:200]}"
            return result

        access_token = session_data.get("accessToken", "")
        if not access_token:
            result["message"] = f"session 中无 accessToken: {body_text[:200]}"
            return result

        # ── Step 6: 写入数据库 ──
        db_result = save_to_db(email, "" if is_no_pwd else password, session_data)
        result.update({"status": "success", "db": db_result,
                       "message": f"token={access_token[:20]}..."})
        print(f"  [✓] 成功！DB: {db_result}  token: {access_token[:30]}...")

    except asyncio.TimeoutError:
        result["message"] = "操作超时"
        try:
            scr_path = f"/tmp/harvest_failed_{email.split('@')[0]}.png"
            await page.screenshot(path=scr_path)
            print(f"  [!] 操作超时，截图已保存至 {scr_path}")
        except Exception:
            pass
    except Exception as e:
        import traceback
        result["message"] = f"异常: {e}\n{traceback.format_exc()[-400:]}"
        try:
            scr_path = f"/tmp/harvest_failed_{email.split('@')[0]}.png"
            await page.screenshot(path=scr_path)
            print(f"  [!] 发生异常，截图已保存至 {scr_path}")
        except Exception:
            pass
    finally:
        # 如果不是成功状态且没有主动截图，做个兜底截图
        if result["status"] != "success":
            try:
                scr_path = f"/tmp/harvest_failed_{email.split('@')[0]}.png"
                await page.screenshot(path=scr_path)
            except Exception:
                pass
        await page.close()

    return result


# ══════════════════════════════════════════════
# 4. 主运行循环
# ══════════════════════════════════════════════
async def run_all(accounts: list[tuple[str, str]]):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[✗] 未安装 playwright，请运行：")
        print("    .venv/bin/pip install playwright")
        print("    .venv/bin/playwright install chromium")
        sys.exit(1)

    init_db()
    results = []

    async with async_playwright() as pw:
        launch_kwargs = {
            "headless": HEADLESS,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ]
        }
        if DEFAULT_PROXY:
            launch_kwargs["proxy"] = {"server": DEFAULT_PROXY}
            print(f"  [i] 浏览器启动代理: {DEFAULT_PROXY}")

        browser = await pw.chromium.launch(**launch_kwargs)
        # 每个账号复用同一 browser，但每次用新 context（独立 cookie）
        for idx, (email, password) in enumerate(accounts):
            print(f"\n{'─'*55}")
            print(f"  [{idx+1}/{len(accounts)}] {email}")
            print(f"{'─'*55}")

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )

            result = await harvest_one(email, password, context)
            results.append(result)

            await context.close()

            if idx < len(accounts) - 1:
                print(f"\n  ⏸  等待 {INTER_DELAY_SEC}s 再处理下一个账号...")
                await asyncio.sleep(INTER_DELAY_SEC)

        await browser.close()

    # ── 汇总 ──
    ok  = [r for r in results if r["status"] == "success"]
    err = [r for r in results if r["status"] != "success"]

    print(f"\n{'═'*55}")
    print(f"  采集完成  成功: {len(ok)}  失败: {len(err)}")
    print(f"  数据库: {DB_PATH}")
    if err:
        print(f"\n  失败明细:")
        for r in err:
            print(f"    ✗ {r['email']}")
            print(f"      {r['message'][:120]}")
    print(f"{'═'*55}")
    return results


# ══════════════════════════════════════════════
# 5. 入口
# ══════════════════════════════════════════════
def parse_accounts_text(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("----", 1)
        if len(parts) == 2 and "@" in parts[0]:
            out.append((parts[0].strip(), parts[1].strip()))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ChatGPT 批量 Session 采集工具 (Cloudflare email + Playwright)"
    )
    ap.add_argument("--accounts", "-a", default=None,
                    help="账号文件路径，格式: email----password，每行一条。不传则用脚本内置列表")
    ap.add_argument("--headless", action="store_true",
                    help="无头模式（不显示浏览器窗口）")
    ap.add_argument("--only", default=None,
                    help="只处理指定邮箱（逗号分隔多个）")
    ap.add_argument("--delay", type=int, default=INTER_DELAY_SEC,
                    help=f"账号间隔秒数（默认 {INTER_DELAY_SEC}）")
    args = ap.parse_args()

    HEADLESS        = args.headless
    INTER_DELAY_SEC = args.delay

    # 读账号
    if args.accounts:
        if not os.path.exists(args.accounts):
            print(f"[✗] 文件不存在: {args.accounts}"); sys.exit(1)
        with open(args.accounts, encoding="utf-8") as f:
            all_accounts = parse_accounts_text(f.read())
    else:
        all_accounts = parse_accounts_text(BUILTIN_ACCOUNTS)

    # 过滤 --only
    if args.only:
        only_set = {e.strip().lower() for e in args.only.split(",")}
        all_accounts = [(e, p) for e, p in all_accounts if e.lower() in only_set]

    if not all_accounts:
        print("[✗] 没有可处理的账号"); sys.exit(1)

    print(f"{'═'*55}")
    print(f"  ChatGPT Session 自动采集")
    print(f"  账号数: {len(all_accounts)}")
    print(f"  邮件API: {GPTMAIL_BASE}")
    print(f"  Admin Auth: {ADMIN_AUTH}")
    print(f"  数据库: {DB_PATH}")
    print(f"  无头模式: {HEADLESS}")
    print(f"{'═'*55}")

    asyncio.run(run_all(all_accounts))
