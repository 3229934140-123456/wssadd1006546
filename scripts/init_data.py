import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal, Base, engine
from app.security import hash_password
from app.models import (
    User, UserRole, Store, Patient, Gender, RiskLevel,
    TreatmentType, TreatmentRecord, CallbackRule, CallTimeWindow
)


def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("开始初始化数据...")

        stores = [
            Store(store_code="ST001", store_name="微笑口腔-北京朝阳店", address="北京市朝阳区建国路88号", contact_phone="010-88880001", manager_name="张经理"),
            Store(store_code="ST002", store_name="微笑口腔-上海浦东店", address="上海市浦东新区陆家嘴环路100号", contact_phone="021-66660002", manager_name="李经理"),
            Store(store_code="ST003", store_name="微笑口腔-广州天河店", address="广州市天河区珠江新城200号", contact_phone="020-33330003", manager_name="王经理"),
        ]
        db.add_all(stores)
        db.commit()
        store_map = {s.store_code: s.id for s in stores}
        print(f"  - 创建 {len(stores)} 家门店")

        users = [
            User(username="admin", real_name="系统管理员", email="admin@smile-dental.com", hashed_password=hash_password("admin123"), role=UserRole.ADMIN, store_id=None),
            User(username="agent1", real_name="王小红", email="agent1@smile-dental.com", hashed_password=hash_password("agent123"), role=UserRole.CALL_AGENT, store_id=None),
            User(username="agent2", real_name="刘雅婷", email="agent2@smile-dental.com", hashed_password=hash_password("agent123"), role=UserRole.CALL_AGENT, store_id=None),
            User(username="nurse_bj", real_name="陈护士", email="nurse_bj@smile-dental.com", hashed_password=hash_password("nurse123"), role=UserRole.STORE_NURSE, store_id=store_map["ST001"]),
            User(username="nurse_sh", real_name="周护士", email="nurse_sh@smile-dental.com", hashed_password=hash_password("nurse123"), role=UserRole.STORE_NURSE, store_id=store_map["ST002"]),
            User(username="doc_zhang", real_name="张医生", email="zhang@smile-dental.com", hashed_password=hash_password("doctor123"), role=UserRole.DOCTOR, store_id=store_map["ST001"]),
            User(username="doc_li", real_name="李医生", email="li@smile-dental.com", hashed_password=hash_password("doctor123"), role=UserRole.DOCTOR, store_id=store_map["ST002"]),
        ]
        db.add_all(users)
        db.commit()
        print(f"  - 创建 {len(users)} 位用户")

        treatment_types = [
            TreatmentType(type_code="WISDOM_EXTRACT", type_name="智齿拔除术", description="拔除阻生智齿或正常智齿"),
            TreatmentType(type_code="ROOT_CANAL", type_name="根管治疗", description="牙髓治疗、根尖治疗"),
            TreatmentType(type_code="ORTHO_EXTRACT", type_name="正畸减数拔牙", description="正畸前减数拔牙"),
            TreatmentType(type_code="IMPLANT", type_name="种植牙手术", description="种植体植入手术"),
            TreatmentType(type_code="SCALING", type_name="超声波洁牙", description="常规口腔洁治"),
            TreatmentType(type_code="FILLING", type_name="龋齿充填", description="树脂充填修复"),
        ]
        db.add_all(treatment_types)
        db.commit()
        ttype_map = {t.type_code: t.id for t in treatment_types}
        print(f"  - 创建 {len(treatment_types)} 种治疗类型")

        patients_data = [
            ("P001", "赵小明", Gender.MALE, 28, "13800138001", RiskLevel.MEDIUM, "高血压", "ST001"),
            ("P002", "孙美华", Gender.FEMALE, 35, "13800138002", RiskLevel.HIGH, "糖尿病,过敏体质", "ST001"),
            ("P003", "钱小刚", Gender.MALE, 24, "13800138003", RiskLevel.LOW, "", "ST001"),
            ("P004", "李芳芳", Gender.FEMALE, 31, "13800138004", RiskLevel.LOW, "孕妇", "ST002"),
            ("P005", "周建国", Gender.MALE, 52, "13800138005", RiskLevel.HIGH, "心脏病,高血压", "ST002"),
            ("P006", "吴晓燕", Gender.FEMALE, 26, "13800138006", RiskLevel.LOW, "", "ST002"),
            ("P007", "郑海涛", Gender.MALE, 38, "13800138007", RiskLevel.MEDIUM, "长期服药", "ST003"),
            ("P008", "王婷婷", Gender.FEMALE, 22, "13800138008", RiskLevel.LOW, "", "ST003"),
        ]
        patients = []
        for p_no, name, g, age, phone, risk, tags, s_code in patients_data:
            p = Patient(
                patient_no=p_no, name=name, gender=g, age=age,
                phone=phone, risk_level=risk, risk_tags=tags,
                store_id=store_map[s_code]
            )
            patients.append(p)
        db.add_all(patients)
        db.commit()
        patient_map = {p.patient_no: p.id for p in patients}
        print(f"  - 创建 {len(patients)} 位患者")

        today = date.today()
        records_data = [
            ("P001", "WISDOM_EXTRACT", today, "张医生", "左下8", "阻生齿拔除，缝合1针"),
            ("P002", "ROOT_CANAL", today - timedelta(days=2), "张医生", "右上6", "根管预备，暂封"),
            ("P003", "ORTHO_EXTRACT", today - timedelta(days=7), "张医生", "左上4,右上4", "减数拔牙2颗"),
            ("P004", "WISDOM_EXTRACT", today, "李医生", "右下8", "微创拔除"),
            ("P005", "IMPLANT", today - timedelta(days=1), "李医生", "左下6", "种植体植入，扭矩35Ncm"),
            ("P006", "FILLING", today, "李医生", "左下5", "3M树脂充填"),
            ("P007", "ROOT_CANAL", today, "李医生", "右下7", "根管再治疗"),
            ("P008", "SCALING", today - timedelta(days=3), "陈医生", "全口", "常规洁治抛光"),
        ]
        treatment_records = []
        for p_no, t_code, t_date, doc, tooth, notes in records_data:
            tr = TreatmentRecord(
                patient_id=patient_map[p_no],
                treatment_type_id=ttype_map[t_code],
                treatment_date=t_date,
                doctor_name=doc,
                tooth_position=tooth,
                treatment_notes=notes,
            )
            treatment_records.append(tr)
        db.add_all(treatment_records)
        db.commit()
        print(f"  - 创建 {len(treatment_records)} 条治疗记录")

        rules_data = [
            ("智齿拔除-当天晚间出血问询", "WISDOM_EXTRACT", 0, CallTimeWindow.EVENING, None,
             "您好，这里是微笑口腔客服中心。请问是{患者姓名}吗？今天您在我们门店做了智齿拔除手术，现在来电了解一下您的术后情况。请问拔牙创口还有没有明显的出血？有没有明显的疼痛或肿胀呢？有没有遵照医嘱咬住棉球止血呢？",
             "持续出血,出血不止,大量出血,晕厥", 5, True),
            ("智齿拔除-术后1日随访", "WISDOM_EXTRACT", 1, CallTimeWindow.AFTERNOON, None,
             "您好，请问是{患者姓名}吗？昨天您在我们这里做了智齿拔除，今天感觉怎么样？创口有没有不适？有没有按医嘱服药？饮食是否注意了？",
             "发热,持续疼痛,肿胀加剧", 3, True),
            ("根管治疗-术后2日疼痛随访", "ROOT_CANAL", 2, CallTimeWindow.AFTERNOON, None,
             "您好，这里是微笑口腔。请问是{患者姓名}吗？两天前您做了根管治疗，请问现在牙齿还有疼痛吗？咬合的时候会不会痛？有没有肿胀或者不舒服？",
             "持续疼痛,剧烈疼痛,肿胀,发热,麻木", 5, True),
            ("根管治疗-术后7日复诊提醒", "ROOT_CANAL", 7, CallTimeWindow.MORNING, None,
             "您好，请问是{患者姓名}吗？温馨提醒您，您的根管治疗已经满一周了，请按时来店复诊完成后续治疗。请问您方便预约哪天呢？",
             "", 2, True),
            ("正畸拔牙-术后7日复查提醒", "ORTHO_EXTRACT", 7, CallTimeWindow.AFTERNOON, None,
             "您好，这里是微笑口腔正畸中心。请问是{患者姓名}吗？您7天前做了正畸减数拔牙，伤口恢复得怎么样？提醒您按时来门店进行复查，让主治医生评估一下恢复情况。",
             "持续出血,剧烈疼痛,感染", 4, True),
            ("种植牙-术后1日随访", "IMPLANT", 1, CallTimeWindow.EVENING, None,
             "您好，请问是{患者姓名}吗？昨天您做了种植牙手术，今天感觉怎么样？创口有没有出血或者明显肿胀？有没有按医嘱服用消炎药？",
             "持续出血,剧烈疼痛,麻木,发热,流脓", 6, True),
            ("种植牙-术后10日复诊提醒", "IMPLANT", 10, CallTimeWindow.MORNING, None,
             "您好，请问是{患者姓名}吗？种植牙术后10天了，提醒您按时来门店拆线复查。",
             "", 2, True),
            ("洁牙-术后3日随访", "SCALING", 3, CallTimeWindow.AFTERNOON, None,
             "您好，请问是{患者姓名}吗？3天前您在我们这里做了洁牙，请问最近牙齿有没有敏感或者不适？有没有正确刷牙使用牙线呢？",
             "持续出血,剧烈酸痛", 1, True),
            ("充填-术后1日随访", "FILLING", 1, CallTimeWindow.EVENING, None,
             "您好，请问是{患者姓名}吗？今天您做了龋齿充填，请问现在牙齿咬合正常吗？有没有敏感或者疼痛？",
             "持续疼痛,咬合不适,填充物脱落", 2, True),
        ]
        rules = []
        for name, t_code, days, window, ctime, script, keywords, priority, active in rules_data:
            r = CallbackRule(
                rule_name=name,
                treatment_type_id=ttype_map[t_code],
                days_after_treatment=days,
                call_time_window=window,
                custom_call_time=ctime,
                script_template=script,
                abnormal_keywords=keywords,
                is_active=active,
                priority=priority,
            )
            rules.append(r)
        db.add_all(rules)
        db.commit()
        print(f"  - 创建 {len(rules)} 条回访规则")

        print("\n初始化完成！")
        print("\n登录账号：")
        print("  管理员: admin / admin123")
        print("  总部客服: agent1 / agent123, agent2 / agent123")
        print("  门店护士: nurse_bj / nurse123, nurse_sh / nurse123")
        print("  门诊医生: doc_zhang / doctor123, doc_li / doctor123")

    finally:
        db.close()


if __name__ == "__main__":
    init_db()
