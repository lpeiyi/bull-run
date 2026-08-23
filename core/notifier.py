# -*- coding: utf-8 -*-
"""飞书机器人推送（自定义机器人 webhook，文本消息）"""
import requests


def send_feishu(webhook, title, text):
    """发送飞书文本消息，返回 (是否成功, 提示信息)"""
    if not webhook:
        return False, "未配置飞书 webhook"
    payload = {
        "msg_type": "text",
        "content": {"text": f"{title}\n{text}"},
    }
    try:
        r = requests.post(webhook, json=payload, timeout=10)
        data = r.json()
        ok = data.get("code") == 0 or data.get("StatusMessage") == "success"
        return ok, (data.get("msg") or data.get("StatusMessage") or "已发送")
    except Exception as e:
        return False, f"推送失败: {e}"