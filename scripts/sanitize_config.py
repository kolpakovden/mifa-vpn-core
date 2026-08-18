#!/usr/bin/env python3
import json, sys
from pathlib import Path
src=Path(sys.argv[1] if len(sys.argv)>1 else "/usr/local/etc/xray/config.json")
dst=Path(sys.argv[2] if len(sys.argv)>2 else "mifa-xray-public-template.json")
cfg=json.loads(src.read_text())
for ib in cfg.get("inbounds",[]):
    settings=ib.get("settings",{}); stream=ib.get("streamSettings",{})
    if "clients" in settings: settings["clients"]=[]
    reality=stream.get("realitySettings",{})
    if "privateKey" in reality: reality["privateKey"]="__REALITY_PRIVATE_KEY__"
    if "shortIds" in reality: reality["shortIds"]=["__REALITY_SHORT_ID__"]
    xhttp=stream.get("xhttpSettings",{}); ws=stream.get("wsSettings",{})
    if "path" in xhttp: xhttp["path"]="/__XHTTP_PATH__/"
    if "path" in ws: ws["path"]="/__WS_PATH__/"
dst.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+"\n")
print(dst)
