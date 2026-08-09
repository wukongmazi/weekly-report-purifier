# -*- coding: utf-8 -*-
"""
周报"注水"净化器 —— 后端 API 与 AI 逻辑
====================================
从流水账到价值叙事的自动化转化。

- 框架: FastAPI (监听 0.0.0.0:7860, 适配魔搭创空间)
- AI:  魔搭 API-Inference (OpenAI 兼容接口, Qwen 系列模型)
- 兜底: 未配置 API Key 时自动降级为本地规则引擎, 保证应用开箱即用
"""

import os
import re
import json
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 魔搭创空间: 在「设置 -> 环境变量」中配置 MODELSCOPE_API_KEY (即魔搭访问令牌)
API_KEY = (
    os.environ.get("MODELSCOPE_API_KEY")
    or os.environ.get("MODELSCOPE_ACCESS_TOKEN")
    or ""
).strip()
BASE_URL = os.environ.get("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-30B-A3B-Instruct-2507")

CATEGORIES = ["用户增长", "留存", "转化", "内容"]

app = FastAPI(title="周报注水净化器", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PurifyRequest(BaseModel):
    text: str
    api_key: str = ""   # 访客自带密钥（仅存于访客浏览器 localStorage，请求时随身携带）
    model: str = ""     # 可选：访客指定模型
    base_url: str = ""  # 可选：访客指定接口地址


# ---------------------------------------------------------------------------
# AI 引擎 (魔搭 API-Inference)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是一位资深互联网运营总监兼周报写作专家。用户会给你一段运营人员一周的零散工作记录（可能是语音转文字的口水话、流水账）。

你的任务分三步：

1.【碎碎念结构化】把零散记录拆分为独立工作条目，每条归入且仅归入以下四个维度之一：用户增长、留存、转化、内容。无法明确归类的按内容意图就近归类。

2.【价值升华】对每个条目，把平铺直叙的执行描述转化为"战略价值叙事"。要求：
   - 使用「通过XX手段/策略，实现/推动XX指标提升」的结构化表达；
   - 基于行业公认基准做合理推断补全数据（如公众号推文平均打开率3%-5%、标题A/B测试可提升点击率10%-20%、社群周活跃基准25%-40%、私域转化率基准5%-8%等），推断的数据须用"约/预计/预估"标注，不得凭空捏造精确到个位的假数据；
   - 体现方法论（A/B测试、漏斗优化、用户分层、SOP沉淀等）；
   - 保留原始描述用于对照。

3.【下周计划补全】识别记录中未完成、被搁置、提到"下周/待办/还没做"的事项，结合本周工作的自然延续，生成3-5条下周计划，每条包含：任务名、预期目标（尽量量化）、2-3个关键动作。

严格只输出如下 JSON（不要输出任何其他文字、不要 markdown 代码块）：
{
  "items": [
    {"category": "用户增长|留存|转化|内容", "raw": "原始描述", "refined": "价值叙事"}
  ],
  "next_week": [
    {"task": "任务名", "goal": "预期目标", "actions": ["关键动作1", "关键动作2"]}
  ],
  "summary": "一句话周报总结（30字内，管理者视角）"
}"""


def call_ai(text: str, api_key: str, model: str = "", base_url: str = "") -> dict:
    """调用魔搭 API-Inference，返回解析后的 JSON 结果。失败则抛异常。

    关键点：必须设置 timeout，否则默认可挂起 10 分钟，导致前端一直转圈。
    base_url / model 若由访客传入则优先使用。
    """
    from openai import OpenAI

    client = OpenAI(
        base_url=(base_url or BASE_URL).strip(),
        api_key=api_key,
        timeout=30.0,      # 单次请求最长 30 秒，超时即失败并降级
        max_retries=0,     # 不重试，避免长时间挂起
    )
    resp = client.chat.completions.create(
        model=model or MODEL_ID,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "本周工作记录如下：\n" + text.strip()},
        ],
        temperature=0.4,
        max_tokens=3000,
    )
    content = resp.choices[0].message.content.strip()
    # 容错：剥离可能存在的 ```json 包裹、思考链（<think>...</think>）等干扰
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I)
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if m:
        content = m.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1:
        content = content[start : end + 1]
    try:
        data = json.loads(content)
    except Exception:
        # 大模型偶尔输出不符合严格 JSON 的内容（漏逗号 / 尾逗号 / 未加引号键等），
        # 用 json_repair 做容错修复后再次解析，最大化可用性。
        import json_repair
        data = json_repair.loads(content)
    # 基本校验
    assert isinstance(data.get("items"), list) and data["items"], "AI返回条目为空"
    for it in data["items"]:
        if it.get("category") not in CATEGORIES:
            it["category"] = "内容"
    data.setdefault("next_week", [])
    data.setdefault("summary", "")
    return data


# ---------------------------------------------------------------------------
# 规则引擎兜底 (无 API Key / AI 调用失败时使用, 保证应用可用)
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "用户增长": ["拉新", "新增", "涨粉", "获客", "推广", "投放", "引流", "注册", "曝光",
               "地推", "裂变", "邀请", "渠道", "广告", "粉丝", "关注"],
    "留存": ["留存", "活跃", "社群", "群", "维护", "回访", "召回", "签到", "打卡",
            "答疑", "客诉", "服务", "会员", "运营活动", "互动"],
    "转化": ["转化", "成交", "下单", "GMV", "销售", "付费", "ROI", "成单", "订单",
            "营收", "变现", "促销", "优惠券", "直播带货", "客单价"],
    "内容": ["推文", "文章", "视频", "标题", "文案", "内容", "公众号", "脚本",
            "海报", "选题", "剪辑", "排版", "小红书", "抖音", "笔记", "直播"],
}

UNFINISHED_HINTS = ["未完成", "没做完", "没来得及", "还没", "待", "下周", "推迟",
                    "延期", "搁置", "计划", "准备", "打算", "遗留"]

BENCHMARK_TEMPLATES = {
    "用户增长": "通过{kw}等渠道动作系统化触达目标用户，{num}沉淀可复用的获客路径，参照行业基准预估可带来约10%-15%的新增用户环比提升空间。",
    "留存": "围绕用户活跃与留存开展{kw}精细化运营，{num}逐步建立分层触达SOP，对标行业25%-40%的社群周活跃基准持续优化留存漏斗。",
    "转化": "针对转化链路关键节点执行{kw}优化动作，{num}结合漏斗分析定位流失环节，参照行业5%-8%的私域转化基准推动成交效率提升。",
    "内容": "通过{kw}的内容生产与A/B迭代策略，{num}沉淀高点击率标题方法论，按行业基准预估可将点击/打开率提升约10%-20%。",
}


def split_items(text: str):
    """把口水话拆成条目：按换行、分号、句号及常见口语连接词切分。"""
    text = re.sub(r"(然后|接着|另外|还有|再就是|后来|周[一二三四五六日天][，、,：: ]?)", "\n", text)
    parts = re.split(r"[\n;；。]+", text)
    return [p.strip(" ，,、.．\t") for p in parts if len(p.strip()) >= 4]


def classify(item: str) -> str:
    best, score = "内容", 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        s = sum(1 for kw in kws if kw in item)
        if s > score:
            best, score = cat, s
    return best


def refine(item: str, category: str) -> str:
    # 仅提取"数量词"（如 5篇/3次/80人/40单），避免把价格(9.9元)误判为动作数量
    counts = re.findall(r"(\d+)\s*(?:多|余)?\s*(篇|条|次|个|场|人|单|款|份|部|轮|波)", item)
    kws = [kw for kw in CATEGORY_KEYWORDS[category] if kw in item][:2]
    kw_txt = "、".join(kws) if kws else "多项执行"
    num_txt = f"累计沉淀{counts[0][0]}{counts[0][1]}以上核心产出，" if counts else ""
    return BENCHMARK_TEMPLATES[category].format(kw=kw_txt, num=num_txt)


def rule_engine(text: str) -> dict:
    raw_items = split_items(text)
    items, unfinished = [], []
    for it in raw_items:
        if any(h in it for h in UNFINISHED_HINTS):
            unfinished.append(it)
            continue
        cat = classify(it)
        items.append({"category": cat, "raw": it, "refined": refine(it, cat)})
    if not items and raw_items:
        for it in raw_items:
            cat = classify(it)
            items.append({"category": cat, "raw": it, "refined": refine(it, cat)})

    next_week = []
    for uf in unfinished[:4]:
        clean = re.sub(r"^(下周|计划|准备|打算|待)+", "", uf).strip("，, ")
        next_week.append({
            "task": clean[:20] or "延续本周未完成事项",
            "goal": "本周内完成并沉淀可量化结果（目标完成率100%）",
            "actions": ["拆解任务节点并排期到天", "中期核对进度、及时暴露风险", "产出结果数据与复盘结论"],
        })
    if not next_week:
        next_week.append({
            "task": "延续本周核心动作并放大有效策略",
            "goal": "关键指标环比提升10%以上",
            "actions": ["复盘本周数据找到最优动作", "对高ROI动作加大投入", "补齐薄弱维度的基础动作"],
        })
    return {
        "items": items,
        "next_week": next_week,
        "summary": f"本周完成{len(items)}项核心运营动作，覆盖{len(set(i['category'] for i in items))}大维度，整体节奏可控。",
        }


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": bool(API_KEY), "model": MODEL_ID if API_KEY else "rule-engine"}


@app.post("/api/purify")
def purify(req: PurifyRequest):
    text = (req.text or "").strip()
    if len(text) < 10:
        return JSONResponse(status_code=400, content={"error": "请至少输入10个字的工作记录"})

    # 密钥优先级：访客自带密钥 > 服务端环境变量
    visitor_key = (req.api_key or "").strip()
    effective_key = visitor_key or API_KEY
    ai_error = ""

    if effective_key:
        try:
            data = call_ai(text, effective_key, (req.model or "").strip(), (req.base_url or "").strip())
            data["mode"] = "ai"
            data["key_source"] = "visitor" if visitor_key else "server"
            return data
        except Exception as e:
            traceback.print_exc()
            # 提炼简短错误原因（如 401 无效密钥），随降级结果告知前端
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg or "invalid" in msg.lower():
                ai_error = "API Key 无效或未授权，请检查密钥设置"
            elif "timeout" in msg.lower() or "timed out" in msg.lower():
                ai_error = "AI 请求超时，请稍后重试"
            elif "429" in msg:
                ai_error = "调用频率超限，请稍后重试"
            else:
                ai_error = "AI 调用失败：" + msg[:80]

    data = rule_engine(text)
    data["mode"] = "rule"
    if ai_error:
        data["ai_error"] = ai_error
    return data


class CheckRequest(BaseModel):
    api_key: str
    model: str = ""
    base_url: str = ""


@app.post("/api/check")
def check(req: CheckRequest):
    """连接自检：用访客提供的密钥/模型/地址做一次极简补全，验证可用性。"""
    key = (req.api_key or "").strip()
    if not key:
        return JSONResponse(status_code=400, content={"ok": False, "error": "未提供 API Key"})
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=(req.base_url or BASE_URL).strip(),
            api_key=key,
            timeout=30.0,
            max_retries=0,
        )
        model = (req.model or MODEL_ID).strip()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        reply = (resp.choices[0].message.content or "")[:60]
        return {"ok": True, "model": model, "reply": reply}
    except Exception as e:
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg or "invalid" in msg.lower():
            return {"ok": False, "error": "API Key 无效或未授权，请检查"}
        elif "404" in msg or ("not" in msg.lower() and "model" in msg.lower()):
            return {"ok": False, "error": "模型不存在或 Base URL 不正确，请检查"}
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            return {"ok": False, "error": "连接超时，请检查网络或 Base URL"}
        else:
            return {"ok": False, "error": msg[:120]}


if __name__ == "__main__":
    import uvicorn
    # 魔搭创空间要求服务监听 7860 端口
    uvicorn.run(app, host="0.0.0.0", port=7860)
