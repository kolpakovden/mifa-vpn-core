#!/usr/bin/env python3
"""MIFA VPN Core Telegram administration bot."""

import copy
import grp
import json
import logging
import os
import pwd
import random
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mifa-bot")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CONFIG_PATH = os.getenv("XRAY_CONFIG") or os.getenv("CONFIG_PATH") or "/usr/local/etc/xray/config.json"
XRAY_SERVICE = os.getenv("XRAY_SERVICE", "xray")
CFG_OWNER = os.getenv("XRAY_CFG_OWNER", "root")
CFG_GROUP = os.getenv("XRAY_CFG_GROUP", "root")
CFG_MODE = int(os.getenv("XRAY_CFG_MODE", "644"), 8)
SERVER_HOST = os.getenv("SERVER_HOST") or os.getenv("SERVER_IP") or "127.0.0.1"
PUBLIC_KEY = (os.getenv("PUBLIC_KEY") or "").strip()
SHORT_ID = (os.getenv("SHORT_ID") or "").strip()
DEFAULT_SNI = os.getenv("DEFAULT_SNI", "www.github.com")
SNI_POOL = [x.strip() for x in os.getenv("SNI_POOL", DEFAULT_SNI).split(",") if x.strip()]
XHTTP_PATH = os.getenv("XHTTP_PATH", "/").strip() or "/"
WS_PATH = os.getenv("WS_PATH", "/").strip() or "/"

_raw_admins = (os.getenv("ADMIN_IDS") or "").strip()
ADMIN_IDS: Set[int] = {int(x.strip()) for x in _raw_admins.split(",") if x.strip().lstrip("-").isdigit()}
_raw_chat = (os.getenv("ALLOWED_CHAT_ID") or "").strip()
ALLOWED_CHAT_ID = int(_raw_chat) if _raw_chat.lstrip("-").isdigit() else 0


def run(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, (p.stdout or "").strip()


def normalize_alias(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    return re.sub(r"[^A-Za-z0-9_.@-]", "", value)[:64].lower()


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write_config(cfg: Dict[str, Any]) -> None:
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    uid = pwd.getpwnam(CFG_OWNER).pw_uid
    gid = grp.getgrnam(CFG_GROUP).gr_gid
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tf:
        json.dump(cfg, tf, ensure_ascii=False, indent=2)
        tf.write("\n")
        tf.flush()
        os.fsync(tf.fileno())
        temp = tf.name
    os.chown(temp, uid, gid)
    os.chmod(temp, CFG_MODE)
    os.replace(temp, path)


def vless_inbounds(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [x for x in cfg.get("inbounds", []) if x.get("protocol") == "vless"]


def inbound_kind(ib: Dict[str, Any]) -> str:
    stream = ib.get("streamSettings", {}) or {}
    if stream.get("security") == "reality" and stream.get("network") == "tcp":
        return "reality"
    if stream.get("network") == "xhttp":
        return "xhttp"
    if stream.get("network") in ("ws", "websocket"):
        return "ws"
    return "other"


def clients(ib: Dict[str, Any]) -> List[Dict[str, Any]]:
    return ib.setdefault("settings", {}).setdefault("clients", [])


def find_user(cfg: Dict[str, Any], alias: str) -> Optional[Dict[str, Any]]:
    alias = alias.lower()
    for ib in vless_inbounds(cfg):
        for client in clients(ib):
            email = (client.get("email") or "").lower()
            base = re.sub(r"-(xhttp|ws)$", "", email)
            if email == alias or base == alias:
                return client
    return None


def reality_params(cfg: Dict[str, Any]) -> Tuple[str, str, str]:
    public_key, short_id, sni = PUBLIC_KEY, SHORT_ID, DEFAULT_SNI
    for ib in vless_inbounds(cfg):
        stream = ib.get("streamSettings", {}) or {}
        if inbound_kind(ib) != "reality":
            continue
        settings = stream.get("realitySettings", {}) or {}
        if not short_id and settings.get("shortIds"):
            short_id = settings["shortIds"][0]
        names = settings.get("serverNames") or []
        if names:
            sni = random.choice(names)
        private = settings.get("privateKey")
        if not public_key and private:
            rc, out = run(["xray", "x25519", "-i", private])
            if rc == 0:
                match = re.search(r"Public\s*(?:Key|key):\s*([A-Za-z0-9_=-]+)", out)
                if match:
                    public_key = match.group(1)
        break
    return public_key, short_id, sni


def validate_and_restart(new_cfg: Dict[str, Any], old_cfg: Dict[str, Any]) -> Tuple[bool, str]:
    atomic_write_config(new_cfg)
    rc, out = run(["xray", "run", "-test", "-config", CONFIG_PATH])
    if rc != 0:
        atomic_write_config(old_cfg)
        return False, f"Xray config test failed:\n{out}"
    rc, out = run(["systemctl", "restart", XRAY_SERVICE])
    if rc != 0:
        atomic_write_config(old_cfg)
        run(["systemctl", "restart", XRAY_SERVICE])
        return False, f"Xray restart failed; rollback completed:\n{out}"
    return True, "OK"


def reality_link(user_id: str, alias: str, port: int, cfg: Dict[str, Any]) -> str:
    pbk, sid, sni = reality_params(cfg)
    return (
        f"vless://{user_id}@{SERVER_HOST}:{port}?security=reality&sni={sni}"
        f"&fp=chrome&pbk={pbk}&sid={sid}&type=tcp&flow=xtls-rprx-vision&encryption=none"
        f"#{alias}-{port}"
    )


def xhttp_link(user_id: str, alias: str) -> str:
    path = XHTTP_PATH if XHTTP_PATH.startswith("/") else f"/{XHTTP_PATH}"
    return (
        f"vless://{user_id}@{SERVER_HOST}:443?security=tls&sni={SERVER_HOST}&fp=chrome"
        f"&type=xhttp&path={path}&mode=stream-one&encryption=none#{alias}-xhttp"
    )


def ws_link(user_id: str, alias: str) -> str:
    path = WS_PATH if WS_PATH.startswith("/") else f"/{WS_PATH}"
    return (
        f"vless://{user_id}@{SERVER_HOST}:443?security=tls&sni={SERVER_HOST}&fp=chrome"
        f"&type=ws&path={path}&encryption=none#{alias}-ws"
    )


async def allowed(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else 0
    if not ADMIN_IDS and not ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("⛔ ACL не настроен: задайте ADMIN_IDS и/или ALLOWED_CHAT_ID")
        return False
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.effective_message.reply_text("⛔ Нет доступа")
        return False
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("⛔ Нет доступа")
        return False
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    await update.effective_message.reply_text(
        "MIFA VPN Core Admin Bot\n\n"
        "/add <alias>\n/del <alias>\n/list\n/key <alias> [8443|50273|xhttp|ws|all]\n"
        "/info\n/status\n/restart"
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Использование: /add <alias>")
        return
    alias = normalize_alias(" ".join(context.args))
    if not alias:
        await update.effective_message.reply_text("❌ Некорректный alias")
        return
    old_cfg = load_config()
    if find_user(old_cfg, alias):
        await update.effective_message.reply_text(f"❌ Пользователь уже существует: {alias}")
        return
    new_cfg = copy.deepcopy(old_cfg)
    user_id = str(uuid.uuid4())
    count = 0
    for ib in vless_inbounds(new_cfg):
        kind = inbound_kind(ib)
        if kind == "reality":
            clients(ib).append({"flow": "xtls-rprx-vision", "id": user_id, "email": alias})
            count += 1
        elif kind == "xhttp":
            clients(ib).append({"id": user_id, "email": f"{alias}-xhttp"})
            count += 1
        elif kind == "ws":
            clients(ib).append({"id": user_id, "email": f"{alias}-ws"})
            count += 1
    if not count:
        await update.effective_message.reply_text("❌ Не найдены поддерживаемые VLESS inbound'ы")
        return
    ok, reason = validate_and_restart(new_cfg, old_cfg)
    if not ok:
        await update.effective_message.reply_text(f"❌ {reason}")
        return
    await update.effective_message.reply_text(f"✅ Добавлен {alias}\nUUID: {user_id}")


async def cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Использование: /del <alias>")
        return
    alias = normalize_alias(" ".join(context.args))
    old_cfg = load_config()
    new_cfg = copy.deepcopy(old_cfg)
    removed = 0
    for ib in vless_inbounds(new_cfg):
        before = len(clients(ib))
        ib["settings"]["clients"] = [
            c for c in clients(ib)
            if re.sub(r"-(xhttp|ws)$", "", (c.get("email") or "").lower()) != alias
        ]
        removed += before - len(ib["settings"]["clients"])
    if not removed:
        await update.effective_message.reply_text("❌ Пользователь не найден")
        return
    ok, reason = validate_and_restart(new_cfg, old_cfg)
    await update.effective_message.reply_text("✅ Удалён" if ok else f"❌ {reason}")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    cfg = load_config()
    names = set()
    for ib in vless_inbounds(cfg):
        for client in clients(ib):
            email = (client.get("email") or "").strip()
            if email:
                names.add(re.sub(r"-(xhttp|ws)$", "", email))
    text = "Пользователи:\n" + ("\n".join(f"• {x}" for x in sorted(names)) if names else "— пусто —")
    await update.effective_message.reply_text(text[:4000])


async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Использование: /key <alias> [8443|50273|xhttp|ws|all]")
        return
    alias = normalize_alias(context.args[0])
    transport = context.args[1].lower() if len(context.args) > 1 else "all"
    cfg = load_config()
    client = find_user(cfg, alias)
    if not client:
        await update.effective_message.reply_text("❌ Пользователь не найден")
        return
    user_id = client.get("id", "")
    links: List[str] = []
    if transport in ("8443", "all"):
        links.append(reality_link(user_id, alias, 8443, cfg))
    if transport in ("50273", "all"):
        links.append(reality_link(user_id, alias, 50273, cfg))
    if transport in ("xhttp", "all"):
        links.append(xhttp_link(user_id, alias))
    if transport in ("ws", "all"):
        links.append(ws_link(user_id, alias))
    if not links:
        await update.effective_message.reply_text("❌ Транспорт: 8443, 50273, xhttp, ws или all")
        return
    await update.effective_message.reply_text("\n\n".join(links), disable_web_page_preview=True)


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    cfg = load_config()
    pbk, sid, sni = reality_params(cfg)
    await update.effective_message.reply_text(
        f"Host: {SERVER_HOST}\nReality: 8443, 50273\nXHTTP: 443 {XHTTP_PATH}\n"
        f"WS legacy: 443 {WS_PATH}\nDefault SNI: {sni}\nPublic key: {pbk or 'n/a'}\nShort ID: {sid or 'n/a'}"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    rc, out = run(["systemctl", "is-active", XRAY_SERVICE])
    await update.effective_message.reply_text(f"Xray: {'✅' if rc == 0 else '❌'} {out or 'unknown'}")


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    rc, out = run(["systemctl", "restart", XRAY_SERVICE])
    await update.effective_message.reply_text("✅ Xray перезапущен" if rc == 0 else f"❌ {out}")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is empty")
    if not ADMIN_IDS and not ALLOWED_CHAT_ID:
        raise SystemExit("Refusing to start without ADMIN_IDS or ALLOWED_CHAT_ID")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("key", cmd_key))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
