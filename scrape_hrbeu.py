#!/usr/bin/env python3
"""抓取哈工程就业网公开的宣讲会/双选会，并生成单文件 HTML。

只访问学校站点公开列表接口；不绕过登录、不抓取个人信息。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://job.hrbeu.edu.cn"
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36 "
    "HRBEU-Job-Radar/1.0"
)

# 增量缓存只在评分/城市推断模型不变时复用；模型改动后自动全量重算一次。
MODEL_VERSION = "2026-09-06-salary-v6"
RAW_VOLATILE_KEYS = frozenset({"browseNumber", "viewNumber"})


@dataclass(frozen=True)
class Source:
    kind: str
    endpoint: str


SOURCES = (
    Source("宣讲会", "/f/recruitmentFair/ajax_frontRecruitfair"),
    Source("双选会", "/f/bilateralchosefair/ajax_frontBilateralchosefair"),
)


# 这是根据企业官网、公开招聘页、地图/工商公开页整理的“总部/主要基地”线索，
# 不冒充岗位工作城市；页面会给每条结果生成网络检索入口并标注“待核验”。
NETWORK_CITY_HINTS: tuple[tuple[str, str], ...] = (
    ("第五十四研究所", "石家庄"),
    ("第五十三研究所", "天津"),
    ("第三十六研究所", "嘉兴"),
    ("第三十三研究所", "太原"),
    ("第十三研究所", "石家庄"),
    ("第四十三研究所", "合肥"),
    ("第二十九研究所", "成都"),
    ("第十研究所", "成都"),
    ("第七一九研究所", "武汉"),
    ("七一五所", "杭州"),
    ("雷华电子", "无锡"),
    ("空空导弹研究院", "洛阳"),
    ("航空制造技术研究院", "北京"),
    ("航天科工二院", "北京"),
    ("北汽福田", "北京"),
    ("博众精工", "苏州"),
    ("辰致汽车", "重庆"),
    ("道恩集团", "烟台"),
    ("东风汽车股份", "武汉"),
    ("烽火通信", "武汉"),
    ("福建省晋华", "泉州"),
    ("歌尔股份", "潍坊"),
    ("顾家家居", "杭州"),
    ("广电运通", "广州"),
    ("广东凯金", "东莞"),
    ("广东美的", "佛山"),
    ("广西柳工", "柳州"),
    ("广西玉柴", "玉林"),
    ("贵州航天风华", "贵阳"),
    ("贵州航天控制", "贵阳"),
    ("国电投莱阳", "烟台"),
    ("国机精工", "郑州"),
    ("国睿科技", "南京"),
    ("海尔智家", "青岛"),
    ("海信集团", "青岛"),
    ("悍高集团", "佛山"),
    ("亨通集团", "苏州"),
    ("久之洋", "武汉"),
    ("华菱线缆", "湘潭"),
    ("星邦智能", "长沙"),
    ("华海通信", "天津"),
    ("华勤技术", "上海"),
    ("华为", "深圳"),
    ("机械工业第九设计研究院", "长春"),
    ("基恩士", "上海"),
    ("嘉士伯企业管理", "广州"),
    ("江南造船", "上海"),
    ("江苏常发", "常州"),
    ("江苏福拉特", "无锡"),
    ("江苏金智", "南京"),
    ("杰瑞新能源", "烟台"),
    ("锦浪科技", "宁波"),
    ("莱克电气", "苏州"),
    ("浪潮集团", "济南"),
    ("奇瑞汽车", "芜湖"),
    ("人本股份", "温州"),
    ("荣耀终端", "深圳"),
    ("软控股份", "青岛"),
    ("赛力斯", "重庆"),
    ("山东核电", "烟台"),
    ("山东临工", "临沂"),
    ("山东新北洋", "威海"),
    ("山推工程", "济宁"),
    ("陕西汉德", "西安"),
    ("陕西汽车", "西安"),
    ("上能电气", "无锡"),
    ("上汽通用五菱", "柳州"),
    ("舜宇集团", "宁波"),
    ("潍柴动力", "潍坊"),
    ("潍柴雷沃", "潍坊"),
    ("西北有色金属研究院", "西安"),
    ("欣旺达", "深圳"),
    ("新乡航空", "新乡"),
    ("新誉集团", "常州"),
    ("徐工集团", "徐州"),
    ("一汽解放", "长春"),
    ("粤芯半导体", "广州"),
    ("长城电源", "深圳"),
    ("长园科技", "深圳"),
    ("长园深瑞", "深圳"),
    ("春风动力", "杭州"),
    ("吉利控股", "杭州"),
    ("晶盛机电", "绍兴"),
    ("锐鹰传感", "嘉兴"),
    ("三花商用制冷", "绍兴"),
    ("水晶光电", "台州"),
    ("致欧家居", "郑州"),
    ("戚墅堰", "常州"),
    ("中达电子", "苏州"),
    ("中电科航空电子", "成都"),
    ("中电科芯片技术", "重庆"),
    ("中国第一汽车", "长春"),
    ("中国电信股份有限公司黑龙江", "哈尔滨"),
    ("中国东方电气", "成都"),
    ("中国工商银行股份有限公司黑龙江", "哈尔滨"),
    ("中国航发动力", "西安"),
    ("航发湖南动力机械", "株洲"),
    ("航发南方工业", "株洲"),
    ("航发商用航空发动机", "上海"),
    ("凯迈（洛阳）", "洛阳"),
    ("中国科学院空天信息", "北京"),
    ("中航飞机起落架", "长沙"),
    ("中航光电", "洛阳"),
    ("中航隆盛", "洛阳"),
    ("中航西飞", "西安"),
    ("中建八局第四", "青岛"),
    ("中建八局西南", "成都"),
    ("中建三局集团华南", "广州"),
    ("中建三局集团建设发展", "北京"),
    ("中建三局总承包", "武汉"),
    ("中建三局集团有限公司", "武汉"),
    ("中建四局建设投资", "广州"),
    ("中建四局土木", "深圳"),
    ("中建一局集团第二", "北京"),
    ("中建长江国际", "武汉"),
    ("中交二航局第三", "镇江"),
    ("中交广航（黑龙江）", "哈尔滨"),
    ("中能建建筑", "合肥"),
    ("中铁城建", "长沙"),
    ("中铁二局", "成都"),
    ("中铁二十五局", "广州"),
    ("中信重工", "洛阳"),
    ("TCL华星", "深圳"),
    ("中兴通讯", "深圳"),
    ("鹏芯微", "深圳"),
    ("优必选", "深圳"),
    ("桃李未来", "深圳"),
    ("西安微电子", "西安"),
    ("西安现代控制", "西安"),
    ("航天智信", "武汉"),
    ("三十研究所", "成都"),
    ("第三十研究所", "成都"),
    ("七一六研究所", "连云港"),
    ("第七一六研究所", "连云港"),
    ("七二二研究所", "武汉"),
    ("第七二二研究所", "武汉"),
    ("上海空间电源", "上海"),
    ("外高桥造船", "上海"),
    ("广船国际", "广州"),
    ("工业和信息化部电子第五研究所", "广州"),
    ("烟台九目", "烟台"),
    ("特变电工沈阳", "沈阳"),
    ("中船澄西", "江阴"),
    ("安凯汽车", "合肥"),
    ("中科光电", "合肥"),
    ("豪迈集团", "潍坊"),
    ("海南国际商业航天", "文昌"),
    ("红林航空", "贵阳"),
    ("中国兵器集团", "多地"),
    ("中国船舶集团", "多地"),
    ("中国电子科技集团", "多地"),
    ("中国航空发动机集团", "多地"),
    ("中国航发控制系统研究所", "无锡"),
    ("中国航空工业集团", "多地"),
    ("中国核工业集团", "多地"),
    ("中国核能电力", "多地"),
    ("中国机械工业集团", "多地"),
    ("中国远洋海运重工", "多地"),
    ("山东省人力资源和社会保障厅", "山东多地"),
    ("工信就业", "多地"),
    ("海军部队", "多地"),
    ("链接未来", "多地"),
    ("军科院", "北京"),
)


CITY_NAMES = (
    "北京", "上海", "深圳", "广州", "杭州", "南京", "苏州", "无锡", "常州",
    "成都", "武汉", "西安", "哈尔滨", "长春", "沈阳", "大连", "天津", "重庆",
    "青岛", "烟台", "济南", "潍坊", "合肥", "厦门", "福州", "宁波", "珠海",
    "佛山", "东莞", "长沙", "郑州", "南昌", "南通", "扬州", "江阴", "连云港",
    "石家庄", "嘉兴", "太原", "泉州", "柳州", "玉林", "洛阳", "湘潭", "济南",
    "芜湖", "温州", "临沂", "威海", "济宁", "绍兴", "台州", "新乡", "徐州",
    "株洲", "镇江",
    "贵阳", "昆明", "海口", "文昌", "太原", "石家庄", "乌鲁木齐", "呼和浩特",
)


PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "ic": {
        "label": "IC 设计验证",
        "signals": (
            "芯片", "微电子", "集成电路", "半导体", "电子", "硬件", "ASIC", "FPGA",
            "验证", "电路", "控制", "嵌入式", "研究所", "航天", "航空", "航发", "兵器", "船舶", "通信",
        ),
        "domains": ("芯片/电子", "航天/军工", "通信/网络安全"),
        "soft_domains": ("汽车/制造", "能源/电力"),
    },
    "ai": {
        "label": "AI 应用开发",
        "signals": (
            "软件", "计算机", "信息", "网络", "网安", "通信", "数字", "智能", "数据",
            "互联网", "云", "AI", "人工智能", "算法", "平台", "Agent", "大模型",
            "科技", "研发",
        ),
        "domains": ("软件/互联网", "通信/网络安全"),
        "soft_domains": ("教育/科研", "芯片/电子", "航天/军工", "能源/电力"),
    },
}

# 保留旧字段名的兼容默认值；新页面使用 profileFits 中的双方向评分。
BACKEND_SIGNALS = PROFILE_CONFIGS["ai"]["signals"]

DOMAIN_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("软件/互联网", ("软件", "互联网", "数据", "云计算", "数字科技")),
    ("通信/网络安全", ("通信", "网安", "网络安全", "电子信息")),
    ("芯片/电子", ("芯", "微电子", "集成电路", "半导体", "电子")),
    ("航天/军工", ("航天", "航空", "航发", "兵器", "国防", "船舶", "中船", "中电科")),
    ("能源/电力", ("电力", "能源", "核能", "电工", "电网")),
    ("建筑/工程", ("中建", "建筑", "建设", "工程局", "水利水电")),
    ("汽车/制造", ("汽车", "装备", "重工", "制造", "机械")),
    ("化工/材料", ("化学", "化工", "材料")),
    ("教育/科研", ("大学", "学院", "教育", "研究院", "研究所")),
)


# 少量高相关企业的“多源线索”。官方材料只能说明制度与公司口径，社区讨论只代表样本体验。
CURATED_REPUTATION: tuple[dict[str, Any], ...] = (
    {
        "keywords": ("中兴通讯",),
        "summary": "技术平台和通信/云网业务与 AI、软件及芯片相关方向有交集；公开讨论反复提醒：工作节奏、绩效和体验高度依赖事业部与直属团队。",
        "verify": "问清具体事业部、产品线、1246/周末安排、绩效基数、调薪节奏和 Base 地，别只看集团名。",
        "links": {
            "中兴·牛客讨论": "https://www.nowcoder.com/enterprise/664/discussion",
            "中兴·2025可持续发展报告": "https://www.zte.com.cn/content/dam/zte-site/investorrelations/cn_announcement/2026032602.pdf",
        },
    },
    {
        "keywords": ("中国电子科技集团", "中国电科", "中电科"),
        "summary": "科研平台、项目资源与稳定性通常有吸引力，但各研究所并不是同一个雇主体验；任务、薪酬、编制和城市必须逐所比较。",
        "verify": "确认事业/企业编、合同主体、密级、总包组成、末位/绩效、加班出差，以及软件岗做研发还是支撑。",
        "links": {
            "中国电科·招聘问答": "https://www.cetc.com.cn/zgdk/1593022/1593025/1610552/index.html",
        },
    },
    {
        "keywords": ("海能达",),
        "summary": "通信技术积累和新人项目机会是常见正面线索；同一社区也能看到对加班、流程、涨薪和团队氛围的相反评价，部门差异明显。",
        "verify": "问到部门和产品线，确认加班是否指令性、是否有费用/调休、年终与涨薪规则、当前业务稳定性。",
        "links": {
            "海能达·牛客讨论": "https://www.nowcoder.com/enterprise/1109/discussion?evaluateSubscriptTab=3032",
            "海能达·牛客面经": "https://www.nowcoder.com/enterprise/1109/interview",
        },
    },
    {
        "keywords": ("烽火通信",),
        "summary": "光通信平台和培训体系是可见优势；员工/校招讨论中也存在对工时、绩效和团队体验的负面样本，需要按岗位与年份核验。",
        "verify": "问清软开岗位技术栈、所在子公司/部门、加班频率与补偿、试用/保护期和绩效分布。",
        "links": {
            "烽火·牛客面经": "https://www.nowcoder.com/enterprise/1121/interview",
            "烽火·2025 ESG报告": "https://stockmc.xueqiu.com/202604/600498_20260425_4CPY.pdf",
        },
    },
    {
        "keywords": ("上海微电子装备",),
        "summary": "国产半导体装备平台和研发场景有稀缺性；公开校招材料强调保障与研发岗位，但互联网匿名口碑不足以代表具体团队。",
        "verify": "技术方向同学重点确认是平台软件/控制软件/信息化哪一类，另问技术栈、项目周期、加班、出差和薪酬组成。",
        "links": {
            "上微·官方园区/生活": "https://www.smee.com.cn/eis.pub?method=page&service=homepageService&showform=portalv2%2Fschoollife.ftl",
            "上微·面试样本": "https://www.job592.com/pay/comms29206487.html",
        },
    },
    {
        "keywords": ("圣邦微电子",),
        "summary": "模拟芯片研发平台和行业成长性值得关注；公司公开材料强调研发人才与激励，具体工时与团队体验仍需向目标部门员工核实。",
        "verify": "确认岗位是否偏软件/工具链、研发团队归属、绩效与股权条件、工作地点和加班频率。",
        "links": {
            "圣邦微·2025年报": "https://www.sg-micro.com/rect/assets/676f0efc-4124-4cfe-90d7-b84cbdaf457e",
            "圣邦微·2025 ESG报告": "https://static.cninfo.com.cn/finalpage/2026-03-28/1225045236.PDF",
        },
    },
)

# 只有能定位到公开校招/岗位样本时才填入数值；仍标注“待核验”，不代表本场活动的确定 offer。
CURATED_SALARY_HINTS: tuple[dict[str, str], ...] = (
    {
        "keywords": "烽火通信",
        "salary": "8k-15k/月",
        "basis": "网络查询得到：公开校招岗位样本（待核验）",
        "url": "https://jdjyw.jlu.edu.cn/portal/jyzp/job/details?id=ebf3868ac9ab438bb1f64b65fdaefeb6",
    },
    {
        "keywords": "中兴通讯",
        "salary": "25k-30k/月",
        "basis": "网络查询得到：公开 AI 应用岗位样本·上海（待核验）",
        "url": "https://www.shushuqiuzhi.com/article/118107",
    },
    {
        "keywords": "海能达",
        "salary": "12k-20k×14薪",
        "basis": "网络查询得到：公开岗位样本·深圳（待核验）",
        "url": "https://www.nowcoder.com/jobs/detail/459408?urlSource=sitemap",
    },
    {
        "keywords": "中国航发控制系统研究所",
        "salary": "12k+/月",
        "basis": "网络查询得到：高校就业岗位样本·无锡（待核验）",
        "url": "https://www.career.zju.edu.cn/jyxt/sczp/zpztgl/ckZpgwXq.zf?zpxxbh=3ECE38011D7383F1E0653A68DD0E9B18",
    },
    {
        "keywords": "理工雷科",
        "salary": "15k-20k/月",
        "basis": "网络查询得到：公开校招岗位样本（待核验）",
        "url": "https://career.nankai.edu.cn/correcruit/content/id/116680.html",
    },
    {
        "keywords": "第五十四研究所",
        "salary": "15k+/月",
        "basis": "网络查询得到：高校就业岗位样本·石家庄（待核验）",
        "url": "https://job.xidian.edu.cn/teachin/view/id/126936",
    },
    {
        "keywords": "七一五",
        "salary": "博士28-40万/年；硕士18-28万/年；本科10-15万/年",
        "basis": "网络查询得到：公开校招公告（待核验）",
        "url": "https://campus.niuqizp.com/job-vss5NzLnL.html",
    },
    {
        "keywords": "第二十九研究所",
        "salary": "20k-30k/月",
        "basis": "网络查询得到：高校就业岗位样本·成都（待核验）",
        "url": "https://scc.hnu.edu.cn/detail/job?id=2579406&online_id=3538470",
    },
    {
        "keywords": "七一六研究所",
        "salary": "博士23k+/月、硕士17k+/月（北京）；博士18k+/月、硕士12k+/月（连云港）",
        "basis": "网络查询得到：高校就业校招简章（待核验）",
        "url": "https://job.hust.edu.cn/extxjh/971757734432078.do",
    },
    {
        "keywords": "圣邦微电子",
        "salary": "1.2万-2万/月",
        "basis": "网络查询得到：公开岗位样本（待核验）",
        "url": "https://mwenku.51job.com/shanghai_jobs/202604/qianrushiyingjian/",
    },
)


def enable_ipv4_only_if_requested() -> None:
    """GitHub hosted runners may resolve the school site to an unroutable IPv6 address."""
    if os.environ.get("HRBEU_FORCE_IPV4") != "1":
        return
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_getaddrinfo(
        host: str | None,
        port: str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[Any, ...]]:
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_getaddrinfo
    print("网络：已启用 IPv4 模式（GitHub Actions 兼容）", flush=True)


def post_json(
    path: str,
    payload: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 4,
) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            BASE_URL + path,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": BASE_URL + "/",
                "Connection": "close",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == retries:
                break
            wait_seconds = attempt * 1.2
            print(f"请求暂时失败，{wait_seconds:.1f} 秒后重试（{attempt}/{retries}）…", flush=True)
            time.sleep(wait_seconds)
    assert last_error is not None
    raise last_error


def fetch_source(source: Source, page_size: int = 100, delay: float = 0.18) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_no = 1
    total_pages = 1
    while page_no <= total_pages:
        result = post_json(source.endpoint, {"pageNo": page_no, "pageSize": page_size})
        if result.get("state") != 1:
            raise RuntimeError(f"{source.kind}接口返回失败: {result.get('msg', '未知错误')}")
        page = result.get("object") or {}
        batch = page.get("list") or []
        for item in batch:
            item["_source_kind"] = source.kind
        items.extend(batch)
        total_pages = int(page.get("totalPage") or 1)
        print(f"{source.kind}: {page_no}/{total_pages} 页，累计 {len(items)} 条", flush=True)
        page_no += 1
        if page_no <= total_pages:
            time.sleep(delay)
    return items


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def iter_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{key}: {child}"
            yield from iter_text_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from iter_text_values(child)
    elif value is not None:
        yield str(value)


SALARY_NUMBER_RE = re.compile(
    r"(?i)(\d{1,3}(?:\.\d+)?\s*(?:k|千|万)?\s*(?:[-~至]\s*\d{1,3}(?:\.\d+)?\s*(?:k|千|万)?)?\s*(?:元|万元)?\s*(?:/月|/年|每月|每年)?)"
)


def extract_school_salary(item: dict[str, Any]) -> str:
    """只从学校公开接口返回的字段中提取薪资，不把标题年份/浏览量当薪资。"""
    context_terms = ("薪资", "月薪", "年薪", "工资", "薪酬", "待遇", "收入", "salary", "pay")
    for text in iter_text_values(item):
        compact = clean_text(text)
        if not any(term.lower() in compact.lower() for term in context_terms):
            continue
        match = SALARY_NUMBER_RE.search(compact)
        if match:
            value = clean_text(match.group(1)).strip(" :：")
            if re.search(r"\d", value) and not re.fullmatch(r"20\d{2}", value):
                return value
    return ""


def infer_city(company: str, title: str) -> tuple[str, str, str]:
    text = company + " " + title
    for city in CITY_NAMES:
        if city in text:
            return city, "名称线索", ""
    for keyword, city in NETWORK_CITY_HINTS:
        if keyword in text:
            query = urllib.parse.quote(f'"{company}" 总部 地址 官网')
            basis = "网络资料：集团/参会单位多地" if "多地" in city else "网络资料：总部/主要基地"
            return city, basis + "（待核验）", "https://cn.bing.com/search?q=" + query
    return "待核验", "学校公开列表未提供", ""


def infer_domain(company: str, title: str) -> str:
    text = company + " " + title
    for label, keywords in DOMAIN_LABELS:
        if any(keyword in text for keyword in keywords):
            return label
    return "其他"


def infer_reputation(company: str, title: str, domain: str) -> tuple[str, str, dict[str, str]]:
    text = company + " " + title
    for profile in CURATED_REPUTATION:
        if any(keyword in text for keyword in profile["keywords"]):
            return profile["summary"], profile["verify"], dict(profile["links"])
    if any(k in text for k in ("研究所", "研究院", "航天", "船舶", "中船", "兵器", "国防", "中电科")):
        return (
            "平台与稳定性通常是优势；不同所、部门和用工性质差异很大。",
            "重点核实编制/合同主体、总包结构、加班出差、涉密限制与技术栈。",
            {},
        )
    if any(k in text for k in ("中兴", "通信", "软件", "互联网", "科技", "数据", "智能")):
        return (
            "技术岗位与 AI、软件或数字化方向的交集较多，但体验通常强依赖事业部和直属团队。",
            "重点核实部门业务、技术岗占比、加班强度、绩效规则和工作地点。",
            {},
        )
    if domain == "建筑/工程":
        return (
            "大型工程平台与项目机会较多，项目制和驻场流动是常见变量。",
            "技术方向同学应确认是否为信息化核心岗，以及常驻地点、出差和项目周期。",
            {},
        )
    if domain in ("汽车/制造", "芯片/电子", "能源/电力"):
        return (
            "产业平台和业务稳定性值得关注，数字化岗位的技术深度因团队而异。",
            "重点核实岗位归属、研发投入、轮岗安排、薪酬构成与城市。",
            {},
        )
    return (
        "公开列表信息不足，暂不对企业好坏下结论。",
        "先看岗位 JD，再交叉核验应届生评价、劳动合同主体和工作地点。",
        {},
    )


def infer_profile_fit(
    company: str,
    title: str,
    domain: str,
    city: str,
    profile_key: str,
) -> dict[str, Any]:
    """根据两份简历提炼的方向证据做可解释初筛，不是录用概率。"""
    config = PROFILE_CONFIGS[profile_key]
    text = company + " " + title
    score = 32
    reasons: list[str] = []
    matches = [signal for signal in config["signals"] if signal.lower() in text.lower()]
    if matches:
        bump = min(36, 10 + len(matches) * 4)
        score += bump
        reasons.append("名称命中方向线索：" + "、".join(matches[:4]))
    if domain in config["domains"]:
        score += 18
        reasons.append("行业与该方向关联较强")
    elif domain in config["soft_domains"]:
        score += 9
        reasons.append("可能存在相关研发、平台或数字化岗位")
    elif domain in ("建筑/工程", "化工/材料"):
        score -= 7
        reasons.append("需确认是否开放该方向的技术岗位")
    if city != "待核验":
        score += 3
    score = max(20, min(92, score))
    if score >= 72:
        band = "优先看"
    elif score >= 55:
        band = "值得核实"
    else:
        band = "低优先"
    if not reasons:
        reasons.append("仅有活动标题，岗位信息不足")
    return {"score": score, "reasons": reasons, "band": band}


def infer_base_fit(company: str, title: str, domain: str, city: str) -> tuple[int, list[str], str]:
    """兼容旧数据字段：以 AI 应用开发方向作为旧版 baseFit。"""
    fit = infer_profile_fit(company, title, domain, city, "ai")
    return fit["score"], fit["reasons"], fit["band"]


def normalize(item: dict[str, Any]) -> dict[str, Any] | None:
    start = parse_dt(item.get("startTime"))
    if not start:
        return None
    title = clean_text(item.get("title")) or "未命名活动"
    corp = item.get("corporationinfo") or {}
    company = clean_text(corp.get("name"))
    if not company or company == "哈尔滨工程大学就业指导中心":
        company = re.sub(r"(?:20\d{2}届|校园|秋季|春季|专场|线下|线上|招聘|宣讲会|双选会).*", "", title).strip(" -—/") or title
    city, city_basis, city_source_url = infer_city(company, title)
    domain = infer_domain(company, title)
    reputation, verify, curated_links = infer_reputation(company, title, domain)
    profile_fits = {
        key: infer_profile_fit(company, title, domain, city, key)
        for key in PROFILE_CONFIGS
    }
    # 旧版页面/外部脚本仍可读取 baseFit；新页面会按当前方向使用 profileFits。
    legacy = profile_fits["ai"]
    path = clean_text(item.get("url"))
    source_url = urllib.parse.urljoin(BASE_URL, path)
    search_term = urllib.parse.quote(company + " 校招 员工评价 加班 薪资")
    school_salary = extract_school_salary(item)
    salary = school_salary
    salary_basis = "学校公开信息" if school_salary else ""
    salary_source_url = source_url if school_salary else ""
    if not school_salary:
        for hint in CURATED_SALARY_HINTS:
            if hint["keywords"] in f"{company} {title}":
                salary = hint["salary"]
                salary_basis = hint["basis"]
                salary_source_url = hint["url"]
                break
    if not salary:
        salary = "未公开"
        salary_basis = "网络查询未找到公开薪资"
        salary_source_url = (
            "https://cn.bing.com/search?q="
            + urllib.parse.quote(f'"{company}" 校招 薪资 月薪 年薪 岗位')
        )
    return {
        "id": clean_text(item.get("id")),
        "type": item.get("_source_kind") or "活动",
        "title": title,
        "company": company,
        "start": start.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "end": (parse_dt(item.get("endTime")) or start).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "place": clean_text(item.get("realPlace") or item.get("place")) or "待公布",
        "online": str(item.get("fairType") or "") not in ("", "1"),
        "status": clean_text(item.get("holdStatus")) or ("已结束" if str(item.get("isExpired")) == "1" else "未开始"),
        "views": int(item.get("browseNumber") or 0),
        "city": city,
        "cityBasis": city_basis,
        "citySourceUrl": city_source_url,
        "salary": salary,
        "salaryBasis": salary_basis,
        "salarySourceUrl": salary_source_url,
        "domain": domain,
        "reputation": reputation,
        "verify": verify,
        "baseFit": max(fit["score"] for fit in profile_fits.values()),
        "fitBand": legacy["band"],
        "fitReasons": legacy["reasons"],
        "profileFits": profile_fits,
        "sourceUrl": source_url,
        "reviewLinks": {
            **curated_links,
            "综合搜索": "https://www.google.com/search?q=" + search_term,
            "牛客讨论": "https://www.google.com/search?q=" + urllib.parse.quote("site:nowcoder.com " + company + " 校招 评价"),
            "知乎讨论": "https://www.google.com/search?q=" + urllib.parse.quote("site:zhihu.com " + company + " 工作 评价"),
        },
    }


def dedupe(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event.get("id") or f"{event['type']}|{event['title']}|{event['start']}"
        unique[key] = event
    return sorted(unique.values(), key=lambda e: (e["start"], e["type"], e["title"]))


def raw_cache_key(item: dict[str, Any]) -> str:
    source = item.get("_source_kind") or "活动"
    identity = item.get("id") or item.get("url") or item.get("title") or "unknown"
    return f"{source}|{identity}"


def raw_fingerprint(item: dict[str, Any]) -> str:
    stable = {key: value for key, value in item.items() if key not in RAW_VOLATILE_KEYS}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_raw(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique[raw_cache_key(item)] = item
    return list(unique.values())


def event_cache_key(event: dict[str, Any]) -> str:
    identity = event.get("id") or event.get("sourceUrl") or event.get("title")
    return f"{event.get('type', '活动')}|{identity}"


def load_incremental_cache(data_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], bool]:
    raw_path = data_dir / "raw-events.json"
    normalized_path = data_dir / "normalized-events.json"
    try:
        raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return {}, {}, False
    if not isinstance(raw_payload, dict) or raw_payload.get("modelVersion") != MODEL_VERSION:
        return {}, {}, False
    if not isinstance(normalized_payload, dict) or normalized_payload.get("modelVersion") != MODEL_VERSION:
        return {}, {}, False
    raw_items = raw_payload.get("items")
    previous_events = normalized_payload.get("events")
    if not isinstance(raw_items, dict) or not isinstance(previous_events, list):
        return {}, {}, False
    event_index = {
        event_cache_key(event): event
        for event in previous_events
        if isinstance(event, dict)
    }
    return raw_items, event_index, True


def normalize_with_cache(
    raw_items: list[dict[str, Any]],
    data_dir: Path,
    full_refresh: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    """复用未变化活动的标准化结果；接口分页仍会执行，因为学校接口没有增量游标。"""
    data_dir.mkdir(exist_ok=True)
    previous_raw, previous_events, cache_ready = load_incremental_cache(data_dir)
    use_cache = cache_ready and not full_refresh
    normalized: list[dict[str, Any]] = []
    current_raw: dict[str, dict[str, Any]] = {}
    seen_event_keys: set[str] = set()
    processed = reused = invalid = 0

    for item in raw_items:
        key = raw_cache_key(item)
        fingerprint = raw_fingerprint(item)
        current_raw[key] = {"fingerprint": fingerprint, "item": item}
        old = previous_raw.get(key) if use_cache else None
        cached_event = previous_events.get(f"{item.get('_source_kind') or '活动'}|{item.get('id')}")
        if (
            isinstance(old, dict)
            and old.get("fingerprint") == fingerprint
            and isinstance(cached_event, dict)
        ):
            # 浏览量是刻意排除在指纹外的易变字段；轻量同步它，避免热度排序停留在旧值。
            event = dict(cached_event)
            event["views"] = int(item.get("browseNumber") or item.get("viewNumber") or event.get("views") or 0)
            reused += 1
        else:
            event = normalize(item)
            processed += 1
        if event:
            normalized.append(event)
            seen_event_keys.add(event_cache_key(event))
        else:
            invalid += 1

    cache_payload = {
        "modelVersion": MODEL_VERSION,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": current_raw,
    }
    (data_dir / "raw-events.json").write_text(
        json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (data_dir / "normalized-events.json").write_text(
        json.dumps(
            {"modelVersion": MODEL_VERSION, "generatedAt": cache_payload["generatedAt"], "events": normalized},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    stats: dict[str, int | bool] = {
        "cacheReady": cache_ready,
        "fullRefresh": full_refresh or not use_cache,
        "rawCount": len(raw_items),
        "processed": processed,
        "reused": reused,
        "invalid": invalid,
        "removed": max(0, len(previous_events) - len(seen_event_keys)) if use_cache else 0,
    }
    return normalized, stats


def safe_json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(template_path: Path, output_path: Path, events: list[dict[str, Any]], fetched_at: datetime, school_warning: str = "") -> None:
    template = template_path.read_text(encoding="utf-8")
    # Only explicitly exported short assessments are eligible for the public site.
    report_path = template_path.parent / "reviews" / "xhs-reviewed.json"
    snapshot = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    reports = snapshot.get("reports", [])
    progress = snapshot.get('progress', {})
    by_company = {report["company"]: report for report in reports}
    events = [{**{k: v for k, v in event.items() if k not in ("xhsResearch", "xhsProgress")},
               "xhsResearch": by_company.get(event.get("company")),
               "xhsProgress": progress.get(event.get('company'), {})} for event in events]
    meta = {
        "fetchedAt": fetched_at.astimezone().isoformat(timespec="seconds"),
        "source": BASE_URL,
        "count": len(events),
        "researchUpdatedAt": snapshot.get('generatedAt'),
        "schoolRefreshWarning": school_warning,
        "note": "城市多为名称或总部/主要基地推断；适配分按 IC 设计验证与 AI 应用开发两条简历方向初筛，不是录用概率。",
    }
    output = template.replace("__EVENT_DATA__", safe_json_for_script(events))
    output = output.replace("__META_DATA__", safe_json_for_script(meta))
    output_path.write_text(output, encoding="utf-8")


def rebuild_saved_page(here: Path, output_path: Path) -> None:
    """Offline publication fallback; never relabel old school data as freshly fetched."""
    html = (here / 'index.html').read_text(encoding='utf-8')
    event_match = re.search(r'<script type="application/json" id="eventData">(.*?)</script>', html, re.S)
    meta_match = re.search(r'<script type="application/json" id="metaData">(.*?)</script>', html, re.S)
    if not event_match or not meta_match:
        raise ValueError('已保存页面缺少活动数据或原抓取时间，拒绝发布空页面。')
    events = json.loads(event_match[1])
    meta = json.loads(meta_match[1])
    if not isinstance(events, list) or not events:
        raise ValueError('已保存活动为空，拒绝回退发布。')
    build_html(here / 'template.html', output_path, events, datetime.fromisoformat(meta['fetchedAt']),
               '本次学校数据刷新失败，暂用已保存活动；下方时间为原抓取时间。')


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取哈工程就业网招聘活动并生成可筛选 HTML")
    parser.add_argument("--include-past", action="store_true", help="同时保留已经结束的活动")
    parser.add_argument("--since", help="起始日期 YYYY-MM-DD；默认今天")
    parser.add_argument("--delay", type=float, default=0.18, help="分页请求间隔秒数，默认 0.18")
    parser.add_argument("--output", default="index.html", help="生成的 HTML 文件名")
    parser.add_argument("--full-refresh", action="store_true", help="忽略本地缓存，强制重新处理全部记录")
    parser.add_argument("--from-snapshot", action="store_true", help="离线重建已保存活动，保留原时间并标注刷新失败")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    if args.from_snapshot:
        rebuild_saved_page(here, (here / args.output).resolve())
        print('已用保存的活动重建页面；未声称学校数据已刷新。')
        return 0
    enable_ipv4_only_if_requested()

    cutoff = datetime.strptime(args.since, "%Y-%m-%d") if args.since else datetime.now()
    raw: list[dict[str, Any]] = []
    try:
        for source in SOURCES:
            raw.extend(fetch_source(source, delay=max(0.0, args.delay)))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"抓取失败：{exc}") from exc

    data_dir = here / "data"
    raw_unique = dedupe_raw(raw)
    normalized, cache_stats = normalize_with_cache(raw_unique, data_dir, full_refresh=args.full_refresh)
    if not args.include_past:
        normalized = [event for event in normalized if datetime.fromisoformat(event["start"]).replace(tzinfo=None) >= cutoff]
    events = dedupe(normalized)

    data_dir.mkdir(exist_ok=True)
    (data_dir / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path = (here / args.output).resolve()
    build_html(here / "template.html", output_path, events, datetime.now().astimezone())
    mode = "全量" if cache_stats["fullRefresh"] else "增量"
    print(
        f"完成：{len(events)} 条活动 -> {output_path}；{mode}处理 "
        f"原始 {cache_stats['rawCount']} 条，复用 {cache_stats['reused']} 条，"
        f"重新处理 {cache_stats['processed']} 条，失效 {cache_stats['invalid']} 条",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
