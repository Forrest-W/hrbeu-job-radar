"""Read-only XHS transport. Cookies are supplied explicitly; no browser-profile access."""
from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ResearchError(Exception):
    """Only fixed, credential-free messages may be raised to the CLI."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an authenticated request to a redirect destination.
        return None


class XhsTransport:
    HOST = "https://edith.xiaohongshu.com"
    SEARCH_ENDPOINTS = {"https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
                        "https://so.xiaohongshu.com/api/sns/web/v2/search/notes"}
    PATHS = {"/api/sns/web/v1/search/notes", "/api/sns/web/v2/search/notes", "/api/sns/web/v1/feed"}

    def __init__(self, cookies: dict[str, str], delay: float = 5, endpoint=None, user_agent=None):
        try:
            from xhshow import Xhshow, CryptoConfig
        except ImportError:
            raise ResearchError("未安装签名依赖；请运行 .venv-xhs 的 pip install -r requirements-xhs.txt") from None
        self.endpoint = endpoint or "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
        if self.endpoint not in self.SEARCH_ENDPOINTS:
            raise ResearchError("搜索接口不在允许列表中。")
        if user_agent and any(ord(c) < 32 or ord(c) > 126 for c in user_agent):
            raise ResearchError("User-Agent 格式无效。")
        config = CryptoConfig()
        if user_agent:
            config = config.with_overrides(PUBLIC_USERAGENT=user_agent)
        self.signer = Xhshow(config)
        self.user_agent = config.PUBLIC_USERAGENT
        self.cookies = cookies
        self.delay = max(5, delay)
        self.last_request = 0.0
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path: str, payload: dict) -> dict:
        if path not in self.PATHS:
            raise ResearchError("仅允许笔记搜索和详情读取接口。")
        time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        try:
            signed = self.signer.sign_headers_post(path, self.cookies, payload=payload,
                                                   x_rap=path.startswith('/api/sns/web/v2/search/'))
        except Exception:
            raise ResearchError("请求签名生成失败；请核对登录信息和签名适配器版本。") from None
        headers = {k: str(v) for k, v in signed.items() if k.lower() in {
            "x-s", "x-t", "x-s-common", "x-b3-traceid", "x-xray-traceid", "x-rap-param"}}
        headers.update({"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
                        "User-Agent": self.user_agent, "Origin": "https://www.xiaohongshu.com",
                        "Referer": "https://www.xiaohongshu.com/",
                        "Content-Type": "application/json;charset=UTF-8"})
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        host = "https://so.xiaohongshu.com" if path == "/api/sns/web/v2/search/notes" else self.HOST
        req = urllib.request.Request(host + path, body, headers, method="POST")
        self.last_request = time.monotonic()
        try:
            with self.opener.open(req, timeout=25) as response:
                data = json.loads(response.read(5_000_001))
        except urllib.error.HTTPError as error:
            raise ResearchError(f"HTTP {error.code}：本批次已停止。请在网站检查登录/验证状态。") from None
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            raise ResearchError("网络异常或响应无法解析，本批次已停止。") from None
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ResearchError("小红书未返回成功结果，可能是登录失效、验证、限流或接口变更；已暂停。")
        result = data.get("data")
        if not isinstance(result, dict):
            raise ResearchError("接口结构发生变化；未将该查询标为完成。")
        return result

    def search(self, keyword: str) -> list[dict]:
        data = self.request(urlsplit(self.endpoint).path, {
            "keyword": keyword, "page": 1, "page_size": 10,
            "search_id": uuid.uuid4().hex, "sort": "general", "note_type": 0,
            "ext_flags": [], "filters": [], "geo": "", "image_formats": ["jpg", "webp"]})
        if not isinstance(data.get("items"), list):
            raise ResearchError("搜索响应缺少 items 数组；需要检查适配器。")
        return data["items"]

    def detail(self, note_id: str, token: str) -> dict:
        data = self.request("/api/sns/web/v1/feed", {
            "source_note_id": note_id, "image_formats": ["jpg", "webp"],
            "extra": {"need_body_topic": "1"}, "xsec_source": "pc_search", "xsec_token": token})
        items = data.get("items")
        if not isinstance(items, list) or not items or not isinstance(items[0].get("note_card"), dict):
            raise ResearchError("详情响应没有可读正文；保留待完成状态。")
        return items[0]["note_card"]
