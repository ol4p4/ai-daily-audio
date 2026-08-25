"""
HTTP 请求安全校验模块
所有出站请求统一走这里：限制协议、校验目标主机、阻断内网/环回/链路本地地址、拦截跨主机重定向
"""
import socket
import urllib.parse
import urllib.request


def validate_url(url: str) -> str:
    """校验 URL：仅允许 http/https 公网地址，拒绝私网/环回/链路本地地址（防 SSRF）"""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")

    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        raise ValueError(f"无法解析主机: {host}")
    if ":" in ip:
        raise ValueError(f"不支持 IPv6 地址: {ip}")

    parts = [int(p) for p in ip.split(".")]
    is_private = (
        parts[0] == 10
        or (parts[0] == 172 and 16 <= parts[1] <= 31)
        or (parts[0] == 192 and parts[1] == 168)
    )
    if is_private or parts[0] in (127, 0):
        raise ValueError(f"目标为私网/环回地址，已拒绝: {ip}")
    if parts[0] == 169 and parts[1] == 254:
        raise ValueError(f"目标为链路本地地址（可能为云元数据），已拒绝: {ip}")
    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """拒绝跨主机的重定向，防止被引导到内网"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            validate_url(new_req.full_url)
        return new_req


def open_url(req, *args, **kwargs):
    """校验目标后发起请求（替代 urllib.request.urlopen 的统一入口）"""
    validate_url(req.full_url if hasattr(req, "full_url") else str(req))
    return urllib.request.build_opener(SafeRedirectHandler()).open(req, *args, **kwargs)
