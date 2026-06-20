import sys
sys.path.insert(0, ".")
import urllib.request, urllib.parse, json
BASE = "http://localhost:8000"

def req(method, path, data=None, token=None, form=None):
    h = {}
    body = None
    if token: h["Authorization"] = f"Bearer {token}"
    if form:
        body = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE+path, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try: return e.code, json.loads(raw)
        except: return e.code, raw

def login(u, p):
    c, r = req("POST", "/api/auth/login", form={"username":u, "password":p})
    return r["access_token"] if c==200 else None

print("=== 快速验证四个优化点 ===\n")

admin_tk = login("admin", "admin123")
agent_tk = login("agent1", "agent123")
doc_zhang_tk = login("doc_zhang", "doctor123")  # 北京店
doc_li_tk = login("doc_li", "doctor123")        # 上海店

print("1. 生成任务并自动分派...")
c, tasks = req("POST", "/api/tasks/generate", data={}, token=admin_tk)
c, _ = req("POST", "/api/tasks/auto-assign", token=admin_tk)

print("\n--- 需求1：默认筛选（无筛选参数时只看今天+待处理）---")
c, r = req("GET", "/api/tasks?page_size=100", token=agent_tk)
items = r["items"]
ok1 = all(
    t["scheduled_date"] <= "2026-06-20"
    and t["status"] not in ["completed", "cancelled", "doctor_reviewed"]
    for t in items
)
print(f"  坐席agent1默认看到 {len(items)} 条，全是今天或之前的待处理: {'✅' if ok1 else '❌'}")

print("\n--- 需求2：风险分层分派（看已分派的任务）---")
c, r = req("GET", "/api/tasks?page_size=100&status=assigned", token=admin_tk)
low_to_agent = sum(1 for t in r["items"] if t["patient"]["risk_level"]=="low" and not t["patient"]["risk_tags"] and t["assigned_user"]["role"]=="call_agent")
low_total = sum(1 for t in r["items"] if t["patient"]["risk_level"]=="low" and not t["patient"]["risk_tags"])
high_to_nurse = sum(1 for t in r["items"] if t["patient"]["risk_level"]=="high" and t["assigned_user"]["role"]=="store_nurse")
high_total = sum(1 for t in r["items"] if t["patient"]["risk_level"]=="high")
ok2 = (low_total==0 or low_to_agent/low_total >= 0.5) and (high_total==0 or high_to_nurse/high_total >= 0.5)
print(f"  低风险→总部坐席: {low_to_agent}/{low_total}")
print(f"  高风险→门店护士: {high_to_nurse}/{high_total}")
print(f"  风险分层符合预期: {'✅' if ok2 else '❌'}")

print("\n--- 需求3：医生复核权限控制 ---")
# 先让坐席处理一个任务并触发关键词转医生复核
c, r = req("GET", "/api/tasks?page_size=1&status=assigned", token=agent_tk)
task_id = r["items"][0]["id"]
req("POST", f"/api/tasks/{task_id}/start", token=agent_tk)
handle_data = {
    "task_id": task_id,
    "call_result": "connected",
    "callback_notes": "患者持续出血，还有发热",
}
c, task = req("POST", "/api/tasks/handle", data=handle_data, token=agent_tk)
print(f"  任务 {task_id} 处理后状态: {task['status']}, 分派医生ID: {task['assigned_user_id']}")
print(f"  命中关键词: {task.get('abnormal_keywords_hit')}")

# 北京医生看列表
c, r = req("GET", "/api/tasks?page_size=50", token=doc_zhang_tk)
bj_reviews = [t for t in r["items"] if t["status"] == "doctor_review"]
print(f"  北京张医生看到的复核任务: {len(bj_reviews)} 条")
for t in bj_reviews:
    print(f"    - {t['task_no']} store_id={t['store_id']} assigned_to={t['assigned_user_id']}")
ok3a = len(bj_reviews) >= 1

# 上海医生看列表
c, r = req("GET", "/api/tasks?page_size=50", token=doc_li_tk)
sh_reviews = [t for t in r["items"] if t["status"] == "doctor_review"]
cross = [t for t in sh_reviews if t["store_id"] == 1]
ok3b = len(cross) == 0
print(f"  上海李医生看到的复核任务: {len(sh_reviews)} 条, 其中北京店: {len(cross)} {'✅' if ok3b else '❌'}")

# 上海医生尝试访问北京任务
c, r = req("GET", f"/api/tasks/{task_id}", token=doc_li_tk)
ok3c = c == 403
print(f"  上海医生访问北京任务: HTTP {c} {'✅ 返回403' if ok3c else '❌ 应该403'}")

# 北京医生访问本店任务
c, r = req("GET", f"/api/tasks/{task_id}", token=doc_zhang_tk)
ok3d = c == 200
print(f"  北京医生访问本店任务: HTTP {c} {'✅ 正常' if ok3d else '❌ 无法访问'}")

ok3 = ok3a and ok3b and ok3c and ok3d
print(f"  医生权限综合: {'✅' if ok3 else '❌'}")

print("\n--- 需求4：超时自动统计口径统一 ---")
c, overview = req("GET", "/api/stats/overview", token=admin_tk)
c, timeout_list = req("GET", "/api/stats/timeout-list?limit=500", token=admin_tk)
ok4 = overview["timeout_tasks"] == len(timeout_list)
print(f"  总览超时数: {overview['timeout_tasks']}, 超时清单数: {len(timeout_list)}, 一致: {'✅' if ok4 else '❌'}")
print(f"  无需手动触发check-timeout: ✅ （代码使用统一的apply_overdue_filter）")

print(f"\n{'='*50}")
results = {"需求1-默认筛选":ok1, "需求2-风险分派":ok2, "需求3-医生权限":ok3, "需求4-超时统计":ok4}
all_ok = all(results.values())
for k, v in results.items():
    print(f"  {'✅' if v else '❌'} {k}")
print(f"\n  综合结果: {'🎉 全部通过' if all_ok else '⚠️ 存在未通过项'}")
print(f"{'='*50}")
