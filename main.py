"""
说明：
1. 先请求亚马逊主页，得到主页的html和cookie（默认为ip地址所在的邮编）；html里面有一个隐藏 csrftoken id=glowValidationToken
2. 再请求切换邮编的页面，请求这个页面需要携带上面的csrftoken的值，请求参数为headers中的Anti-Csrftoken-A2z字段；
    得到响应的html。html中还有个 CSRF_TOKEN 字段，需使用则正匹配出其值
3. 再调用切换邮编地址的接口，post请求，body参数重需要填邮编地址；headers中的Anti-Csrftoken-A2z字段的值为邮编页面CSRF_TOKEN的值

"""

import re

from loguru import logger
from bs4 import BeautifulSoup
from curl_cffi import requests
from fake_useragent import UserAgent


class AddressCookie:
    def __init__(self, url: str, zip_code: str):
        self.url = url
        self.zip_code = zip_code
        self._default_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-fetch-dest": "document",
            "user-agent": UserAgent().random,
        }
        self.proxy = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

    def fetch(
            self, session: requests.Session, method: str, url: str, body: dict = None,
            headers: dict = None, cookies: dict = None
    ) -> requests.Response:
        logger.debug(f"请求 {url} 。。。")
        response = session.request(
            method=method, url=url, json=body, headers=headers, proxies=self.proxy, cookies=cookies
        )
        response.raise_for_status()
        return response

    def gen_address_cookie(self) -> dict:
        try:
            # --------------------- 1. 先请求亚马逊主页面 ---------------------
            session = requests.Session()
            index_rsp = self.fetch(session, "GET", self.url, headers=self._default_headers)
            # 获取 主页中的 csrf token 和 服务器返回的 cookies
            soup = BeautifulSoup(index_rsp.text, "html.parser")
            if soup.find("input", attrs={"id": "glowValidationToken"}) is None:
                raise Exception("没有获取到主页的 csrf_token，请重试或检查代码。")
            csrf_token = soup.find("input", attrs={"id": "glowValidationToken"}).get("value")
            index_cookies = index_rsp.cookies.get_dict()

            # --------------------- 2. 请求切换地址的页面 ---------------------
            # 需要携带上面的 csrf_token 请求参数为headers中的Anti-Csrftoken-A2z字段；
            csrf_token_endpoint = (
                "/portal-migration/hz/glow/get-rendered-address-selections?deviceType=desktop"
                "&pageType=Search&storeContext=NoStoreName&actionSource=desktop-modal"
            )
            headers = {**self._default_headers, "anti-csrftoken-a2z": csrf_token}
            csrf_token_rsp = self.fetch(
                session, "GET", self.url + csrf_token_endpoint, headers=headers, cookies=index_cookies
            )
            # 获取 地址页面的 csrf_token
            csrf_token_pattern = r'CSRF_TOKEN\s*:\s*"([^"]+)"'
            match = re.search(csrf_token_pattern, csrf_token_rsp.text)
            if match is None:
                raise Exception("没有获取到地址页面 csrf_token，请重试或检查代码。")
            add_page_csrf_token = match.group(1)

            # --------------------- 3.再调用切换邮编的接口 ---------------------
            payload = {
                "locationType": "LOCATION_INPUT",
                "zipCode": self.zip_code.replace("+", " "),
                "storeContext": "generic",
                "deviceType": "web",
                "pageType": "Gateway",
                "actionSource": "glow",
            }
            headers = {
                **self._default_headers,
                "content-type": "application/json",
                "anti-csrftoken-a2z": add_page_csrf_token,
            }
            address_change_endpoint = "/portal-migration/hz/glow/address-change?actionSource=glow"
            add_rsp = self.fetch(
                session, method="POST", url=self.url + address_change_endpoint, body=payload,
                headers=headers, cookies=index_cookies
            )
            if '"isValidAddress":1' not in add_rsp.text:
                raise Exception(f"切换失败，请检查 {self.url} 站点{self.zip_code}")
            return add_rsp.cookies.get_dict()
        except Exception as e:
            logger.exception(f"获取失败，错误信息： {e=}")


if __name__ == '__main__':
    cookie = AddressCookie(url="https://www.amazon.com", zip_code="10008")
    logger.info(cookie.gen_address_cookie())
