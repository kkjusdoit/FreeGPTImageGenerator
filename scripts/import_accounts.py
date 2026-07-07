#!/usr/bin/env python3
"""
从浏览器导出的 JSON 批量导入到 openai-cpa 数据库。

用法：
  # 单个导入（粘贴 JSON）
  cd ~/openai-cpa && .venv/bin/python scripts/import_accounts.py '{"email":"xxx",...}'

  # 批量导入（从文件，每行一个 JSON）
  cd ~/openai-cpa && .venv/bin/python scripts/import_accounts.py -f accounts.txt

  # 从剪贴板导入（macOS）
  cd ~/openai-cpa && .venv/bin/python scripts/import_accounts.py -c

  # 交互模式（粘贴多个，空行结束）
  cd ~/openai-cpa && .venv/bin/python scripts/import_accounts.py -i
"""

import json
import sqlite3
import sys
import os
import subprocess

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "data.db")


def parse_token(raw: dict) -> tuple:
    """解析各种格式的 token，返回 (email, token_data_json)"""
    email = raw.get("email", "")
    id_token = raw.get("id_token", "")
    access_token = raw.get("access_token", id_token)  # 如果没有 access_token 用 id_token
    refresh_token = raw.get("refresh_token", "")

    if not email and id_token:
        # 从 JWT 解析邮箱
        try:
            import base64
            parts = id_token.split(".")
            if len(parts) >= 2:
                payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload))
                email = claims.get("https://api.openai.com/profile", {}).get("email", "") or claims.get("email", "")
        except:
            pass

    token_data = {
        "email": email,
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "type": raw.get("type", "imported"),
    }

    return email, json.dumps(token_data, ensure_ascii=False)


def import_one(raw: dict, conn) -> str:
    """导入单个账号，返回状态字符串"""
    email, token_data = parse_token(raw)
    if not email:
        return "❌ 无法提取邮箱，跳过"

    c = conn.cursor()
    c.execute("SELECT id FROM accounts WHERE email = ?", (email,))
    if c.fetchone():
        c.execute("UPDATE accounts SET token_data = ? WHERE email = ?", (token_data, email))
        conn.commit()
        return f"✅ 更新: {email}"
    else:
        c.execute("INSERT INTO accounts (email, password, token_data) VALUES (?, ?, ?)", (email, "", token_data))
        conn.commit()
        return f"✅ 新增: {email}"


def import_from_clipboard(conn):
    """从 macOS 剪贴板读取"""
    try:
        raw = subprocess.check_output(["pbpaste"], text=True).strip()
        data = json.loads(raw)
        if isinstance(data, list):
            for item in data:
                print(import_one(item, conn))
        else:
            print(import_one(data, conn))
    except json.JSONDecodeError:
        print("❌ 剪贴板内容不是有效 JSON")
    except Exception as e:
        print(f"❌ 错误: {e}")


def import_interactive(conn):
    """交互模式：粘贴多个 JSON，空行结束"""
    print("=" * 50)
    print("  交互导入模式")
    print("  粘贴 JSON，每条回车，空行结束")
    print("=" * 50)
    print()

    while True:
        try:
            line = input("粘贴 JSON > ").strip()
            if not line:
                break
            data = json.loads(line)
            print(import_one(data, conn))
        except json.JSONDecodeError:
            print("❌ 无效 JSON，重新粘贴")
        except KeyboardInterrupt:
            break

    print("\n完成！")


def import_from_file(path, conn):
    """从文件导入（每行一个 JSON）"""
    with open(path, "r") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                print(f"[{i}] {import_one(data, conn)}")
            except json.JSONDecodeError:
                print(f"[{i}] ❌ 无效 JSON，跳过")


def show_all(conn):
    """显示库中所有账号"""
    c = conn.cursor()
    c.execute("SELECT email, substr(token_data,1,40) FROM accounts ORDER BY id DESC")
    rows = c.fetchall()
    print(f"\n当前库中共 {len(rows)} 个账号：")
    for r in rows:
        print(f"  • {r[0]}")


def main():
    conn = sqlite3.connect(DB_PATH)
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        show_all(conn)
        conn.close()
        return

    if args[0] == "-c":
        import_from_clipboard(conn)
    elif args[0] == "-i":
        import_interactive(conn)
    elif args[0] == "-f" and len(args) >= 2:
        import_from_file(args[1], conn)
    elif args[0] == "-l":
        show_all(conn)
    else:
        # 直接传 JSON 字符串
        raw_json = " ".join(args)
        try:
            data = json.loads(raw_json)
            if isinstance(data, list):
                for item in data:
                    print(import_one(item, conn))
            else:
                print(import_one(data, conn))
        except json.JSONDecodeError:
            print("❌ 无效 JSON")

    show_all(conn)
    conn.close()


if __name__ == "__main__":
    main()
