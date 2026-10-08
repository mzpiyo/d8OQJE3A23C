import os
import re
import time
import logging
import json
from curl_cffi import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class TSDMAutomation:
    BASE_URL = "https://www.tsdm39.com"
    
    def __init__(self):
        self.cookie = os.environ.get("TSDM_COOKIE", "")
        self.gotify_url = os.environ.get("GOTIFY_URL", "")
        self.gotify_token = os.environ.get("GOTIFY_TOKEN", "")

        self.session = requests.Session(impersonate="chrome120")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"{self.BASE_URL}/forum.php",
            "Cookie": self.cookie
        })
        
        self.results = []
        self.angel_coins = "未知"

    def request(self, method, url, retries=3, **kwargs):
        """带重试机制的请求封装"""
        for i in range(retries):
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code == 200 or resp.status_code == 302:
                    return resp
                logging.warning(f"请求 {url} 状态码异常: {resp.status_code}，重试 {i+1}/{retries}")
            except Exception as e:
                logging.error(f"请求 {url} 网络异常: {e}，重试 {i+1}/{retries}")
            time.sleep(3)
        raise Exception(f"请求 {url} 彻底失败")

    def extract_formhash(self, html):
        pattern = r'(?:name="formhash"\s+value="|formhash=)([a-zA-Z0-9]{8})'
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def get_score(self):
        """获取天使币余额"""
        try:
            url = f"{self.BASE_URL}/home.php"
            params = {"mod": "spacecp", "ac": "credit", "showcredit": "1"}
            resp = self.request("GET", url, params=params)
            match = re.search(r'天使币[：:]\s*(\d+)', resp.text)
            if match:
                self.angel_coins = match.group(1)
        except Exception as e:
            logging.error(f"获取积分失败: {e}")

    def check_in(self):
        """每日签到"""
        logging.info("开始执行签到...")
        try:
            resp = self.request("GET", f"{self.BASE_URL}/forum.php")
            formhash = self.extract_formhash(resp.text)
            if not formhash:
                self.results.append("❌ **签到失败**: 无法获取 formhash (Cookie可能已失效)")
                return

            payload = {
                "formhash": formhash, "qdxq": "kx", "qdmode": "3", 
                "todaysay": "", "fastreply": "1"
            }
            params = {
                "id": "dsu_paulsign:sign", "operation": "qiandao", 
                "infloat": "1", "sign_as": "1", "inajax": "1"
            }
            
            # X5.0 AJAX 请求通常需要此 Header
            headers = {"X-Requested-With": "XMLHttpRequest"}
            resp = self.request("POST", f"{self.BASE_URL}/plugin.php", params=params, data=payload, headers=headers)
            
            if "签到成功" in resp.text or "恭喜你签到成功" in resp.text:
                self.results.append("✅ **签到成功**: 获得随机奖励")
            elif "您今日已经签到" in resp.text:
                self.results.append("ℹ️ **签到跳过**: 今日已签到")
            else:
                self.results.append(f"⚠️ **签到异常**: 未知响应 (请检查Cookie)")
        except Exception as e:
            self.results.append(f"❌ **签到失败**: {str(e)}")

    def work(self):
        """每6小时打工"""
        logging.info("开始执行打工...")
        try:
            params = {"id": "np_cliworkdz:work"}
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}/plugin.php?id=np_cliworkdz:work"
            }
            
            # 1. 检查冷却状态
            resp = self.request("GET", f"{self.BASE_URL}/plugin.php", params=params, headers=headers)
            if re.search(r'需要等待.*?后即可进行', resp.text) or re.search(r'等待.*?小时', resp.text):
                self.results.append("ℹ️ **打工跳过**: 冷却时间中")
                return

            # 2. 连续点击广告 6 次
            for i in range(6):
                self.request("POST", f"{self.BASE_URL}/plugin.php", params=params, data={"act": "clickad"}, headers=headers)
                time.sleep(2) # 模拟人类点击间隔

            # 3. 领取奖励
            resp = self.request("POST", f"{self.BASE_URL}/plugin.php", params=params, data={"act": "getcre"}, headers=headers)
            
            if "领取了奖励" in resp.text or "打工成功" in resp.text or "获得" in resp.text:
                self.results.append("✅ **打工成功**: 已领取奖励")
            elif "已经打过工" in resp.text or "必须与上一次间隔" in resp.text:
                self.results.append("ℹ️ **打工跳过**: 今日额度已用完")
            else:
                self.results.append(f"⚠️ **打工异常**: 未知响应")
        except Exception as e:
            self.results.append(f"❌ **打工失败**: {str(e)}")

    def send_gotify(self):
        """发送聚合通知"""
        if not self.gotify_url or not self.gotify_token:
            logging.warning("未配置 Gotify，跳过通知")
            return

        self.get_score()
        
        title = "TSDM 任务执行报告"
        
        # 构建 Markdown 消息
        msg_lines = [f"💰 **当前天使币**: {self.angel_coins}\n", "---\n"]
        msg_lines.extend(self.results)
        message = "\n".join(msg_lines)

        payload = {
            "title": title,
            "message": message,
            "priority": 5,
            "extras": {
                "client::display": {
                    "contentType": "text/markdown"
                }
            }
        }

        try:
            url = f"{self.gotify_url}/message?token={self.gotify_token}"
            resp = requests.post(url, json=payload, impersonate="chrome120")
            if resp.status_code == 200:
                logging.info("Gotify 通知发送成功")
            else:
                logging.error(f"Gotify 发送失败: {resp.text}")
        except Exception as e:
            logging.error(f"Gotify 网络异常: {e}")

if __name__ == "__main__":
    bot = TSDMAutomation()
    
    if not bot.cookie:
        logging.error("未检测到 TSDM_COOKIE，请在 GitHub Secrets 中配置！")
        exit(1)

    bot.check_in()
    bot.work()
    
    bot.send_gotify()
