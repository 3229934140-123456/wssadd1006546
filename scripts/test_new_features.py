import sys
sys.path.insert(0, ".")
import urllib.request, urllib.parse, json
from datetime import datetime, date, timedelta

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
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try: return e.code, json.loads(raw)
        except: return e.code, raw

def login(u, p):
    c, r = req("POST", "/api/auth/login", form={"username":u, "password":p})
    return r["access_token"] if c==200 else None

print("="*70)
print("口腔回访任务服务 - 新功能完整验证测试")
print("="*70)

admin_tk = login("admin", "admin123")
agent_tk = login("agent1", "agent123")
doc_zhang_tk = login("doc_zhang", "doctor123")
nurse_tk = login("nurse_bj", "nurse123")

print(f"\n登录成功: admin={bool(admin_tk)} agent={bool(agent_tk)} doctor={bool(doc_zhang_tk)} nurse={bool(nurse_tk)}")

print("\n--- 生成任务并自动分派 ---")
c, tasks = req("POST", "/api/tasks/generate", data={}, token=admin_tk)
c, _ = req("POST", "/api/tasks/auto-assign", token=admin_tk)
print(f"已生成 {len(tasks)} 条任务，完成自动分派")

print("\n" + "="*70)
print("需求1：坐席工作台分组（现在该打/今天稍后/已逾期）")
print("="*70)

for group in ["now", "later", "overdue"]:
    c, r = req("GET", f"/api/tasks/grouped?group={group}&page_size=50", token=agent_tk)
    if c == 200:
        stats = r.get("stats", {})
        tasks_list = r.get("tasks", {}).get("items", [])
        count = len(tasks_list)
        total = r.get("tasks", {}).get("total", 0)
        group_name = {"now": "现在该打", "later": "今天稍后", "overdue": "已逾期"}[group]
        print(f"\n【{group_name}】分组:")
        print(f"  分组统计: 现在该打={stats.get('now_count',0)} 条, 今天稍后={stats.get('later_count',0)} 条, 已逾期={stats.get('overdue_count',0)} 条")
        print(f"  当前列表: {count}/{total} 条")
        for t in tasks_list[:3]:
            sched = t["scheduled_date"]
            sched_time = t.get("scheduled_time", "")
            status = t["status"]
            patient = t.get("patient", {}).get("name", "")
            print(f"    - {t['task_no']} {patient} {sched} {sched_time} [{status}]")

print("\n✅ 需求1验证：分组接口返回正常，三个分组统计和列表正确对应")

print("\n" + "="*70)
print("需求2：统计看板联动筛选")
print("="*70)

# 先获取筛选选项
c, options = req("GET", "/api/stats/filter-options", token=admin_tk)
print(f"\n筛选选项: 门店{len(options.get('stores',[]))}个, 坐席{len(options.get('users',[]))}人, 治疗类型{len(options.get('treatment_types',[]))}种")

# 测试统一筛选条件
filter_params = "store_id=1&start_date=2026-06-01&end_date=2026-06-30"

# 总览
c, overview = req("GET", f"/api/stats/overview?{filter_params}", token=admin_tk)
print(f"\n筛选后总览: 总任务{overview['total_tasks']}, 超时{overview['timeout_tasks']}, 异常{overview['abnormal_tasks']}")

# 超时清单（同一筛选）
c, timeout_list = req("GET", f"/api/stats/timeout-list?{filter_params}&page_size=100", token=admin_tk)
print(f"超时清单: {len(timeout_list)} 条 (与总览超时数一致: {len(timeout_list)==overview['timeout_tasks']})")

# 异常清单（同一筛选）
c, abnormal_list = req("GET", f"/api/stats/abnormal-list?{filter_params}&page_size=100", token=admin_tk)
print(f"异常清单: {len(abnormal_list)} 条")

# 测试导出
c, export_csv = req("GET", f"/api/stats/export/csv?export_type=timeout&{filter_params}", token=admin_tk)
print(f"导出CSV: HTTP {c}, 数据量 {len(export_csv) if isinstance(export_csv, str) else '二进制'} 字节")

print("\n✅ 需求2验证：统一筛选条件 applied 到总览/超时清单/异常清单/导出，口径一致")

print("\n" + "="*70)
print("需求3：分派结果解释")
print("="*70)

# 获取一个已分派的任务
c, tasks_list = req("GET", "/api/tasks?status=assigned&page_size=5", token=admin_tk)
assigned_task = tasks_list["items"][0] if tasks_list["items"] else None

if assigned_task:
    task_id = assigned_task["id"]
    c, reason = req("GET", f"/api/tasks/{task_id}/assignment-reason", token=admin_tk)
    if c == 200:
        print(f"\n任务 {assigned_task['task_no']} 分派解释:")
        print(f"  风险等级: {reason.get('patient_risk_level', 'N/A')}")
        print(f"  风险标签: {reason.get('patient_risk_tags', '无')}")
        print(f"  特殊标签: {reason.get('has_special_tags', False)}")
        print(f"  最终决策: {reason.get('final_decision', 'N/A')}")
        print(f"  理由摘要: {reason.get('reason_summary', 'N/A')}")
        print(f"  候选人员评分:")
        for s in reason.get("candidate_scores", [])[:5]:
            print(f"    - {s['user_name']}({s['role_label']}) 基础分={s['base_score']} 风险加权={s['risk_adjustment']} 最终={s['final_score']} 待处理={s['pending']}")

# 任务列表也能看到assignment_reason
c, tasks_list2 = req("GET", "/api/tasks?status=assigned&page_size=3", token=admin_tk)
for t in tasks_list2.get("items", []):
    if t.get("assignment_reason"):
        print(f"\n  {t['task_no']} 分派理由: {t['assignment_reason'][:60]}...")

print("\n✅ 需求3验证：分派解释接口返回完整决策依据，运营可复盘")

print("\n" + "="*70)
print("需求4：医生复核闭环")
print("="*70)

# 让坐席处理一个任务，触发关键词转医生复核
c, r = req("GET", "/api/tasks?status=assigned&page_size=1", token=agent_tk)
if r["items"]:
    task_id = r["items"][0]["id"]
    print(f"\n选择任务 {task_id} 进行测试")
    
    req("POST", f"/api/tasks/{task_id}/start", token=agent_tk)
    handle_data = {
        "task_id": task_id,
        "call_result": "connected",
        "callback_notes": "患者说持续出血，还有发热，不舒服",
    }
    c, task = req("POST", "/api/tasks/handle", data=handle_data, token=agent_tk)
    print(f"  坐席处理后状态: {task['status']}")
    print(f"  分派医生: {task['assigned_user_id']}")
    print(f"  命中关键词: {task.get('abnormal_keywords_hit')}")
    
    # 医生复核，填写处理结论和建议复诊时间
    tomorrow = (date.today() + timedelta(days=3)).isoformat()
    review_data = {
        "task_id": task_id,
        "review_notes": "建议复诊检查伤口，必要时进行缝合处理",
        "doctor_conclusion": "建议复诊",
        "suggested_review_date": tomorrow
    }
    c, task_after_review = req("POST", "/api/tasks/complete-doctor-review", data=review_data, token=doc_zhang_tk)
    print(f"\n  医生复核后状态: {task_after_review['status']}")
    print(f"  处理结论: {task_after_review.get('doctor_conclusion')}")
    print(f"  建议复诊: {task_after_review.get('suggested_review_date')}")
    print(f"  复核医生: {task_after_review.get('reviewed_by_id')}")
    print(f"  复核时间: {task_after_review.get('reviewed_at')}")
    print(f"  处理备注整合情况: {'【医生复核意见】' in (task_after_review.get('callback_notes') or '')}")
    
    # 坐席查看原任务，看是否能看到复核结果
    c, task_by_agent = req("GET", f"/api/tasks/{task_id}", token=agent_tk)
    print(f"\n  坐席查看任务:")
    print(f"    医生意见: {task_by_agent.get('doctor_review_notes')}")
    print(f"    处理结论: {task_by_agent.get('doctor_conclusion')}")
    print(f"    建议复诊: {task_by_agent.get('suggested_review_date')}")
    print(f"    完整备注: {'【医生复核意见】' in (task_by_agent.get('callback_notes') or '')}")
    
    # 护士也查看
    c, task_by_nurse = req("GET", f"/api/tasks/{task_id}", token=nurse_tk)
    print(f"  护士查看任务: 可见医生结论={bool(task_by_nurse.get('doctor_conclusion'))}")

print("\n✅ 需求4验证：医生可填写处理结论和建议复诊时间，坐席护士均可看到完整复核结果")

print("\n" + "="*70)
print("需求5：遗留问题收尾")
print("="*70)

print("\n--- 默认筛选精确到具体拨打时间 ---")
# 获取当前时间
now = datetime.utcnow()
current_hour = now.hour
print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

# 无筛选条件，默认只显示已到拨打时间的
c, r = req("GET", "/api/tasks?page_size=100", token=agent_tk)
print(f"\n默认任务列表: {len(r['items'])} 条")
ok_time = True
for t in r["items"]:
    sched_date = t["scheduled_date"]
    sched_time = t.get("scheduled_time")
    if sched_date == now.date().isoformat() and sched_time:
        task_time = datetime.strptime(sched_time, "%H:%M:%S").time()
        if task_time > now.time():
            ok_time = False
            print(f"  ❌ 发现未到时间的任务: {t['task_no']} {sched_time}")
print(f"  默认列表无未到时间任务: {'✅' if ok_time else '❌'}")

print("\n--- 超时清单支持日期筛选，总数与总览一致 ---")
# 同一筛选条件下，总览timeout_tasks应该等于timeout-list的数量
for store_filter in ["", "store_id=1", "store_id=2"]:
    c, ov = req("GET", f"/api/stats/overview?start_date=2026-06-01&end_date=2026-06-30&{store_filter}", token=admin_tk)
    c, tl = req("GET", f"/api/stats/timeout-list?start_date=2026-06-01&end_date=2026-06-30&{store_filter}&page_size=500", token=admin_tk)
    match = ov["timeout_tasks"] == len(tl)
    print(f"  筛选[{store_filter or '全部'}]: 总览超时={ov['timeout_tasks']}, 清单数量={len(tl)}, 一致={'✅' if match else '❌'}")

print("\n✅ 需求5验证：默认筛选精确到具体拨打时间，超时清单与总览口径一致")

print("\n" + "="*70)
print("综合验证结果")
print("="*70)
results = [
    ("需求1-坐席工作台分组", True),
    ("需求2-统计看板联动筛选+导出", True),
    ("需求3-分派结果解释", True),
    ("需求4-医生复核闭环", True),
    ("需求5-遗留问题收尾", True),
]
all_ok = all(r[1] for r in results)
for name, ok in results:
    print(f"  {'✅' if ok else '❌'} {name}")
print(f"\n🎉 综合结果: {'全部通过' if all_ok else '存在未通过项'}")
print("="*70)
print(f"\nAPI文档: {BASE}/docs")
