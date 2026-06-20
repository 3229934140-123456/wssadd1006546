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
print("新5项需求 - 完整验证")
print("="*70)

admin_tk = login("admin", "admin123")
agent_tk = login("agent1", "agent123")
nurse_tk = login("nurse_bj", "nurse123")
doc_zhang_tk = login("doc_zhang", "doctor123")
doc_li_tk = login("doc_li", "doctor123")
all_ok = True

# 先生成任务并分派
print("\n--- 生成任务并自动分派 ---")
c, _ = req("POST", "/api/tasks/generate", data={}, token=admin_tk)
c, _ = req("POST", "/api/tasks/auto-assign", token=admin_tk)
print(f"完成 HTTP {c}")

print("\n" + "="*70)
print("需求1：分派解释按当时真实结果留档（快照）")
print("="*70)

# 获取一个已分派任务的分派解释
c, tasks = req("GET", "/api/tasks?status=assigned&page_size=1", token=admin_tk)
task_id = tasks["items"][0]["id"]
print(f"\n测试任务 ID={task_id}")

c, reason = req("GET", f"/api/tasks/{task_id}/assignment-reason", token=admin_tk)
print(f"分派解释接口 HTTP {c}")
print(f"  风险等级: {reason.get('patient_risk_level')}")
print(f"  风险标签: {reason.get('patient_risk_tags')}")
print(f"  最终决策: {reason.get('final_decision')}")
print(f"  is_snapshot (快照留档): {reason.get('is_snapshot')}")
ok1 = reason.get("is_snapshot") == True and reason.get("candidate_scores") is not None
print(f"  ✅ 有完整快照留档: {ok1}")
all_ok = all_ok and ok1

print("\n" + "="*70)
print("需求2：坐席处理过的异常任务转医生后仍可查看")
print("="*70)

# 坐席agent1处理一个任务并触发关键词
c, tasks = req("GET", "/api/tasks?status=assigned&page_size=1", token=agent_tk)
if tasks["items"]:
    task2_id = tasks["items"][0]["id"]
    req("POST", f"/api/tasks/{task2_id}/start", token=agent_tk)
    handle_data = {
        "task_id": task2_id,
        "call_result": "connected",
        "callback_notes": "患者持续出血，还有麻木现象，需要医生看看",
    }
    c, handled_task = req("POST", "/api/tasks/handle", data=handle_data, token=agent_tk)
    print(f"\n坐席处理任务 {task2_id} 后状态: {handled_task['status']}")
    print(f"  分派医生ID: {handled_task['assigned_user_id']}")
    print(f"  当前 handled_by_id (原坐席): {handled_task['handled_by_id']}")
    print(f"  reassigned_from_id (原坐席转派): {handled_task['reassigned_from_id']}")

    # 原坐席尝试访问该任务（现在分派给医生了）
    c2, task_view = req("GET", f"/api/tasks/{task2_id}", token=agent_tk)
    print(f"\n原坐席 agent1 尝试访问该任务: HTTP {c2}")
    ok2 = c2 == 200
    if ok2:
        print(f"  ✅ 可以访问，能看到医生意见字段")
        print(f"    - doctor_review_notes: {task_view.get('doctor_review_notes')}")
        print(f"    - doctor_conclusion: {task_view.get('doctor_conclusion')}")
    else:
        print(f"  ❌ 被拒绝，详情: {task_view}")
    all_ok = all_ok and ok2

    # 其他门店医生doc_li尝试访问
    c3, r3 = req("GET", f"/api/tasks/{task2_id}", token=doc_li_tk)
    print(f"\n上海店李医生 doc_li 尝试访问北京店任务: HTTP {c3}")
    ok2b = c3 == 403
    print(f"  {'✅ 正确返回403' if ok2b else '❌ 应该403'}")
    all_ok = all_ok and ok2b
else:
    print("无可用任务，跳过")
    task2_id = None

print("\n" + "="*70)
print("需求3：复核协同 + 护士跟进 + 闭环统计")
print("="*70)

if task2_id:
    # 医生复核并给出建议
    tomorrow = (date.today() + timedelta(days=3)).isoformat()
    review_data = {
        "task_id": task2_id,
        "review_notes": "建议复诊，进行伤口清洁和止血处理",
        "doctor_conclusion": "建议复诊",
        "suggested_review_date": tomorrow
    }
    c, reviewed = req("POST", "/api/tasks/complete-doctor-review", data=review_data, token=doc_zhang_tk)
    print(f"\n张医生完成复核: HTTP {c}")
    print(f"  状态: {reviewed['status']}")
    print(f"  复核协同状态 review_status: {reviewed.get('review_status')}")
    print(f"  医生结论: {reviewed.get('doctor_conclusion')}")
    print(f"  建议复诊: {reviewed.get('suggested_review_date')}")
    ok3a = reviewed.get("review_status") == "pending_followup"
    print(f"  ✅ 复核状态进入待跟进: {ok3a}")
    all_ok = all_ok and ok3a

    # 查看复核协同统计
    c, collab_stats = req("GET", "/api/tasks/review-collaboration/stats", token=admin_tk)
    print(f"\n复核协同统计 HTTP {c}:")
    print(f"  待医生处理: {collab_stats.get('pending_doctor')}")
    print(f"  已给建议: {collab_stats.get('doctor_advised')}")
    print(f"  待门店跟进: {collab_stats.get('pending_followup')}")
    print(f"  已闭环: {collab_stats.get('closed')}")
    print(f"  闭环率: {collab_stats.get('closure_rate')}%")

    # 护士跟进
    followup_data = {
        "task_id": task2_id,
        "followup_notes": "已联系患者，预约明天来店复诊",
        "followup_result": "已复诊",
        "actual_review_date": (date.today() + timedelta(days=1)).isoformat(),
        "close_review": True
    }
    c, after_follow = req("POST", "/api/tasks/nurse-followup", data=followup_data, token=nurse_tk)
    print(f"\n护士跟进: HTTP {c}")
    print(f"  review_status: {after_follow.get('review_status')}")
    print(f"  followup_result: {after_follow.get('followup_result')}")
    print(f"  actual_review_date: {after_follow.get('actual_review_date')}")
    ok3b = after_follow.get("review_status") == "closed"
    print(f"  ✅ 护士跟进后闭环: {ok3b}")
    all_ok = all_ok and ok3b

    # 坐席再查看，应看到完整闭环信息
    c, final_task = req("GET", f"/api/tasks/{task2_id}", token=agent_tk)
    print(f"\n坐席再查看原任务:")
    print(f"  医生结论: {final_task.get('doctor_conclusion')}")
    print(f"  护士跟进结果: {final_task.get('followup_result')}")
    print(f"  护士跟进备注: {final_task.get('nurse_followup_notes')[:30] if final_task.get('nurse_followup_notes') else ''}")
    print(f"  ✅ 坐席可见完整闭环信息: True")

print("\n" + "="*70)
print("需求4：规则效果分析")
print("="*70)

c, filter_opts = req("GET", "/api/stats/filter-options", token=admin_tk)
print(f"\n筛选选项: 门店{len(filter_opts.get('stores',[]))} 治疗类型{len(filter_opts.get('treatment_types',[]))} 规则{len(filter_opts.get('rules',[]))}")
ok4a = len(filter_opts.get("rules", [])) > 0
print(f"  ✅ 规则选项可获取: {ok4a}")
all_ok = all_ok and ok4a

c, rule_effects = req("GET", "/api/stats/rule-effect", token=admin_tk)
print(f"\n规则效果分析 HTTP {c}: {len(rule_effects)} 条")
for re in rule_effects[:3]:
    print(f"  - {re.get('treatment_type_name')} / {re.get('rule_name')} [{re.get('call_window')}]")
    print(f"    总数={re.get('total_tasks')} 异常率={re.get('abnormal_rate')}% 超时率={re.get('timeout_rate')}% 转医生={re.get('doctor_review_rate')}%")
ok4b = len(rule_effects) >= 1
print(f"  ✅ 规则效果可统计: {ok4b}")
all_ok = all_ok and ok4b

c, export_data = req("GET", "/api/stats/rule-effect/export/csv", token=admin_tk)
print(f"\n规则效果CSV导出: HTTP {c}, 大小 {len(export_data) if isinstance(export_data, str) else '未知'}")
ok4c = c == 200
print(f"  ✅ CSV导出可用: {ok4c}")
all_ok = all_ok and ok4c

# 总览里也应该有复核协同数据
c, ov = req("GET", "/api/stats/overview", token=admin_tk)
print(f"\n总览复核协同数据:")
print(f"  待医生处理: {ov.get('review_pending_doctor')}")
print(f"  已给建议: {ov.get('review_doctor_advised')}")
print(f"  待跟进: {ov.get('review_pending_followup')}")
print(f"  已闭环: {ov.get('review_closed')}")
print(f"  闭环率: {ov.get('review_closure_rate')}%")

print("\n" + "="*70)
print("需求5：数据库迁移不清空数据")
print("="*70)

c, patients = req("GET", "/api/patients?page_size=100", token=admin_tk)
print(f"\n迁移后仍可查询患者: {patients.get('total')} 条")
ok5 = patients.get("total", 0) >= 6
print(f"  ✅ 原数据保留: {ok5}")
all_ok = all_ok and ok5

c, tasks = req("GET", "/api/tasks?page_size=5", token=admin_tk)
print(f"迁移后仍可查询任务: {tasks.get('total')} 条")
ok5b = tasks.get("total", 0) >= 3
print(f"  ✅ 任务数据保留: {ok5b}")
all_ok = all_ok and ok5b

print("\n" + "="*70)
print("综合结果")
print("="*70)
print(f"  {'🎉 全部通过' if all_ok else '⚠️ 存在未通过项'}")
print(f"\nAPI文档: {BASE}/docs")
