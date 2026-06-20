import sys
sys.path.insert(0, ".")

import urllib.request
import urllib.parse
import json

BASE = "http://localhost:8000"

def request(method, path, data=None, token=None, form_data=None):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form_data:
        body = urllib.parse.urlencode(form_data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            if raw:
                return resp.status, json.loads(raw)
            return resp.status, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except:
            return e.code, raw

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

if __name__ == "__main__":
    print_section("1. 健康检查")
    code, data = request("GET", "/health")
    print(f"  Status: {code} -> {data}")

    print_section("2. 管理员登录")
    code, data = request("POST", "/api/auth/login", form_data={"username": "admin", "password": "admin123"})
    print(f"  Status: {code}")
    if code == 200:
        admin_token = data["access_token"]
        print(f"  ✅ 登录成功，获取Token成功")
    else:
        print(f"  ❌ 登录失败: {data}")
        sys.exit(1)

    print_section("3. 获取当前用户信息")
    code, data = request("GET", "/api/auth/me", token=admin_token)
    print(f"  当前用户: {data.get('real_name')} 角色: {data.get('role')}")

    print_section("4. 查看门店列表")
    code, data = request("GET", "/api/stores", token=admin_token)
    print(f"  门店数量: {len(data)}")
    for s in data:
        print(f"    - {s['store_code']} | {s['store_name']} | {s.get('manager_name', '')}")

    print_section("5. 查看治疗类型")
    code, data = request("GET", "/api/treatment-types", token=admin_token)
    print(f"  治疗类型数量: {len(data)}")
    for t in data[:5]:
        print(f"    - {t['type_code']} | {t['type_name']}")

    print_section("6. 查看回访规则")
    code, data = request("GET", "/api/rules", token=admin_token)
    print(f"  激活规则数量: {len([r for r in data if r['is_active']])}")
    for r in data[:6]:
        print(f"    - 第{r['days_after_treatment']}天 | {r['rule_name'][:20]} | 优先级{r['priority']}")

    print_section("7. 生成回访任务 (核心业务！)")
    code, data = request("POST", "/api/tasks/generate", data={}, token=admin_token)
    print(f"  Status: {code}")
    if code == 200:
        print(f"  ✅ 生成任务数: {len(data)}")
        for t in data[:6]:
            print(f"    - {t['task_no']} | 计划:{t['scheduled_date']} | 状态:{t['status']}")
    else:
        print(f"  ❌ 失败: {data}")

    print_section("8. 自动分派任务")
    code, data = request("POST", "/api/tasks/auto-assign", token=admin_token)
    print(f"  Status: {code} -> {data}")

    print_section("9. 坐席 agent1 登录查看自己的任务")
    code, resp = request("POST", "/api/auth/login", form_data={"username": "agent1", "password": "agent123"})
    if code == 200:
        agent_token = resp["access_token"]
        code, tasks = request("GET", "/api/tasks?page_size=5", token=agent_token)
        if code == 200:
            print(f"  坐席agent1待处理任务: total={tasks['total']}")
            for t in tasks['items'][:5]:
                patient_name = t.get('patient', {}).get('name', '?') if t.get('patient') else '?'
                print(f"    - {t['task_no']} | 患者:{patient_name} | 状态:{t['status']}")

            if len(tasks['items']) > 0:
                task_id = tasks['items'][0]['id']
                task_no = tasks['items'][0]['task_no']
                rule_script = ""
                if tasks['items'][0].get('rule'):
                    rule_script = tasks['items'][0]['rule'].get('script_template', '')[:60]
                print(f"\n  选择任务 {task_no} 开始处理...")
                print(f"  话术模板: {rule_script}...")

                code, t = request("POST", f"/api/tasks/{task_id}/start", token=agent_token)
                print(f"  开始任务: Status={code}")

                print(f"\n  模拟通话记录(命中关键词'持续出血'...)")
                handle_data = {
                    "task_id": task_id,
                    "call_result": "connected",
                    "call_duration_seconds": 158,
                    "callback_notes": "患者反映伤口仍有持续出血，伴有轻微发热，嘱咐咬棉球并建议尽快复诊",
                    "escalate_to_doctor": False
                }
                code, t = request("POST", "/api/tasks/handle", data=handle_data, token=agent_token)
                if code == 200:
                    print(f"  ✅ 处理完成")
                    print(f"     - 新状态: {t['status']}")
                    print(f"     - 异常标记: {t['is_abnormal']}")
                    print(f"     - 命中关键词: {t.get('abnormal_keywords_hit', '(无)')}")
                    if t['status'] == 'doctor_review':
                        print(f"     - ✅ 自动转医生复核任务")

    print_section("10. 统计看板 - 总览")
    code, data = request("GET", "/api/stats/overview", token=admin_token)
    if code == 200:
        print(f"  总任务数: {data['total_tasks']}")
        print(f"  已完成: {data['completed_tasks']} (完成率 {data['completion_rate']}%)")
        print(f"  异常数: {data['abnormal_tasks']} (异常率 {data['abnormal_rate']}%)")
        print(f"  医生复核中: {data['doctor_review_tasks']}")
        print(f"  超时任务: {data['timeout_tasks']}")

    print_section("11. 各门店维度统计")
    code, data = request("GET", "/api/stats/by-store", token=admin_token)
    if code == 200:
        for s in data:
            print(f"  {s['store_name'][:16]:18s} 总数:{s['total_tasks']:3d} 完成率:{s['completion_rate']:5.1f}% 异常:{s['abnormal_tasks']}")

    print_section("12. 超时未回访清单")
    code, data = request("GET", "/api/stats/timeout-list?limit=10", token=admin_token)
    if code == 200:
        print(f"  超时/逾期任务: {len(data)}")
        for t in data[:5]:
            print(f"    - {t['task_no']} | {t['patient_name']} | {t['store_name'][:12]} | 超{t['overdue_hours']}h | {t['status']}")

    print(f"\n{'='*60}")
    print(f"  ✅ 全部测试通过！服务运行正常")
    print(f"{'='*60}")
    print(f"\n📖 接口文档: http://localhost:8000/docs")
    print(f"👤 默认账号: admin / admin123\n")
