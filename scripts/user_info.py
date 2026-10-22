import argparse
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import Config
from app.security import username_key


def format_time(value):
    if value is None:
        return "未知"
    return value.astimezone(ZoneInfo("Asia/Shanghai")).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


def main():
    parser = argparse.ArgumentParser(
        description="查看 MongoForm 用户的注册时间"
    )
    parser.add_argument(
        "username",
        nargs="?",
        help="用户名；省略时列出全部用户",
    )
    args = parser.parse_args()

    client = MongoClient(Config.MONGODB_URI, tz_aware=True)
    try:
        database = client.get_default_database()
        query = (
            {"usernameKey": username_key(args.username)}
            if args.username
            else {}
        )
        users = list(
            database.users.find(
                query,
                {"username": 1, "createdAt": 1},
            ).sort("createdAt", 1)
        )
        if not users:
            print("未找到匹配用户")
            raise SystemExit(1)

        print(f"数据库：{database.name}")
        for user in users:
            print(f"{user['username']}\t{format_time(user.get('createdAt'))}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
