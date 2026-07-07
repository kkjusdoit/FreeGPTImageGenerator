import sqlite3
import pymysql
import json
import os
from typing import Any
from utils.config import DB_TYPE, MYSQL_CFG
from utils import config as cfg

os.makedirs("data", exist_ok=True)
DB_PATH = "data/data.db"


def classify_token_payload(token_payload: Any) -> dict:
    """Classify local inventory records for UI and CPA eligibility checks."""
    details = {
        "status": "未知",
        "account_type": "unknown",
        "cpa_eligible": False,
        "maintenance_ready": False,
    }

    if isinstance(token_payload, str):
        try:
            token_payload = json.loads(token_payload)
        except Exception:
            token_payload = None

    if not isinstance(token_payload, dict):
        return details

    if token_payload.get("status") == "仅注册成功":
        details.update({
            "status": "仅注册成功",
            "account_type": "reg_only",
        })
        return details

    has_id = bool(str(token_payload.get("id_token", "")).strip())
    has_access = bool(str(token_payload.get("access_token", "")).strip())
    has_refresh = bool(str(token_payload.get("refresh_token", "")).strip())

    if has_id and has_access:
        details.update({
            "status": "有凭证",
            "account_type": "credential",
            "cpa_eligible": True,
            "maintenance_ready": has_refresh,
        })
    elif has_refresh:
        details.update({
            "status": "待刷新",
            "account_type": "credential",
            "cpa_eligible": False,
            "maintenance_ready": True,
        })
    elif has_id or has_access:
        details.update({
            "status": "凭证不全",
            "account_type": "credential",
            "cpa_eligible": False,
            "maintenance_ready": False,
        })

    return details


class get_db_conn:
    """抹平 SQLite 和 MySQL 连接差异"""
    def __init__(self, as_dict=False):
        self.as_dict = as_dict

    def __enter__(self):
        if DB_TYPE == "mysql":
            self.conn = pymysql.connect(
                host=MYSQL_CFG.get('host', '127.0.0.1'),
                port=MYSQL_CFG.get('port', 3306),
                user=MYSQL_CFG.get('user', 'root'),
                password=MYSQL_CFG.get('password', ''),
                database=MYSQL_CFG.get('db_name', 'wenfxl_manager'),
                charset='utf8mb4'
            )
        else:
            self.conn = sqlite3.connect(DB_PATH, timeout=10)
            if self.as_dict:
                self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def get_cursor(conn, as_dict=False):
    """获取适配的游标"""
    if DB_TYPE == "mysql" and as_dict:
        return conn.cursor(pymysql.cursors.DictCursor)
    return conn.cursor()


def execute_sql(cursor, sql: str, params=()):
    if DB_TYPE == "mysql":
        sql = sql.replace('?', '%s')
        sql = sql.replace('AUTOINCREMENT', 'AUTO_INCREMENT')

        sql = sql.replace('INSERT OR IGNORE', 'INSERT IGNORE')
        sql = sql.replace('INSERT OR REPLACE', 'REPLACE')

        sql = sql.replace('TEXT UNIQUE', 'VARCHAR(191) UNIQUE')
        sql = sql.replace('TEXT PRIMARY KEY', 'VARCHAR(191) PRIMARY KEY')

        # 3. 抹平特殊的 PRAGMA
        if 'PRAGMA' in sql:
            return None

    return cursor.execute(sql, params)

def init_db():
    """初始化数据库，自动适应双引擎建表"""
    with get_db_conn() as conn:
        c = get_cursor(conn)
        execute_sql(c, 'PRAGMA journal_mode=WAL;')
        execute_sql(c, 'PRAGMA synchronous=NORMAL;')

        execute_sql(c, '''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password TEXT,
                token_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        execute_sql(c, '''
            CREATE TABLE IF NOT EXISTS system_kv (
                `key` TEXT PRIMARY KEY, 
                value TEXT
            )
        ''')
        execute_sql(c, '''
            CREATE TABLE IF NOT EXISTS local_mailboxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password TEXT,
                client_id TEXT,
                refresh_token TEXT,
                status INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        try:
            execute_sql(c, 'ALTER TABLE local_mailboxes ADD COLUMN fission_count INTEGER DEFAULT 0;')
            execute_sql(c, 'ALTER TABLE local_mailboxes ADD COLUMN retry_master INTEGER DEFAULT 0;')
        except Exception:
            pass
    print(f"[{cfg.ts()}] [系统] 数据库模块初始化完成 (引擎: {DB_TYPE.upper()})")


def sync_token_to_chatgpt2api(email: str, access_token: str):
    """
    无缝对接 chatgpt2api 项目：
    1. 尝试通过 http://localhost:8000/api/accounts API 导入 token
    2. 若 API 连不上，直接修改 /Users/linkunkun/Documents/TempTry/chatgpt2api/data/accounts.json
    """
    import json
    import os

    api_url = "http://localhost:8000/api/accounts"
    auth_key = "chatgpt2api"
    json_path = "/Users/linkunkun/Documents/TempTry/chatgpt2api/data/accounts.json"

    # 1. 尝试 API 导入
    try:
        import httpx
        with httpx.Client(timeout=3) as client:
            r = client.post(
                api_url,
                headers={"Authorization": auth_key},
                json={"tokens": [access_token]}
            )
            if r.status_code in (200, 201):
                print(f"[{cfg.ts()}] [Sync] 成功通过 API 将账号 {email} 同步到 chatgpt2api 项目")
                return True
    except Exception:
        pass

    # 2. 尝试文件直接写入
    if os.path.exists(os.path.dirname(json_path)):
        try:
            accounts = []
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        accounts = json.load(f)
                except Exception:
                    accounts = []
            if not isinstance(accounts, list):
                accounts = []

            # 检查是否已存在
            found = False
            for acc in accounts:
                if acc.get("email") == email or acc.get("access_token") == access_token:
                    acc["access_token"] = access_token
                    acc["email"] = email
                    acc["status"] = "正常"
                    found = True
                    break

            if not found:
                new_acc = {
                    "access_token": access_token,
                    "type": "Free",
                    "status": "正常",
                    "quota": 8,
                    "email": email,
                    "user_id": None,
                    "limits_progress": [
                        {"feature_name": "deep_research", "remaining": 5, "reset_after": None},
                        {"feature_name": "file_upload", "remaining": 5, "reset_after": None},
                        {"feature_name": "paste_text_to_file", "remaining": 3, "reset_after": None},
                        {"feature_name": "image_gen", "remaining": 8, "reset_after": None}
                    ],
                    "default_model_slug": "auto",
                    "restore_at": None,
                    "success": 0,
                    "fail": 0,
                    "last_used_at": None
                }
                accounts.append(new_acc)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=2, ensure_ascii=False)
            print(f"[{cfg.ts()}] [Sync] 成功直接写入文件将账号 {email} 同步到 chatgpt2api 项目")
            return True
        except Exception as e:
            print(f"[{cfg.ts()}] [Sync] 写入 chatgpt2api 配置文件失败: {e}")

    return False


def save_account_to_db(email: str, password: str, token_json_str: str) -> bool:
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, '''
                INSERT OR REPLACE INTO accounts (email, password, token_data)
                VALUES (?, ?, ?)
            ''', (email, password, token_json_str))
            
        # 成功保存到数据库后，自动触发同步到 chatgpt2api 项目
        try:
            token_payload = json.loads(token_json_str) if isinstance(token_json_str, str) else token_json_str
            if isinstance(token_payload, dict):
                access_token = token_payload.get("access_token") or token_payload.get("accessToken")
                if access_token:
                    sync_token_to_chatgpt2api(email, access_token)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 数据库保存失败: {e}")
        return False


def get_all_accounts() -> list:
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT email, password, created_at FROM accounts ORDER BY id DESC")
            rows = c.fetchall()
            # MySQL 默认游标返回的也是元组，兼容原版切片逻辑
            return [{"email": r[0], "password": r[1], "created_at": r[2]} for r in rows]
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 获取账号列表失败: {e}")
        return []


def get_token_by_email(email: str) -> dict:
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT token_data FROM accounts WHERE email = ?", (email,))
            row = c.fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 读取 Token 失败: {e}")
        return None


def get_tokens_by_emails(emails: list) -> list:
    if not emails: return []
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            placeholders = ','.join(['?'] * len(emails))
            execute_sql(c, f"SELECT token_data FROM accounts WHERE email IN ({placeholders})", tuple(emails))
            rows = c.fetchall()

            export_list = []
            for r in rows:
                if r[0]:
                    try:
                        export_list.append(json.loads(r[0]))
                    except:
                        pass
            return export_list
    except Exception as e:
        return []


def delete_accounts_by_emails(emails: list) -> bool:
    if not emails: return True
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            placeholders = ','.join(['?'] * len(emails))
            execute_sql(c, f"DELETE FROM accounts WHERE email IN ({placeholders})", tuple(emails))
            return True
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 数据库批量删除账号异常: {e}")
        return False


def get_accounts_page(page: int = 1, page_size: int = 50, hide_reg: str = "0", account_filter: str = "all") -> dict:
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT email, password, created_at, token_data FROM accounts ORDER BY id DESC")
            rows = c.fetchall()

            data = []
            for r in rows:
                classified = classify_token_payload(r[3])
                item = {
                    "email": r[0],
                    "password": r[1],
                    "created_at": r[2],
                    **classified,
                }
                data.append(item)

            if hide_reg == "1":
                data = [item for item in data if item["account_type"] != "reg_only"]

            if account_filter == "credential":
                data = [item for item in data if item["account_type"] == "credential"]
            elif account_filter == "reg_only":
                data = [item for item in data if item["account_type"] == "reg_only"]

            total = len(data)
            offset = (page - 1) * page_size
            data = data[offset: offset + page_size]
            return {"total": total, "data": data}
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 分页获取账号列表失败: {e}")
        return {"total": 0, "data": []}


def set_sys_kv(key: str, value: Any):
    try:
        val_str = json.dumps(value, ensure_ascii=False)
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "INSERT OR REPLACE INTO system_kv (`key`, value) VALUES (?, ?)", (key, val_str))
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 系统配置保存失败: {e}")


def get_sys_kv(key: str, default=None):
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT value FROM system_kv WHERE `key` = ?", (key,))
            row = c.fetchone()
            if row:
                return json.loads(row[0])
    except Exception:
        pass
    return default


def get_all_accounts_with_token(limit: int = 10000) -> list:
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT email, password, token_data FROM accounts ORDER BY id DESC LIMIT ?", (limit,))
            rows = c.fetchall()
            return [{"email": r[0], "password": r[1], "token_data": r[2]} for r in rows]
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 提取完整账号数据失败: {e}")
        return []


def import_local_mailboxes(mailboxes_data: list) -> int:
    count = 0
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            for mb in mailboxes_data:
                try:
                    execute_sql(c, '''
                        INSERT OR IGNORE INTO local_mailboxes (email, password, client_id, refresh_token, status)
                        VALUES (?, ?, ?, ?, 0)
                    ''', (mb['email'], mb['password'], mb.get('client_id', ''), mb.get('refresh_token', '')))
                    if c.rowcount > 0:
                        count += 1
                except:
                    pass
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 导入邮箱库失败: {e}")
    return count


def import_authorized_accounts(accounts_data: list) -> tuple[int, int]:
    inserted = 0
    updated = 0
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            for acc in accounts_data:
                email = str(acc.get("email", "")).strip().lower()
                if not email:
                    continue
                password = str(acc.get("password", "")).strip()
                token_json = json.dumps({
                    "email": email,
                    "client_id": str(acc.get("client_id", "")).strip(),
                    "refresh_token": str(acc.get("refresh_token", "")).strip(),
                    "access_token": "",
                    "id_token": "",
                    "type": "authorized_import",
                    "source": "manual_authorized_import",
                }, ensure_ascii=False)

                execute_sql(c, "SELECT id FROM accounts WHERE email = ?", (email,))
                existing = c.fetchone()
                if existing:
                    execute_sql(c, "UPDATE accounts SET password = ?, token_data = ? WHERE email = ?", (password, token_json, email))
                    updated += 1
                else:
                    execute_sql(c, "INSERT INTO accounts (email, password, token_data) VALUES (?, ?, ?)", (email, password, token_json))
                    inserted += 1
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 导入授权账号失败: {e}")
    return inserted, updated


def get_local_mailboxes_page(page: int = 1, page_size: int = 50) -> dict:
    try:
        # as_dict=True 通知游标返回字典格式，适配原来的 sqlite3.Row
        with get_db_conn(as_dict=True) as conn:
            c = get_cursor(conn, as_dict=True)
            execute_sql(c, "SELECT COUNT(1) AS cnt FROM local_mailboxes")
            total_row = c.fetchone()
            total = total_row['cnt'] if DB_TYPE == "mysql" else total_row[0]

            offset = (page - 1) * page_size
            execute_sql(c, "SELECT * FROM local_mailboxes ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
            rows = c.fetchall()
            return {"total": total, "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"total": 0, "data": []}


def delete_local_mailboxes(ids: list) -> bool:
    if not ids: return True
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            placeholders = ','.join(['?'] * len(ids))
            execute_sql(c, f"DELETE FROM local_mailboxes WHERE id IN ({placeholders})", tuple(ids))
            return True
    except Exception as e:
        return False

def get_and_lock_unused_local_mailbox() -> dict:
    """提取一个未使用的账号，并状态锁定为占用中"""
    try:
        with get_db_conn(as_dict=True) as conn:
            c = get_cursor(conn, as_dict=True)

            filter_sql = """
                            SELECT * FROM local_mailboxes m
                            WHERE status = 0 
                            AND NOT EXISTS (
                                SELECT 1 FROM accounts a WHERE TRIM(LOWER(a.email)) = TRIM(LOWER(m.email))
                            )
                            ORDER BY id ASC LIMIT 1
                        """

            if DB_TYPE == "mysql":
                execute_sql(c, "START TRANSACTION")
                execute_sql(c, filter_sql + " FOR UPDATE")
            else:
                execute_sql(c, "BEGIN EXCLUSIVE")
                execute_sql(c, filter_sql)

            row = c.fetchone()
            if row:
                execute_sql(c, "UPDATE local_mailboxes SET status = 1 WHERE id = ?", (row['id'],))
                return dict(row)
            return None
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] 提取本地邮箱失败: {e}")
        return None


def get_mailbox_for_pool_fission() -> dict:
    """带重试优先级的并发取号"""
    try:
        with get_db_conn(as_dict=True) as conn:
            c = get_cursor(conn, as_dict=True)
            if DB_TYPE == "mysql":
                execute_sql(c, "START TRANSACTION")
                execute_sql(c, "SELECT * FROM local_mailboxes WHERE status = 0 AND retry_master = 1 AND email NOT IN (SELECT email FROM accounts) LIMIT 1 FOR UPDATE")
            else:
                execute_sql(c, "BEGIN EXCLUSIVE")
                execute_sql(c, "SELECT * FROM local_mailboxes WHERE status = 0 AND retry_master = 1 AND email NOT IN (SELECT email FROM accounts) LIMIT 1")

            row = c.fetchone()

            if not row:
                if DB_TYPE == "mysql":
                    execute_sql(c, "SELECT * FROM local_mailboxes WHERE status = 0 ORDER BY fission_count ASC LIMIT 1 FOR UPDATE")
                else:
                    execute_sql(c, "SELECT * FROM local_mailboxes WHERE status = 0 ORDER BY fission_count ASC LIMIT 1")
                row = c.fetchone()

            if row:
                execute_sql(c, "UPDATE local_mailboxes SET fission_count = fission_count + 1 WHERE id = ?",
                            (row['id'],))
                return dict(row)
            return None
    except Exception as e:
        print(f"[{cfg.ts()}] [DB_ERROR] 提取失败: {e}")
        return None


def update_local_mailbox_status(email: str, status: int):
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "UPDATE local_mailboxes SET status = ? WHERE email = ?", (status, email))
    except Exception:
        pass

def update_local_mailbox_refresh_token(email: str, new_rt: str):
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "UPDATE local_mailboxes SET refresh_token = ? WHERE email = ?", (new_rt, email))
    except Exception:
        pass


def update_pool_fission_result(email: str, is_blocked: bool, is_raw: bool):
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            if not is_blocked:
                execute_sql(c, "UPDATE local_mailboxes SET retry_master = 0 WHERE email = ?", (email,))
            else:
                if not is_raw:
                    execute_sql(c, "UPDATE local_mailboxes SET retry_master = 1 WHERE email = ?", (email,))
                else:
                    execute_sql(c, "UPDATE local_mailboxes SET status = 3, retry_master = 0 WHERE email = ?", (email,))
    except Exception as e:
        print(f"[{cfg.ts()}] [DB_ERROR] 结果更新失败: {e}")

def clear_retry_master_status(email: str):
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "UPDATE local_mailboxes SET retry_master = 0 WHERE email = ?", (email,))
    except Exception as e:
        print(f"[{ts()}] [DB_ERROR] 清除 {email} 的 retry_master 状态失败: {e}")

def get_all_accounts_raw() -> list:
    """获取账号库所有原始数据"""
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT email, password, token_data FROM accounts ORDER BY id DESC")
            rows = c.fetchall()
            return [{"email": r[0], "password": r[1], "token_data": json.loads(r[2]) if r[2] else {}} for r in rows]
    except: return []

def check_account_exists(email: str) -> bool:
    """检查指定邮箱是否已经在本地账号库中"""
    if not email: return False
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "SELECT 1 FROM accounts WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))", (email,))
            return c.fetchone() is not None
    except Exception as e:
        print(f"[{cfg.ts()}] [DB_ERROR] 查重失败: {e}")
        return False

def clear_all_accounts() -> bool:
    """一键清空账号库"""
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "DELETE FROM accounts")
            return True
    except: return False

def get_all_mailboxes_raw() -> list:
    """获取邮箱库所有原始数据"""
    try:
        with get_db_conn(as_dict=True) as conn:
            c = get_cursor(conn, as_dict=True)
            execute_sql(c, "SELECT * FROM local_mailboxes ORDER BY id DESC")
            return [dict(r) for r in c.fetchall()]
    except: return []

def clear_all_mailboxes() -> bool:
    """一键清空邮箱库"""
    try:
        with get_db_conn() as conn:
            c = get_cursor(conn)
            execute_sql(c, "DELETE FROM local_mailboxes")
            return True
    except: return False
