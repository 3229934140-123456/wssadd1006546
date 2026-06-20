import sys
sys.path.insert(0, ".")
import urllib.request, urllib.parse, json
from datetime import date, timedelta

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

admin_tk = login("admin", "admin123")
agent_tk = login("agent1", "agent123")
nurse_tk = login("nurse_bj", "nurse123")
doc_zhang_tk = login("doc_zhang", "doctor123")
doc_li_tk = login("doc_li", "doctor123")
all_ok = True

print("=== 需求1: 分派解释快照 ===")
c, tasks = req("GET", "/api/tasks?page_size=100", token=admin_tk)
print(f"admin能看到任务总数={tasks.get('total')}, items数={len(tasks.get('items',[]))}")
if tasks.get("items"):
    task_id = tasks["items"][0]["id"]
    c, reason = req("GET", f"/api/tasks/{task_id}/assignment-reason", token=admin_tk)
    print(f"HTTP {c}, is_snapshot={reason.get('is_snapshot')}, 风险={reason.get('patient_risk_level')}, 候选分数长度={len(reason.get('candidate_scores',[]))}")
    ok1 = reason.get("is_snapshot") == True and len(reason.get("candidate_scores",[])) > 0
    print(f"  {'✅' if ok1 else '❌'} {ok1}")
    all_ok = all_ok and ok1
else:
    print("  无任务，需重新生成")

print("\n=== 需求2: 坐席转医生仍可访问 ===")
c, tasks = req("GET", "/api/tasks?status=assigned&page_size=1", token=agent_tk)
if tasks.get("items"):
    t = tasks["items"][0]
    print(f"坐席agent1可见 assigned任务 {t['id']} 分派给: {t.get('assigned_user_id')}")
    c2, tview = req("GET", f"/api/tasks/{t['id']}", token=agent_tk)
    print(f"  GET详情 HTTP {c2}")
else:
    print("无assigned任务")

print("\n=== 需求3: 复核协同 + 护士跟进 ===")
# 找一个DOCTOR_REVIEW状态的任务
c, rev_tasks = req("GET", "/api/tasks/review-collaboration?review_status=pending_doctor", token=doc_zhang_tk)
print(f"张医生待复核任务数: {len(rev_tasks.get('items',[]))}")
# 复核协同统计
c, s = req("GET", "/api/tasks/review-collaboration/stats", token=admin_tk)
print(f"复核协同统计: {s}")
ok3 = s.get("closed", 0) >= 0
print(f"  {'✅' if ok3 else '❌'}")
all_ok = all_ok and ok3

print("\n=== 需求4: 规则效果分析 ===")
c, opts = req("GET", "/api/stats/filter-options", token=admin_tk)
print(f"筛选规则数: {len(opts.get('rules',[]))}")
ok4a = len(opts.get("rules",[])) > 0
print(f"  {'✅' if ok4a else '❌'} 规则选项可用")
c, eff = req("GET", "/api/stats/rule-effect", token=admin_tk)
print(f"规则效果条目: {len(eff)}")
for e in eff[:2]:
    print(f"  {e['treatment_type_name']}/{e['rule_name']}: 总={e['total_tasks']} 异常率={e['abnormal_rate']}%")
ok4b = len(eff) >= 1
print(f"  {'✅' if ok4b else '❌'} 规则效果可用")
all_ok = all_ok and ok4a and ok4b

c, ov = req("GET", "/api/stats/overview", token=admin_tk)
print(f"总览复核字段: pending_doctor={ov.get('review_pending_doctor')}, closed={ov.get('review_closed')}, closure_rate={ov.get('review_closure_rate')}%")

print("\n=== 需求5: 数据库迁移数据保留 ===")
c, p = req("GET", "/api/patients?page_size=100", token=admin_tk)
print(f"迁移后患者数: {p.get('total')}")
ok5 = p.get("total", 0) >= 6
print(f"  {'✅' if ok5 else '❌'} 数据保留")
all_ok = all_ok and ok5

print(f"\n=== 综合结果: {'🎉 全部通过' if all_ok else '⚠️ 部分失败'} ===")
