# Handoff Log

Append-only log of Handoff Reports produced when switching between the two
Claude Code accounts working this project (see `CLAUDE.md`'s "Working
agreement: multi-account handoff"). Oldest entry first, newest appended at
the bottom — open this file directly to catch up instead of waiting for the
report to be pasted into chat.

---

## 2026-07-17 13:21 ICT

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

**A. แก้ไขเล็กๆ 3 จุดในหน้า Forecast** (`web/src/pages/ForecastPage.tsx` และไฟล์เกี่ยวข้อง)
1. แถบ "Generated power" (สีม่วง) ไม่โชว์ล่วงหน้าอีกต่อไป — เพิ่มฟังก์ชัน
   `truncateGeneratedToNow()` ใน `lib/chartData.ts` ตัดข้อมูลให้แสดงเฉพาะเวลาที่
   ผ่านไปแล้วจริงๆ (ก่อนหน้านี้ underlying data เป็นข้อมูลสังเคราะห์เต็มวัน
   ทำให้โชว์กำลังที่ "ยังไม่เกิด" ราวกับเป็นของจริง)
2. สี "Prediction interval" เปลี่ยนจากน้ำเงิน (ซ้ำกับเส้น Forecast) เป็นเขียว —
   เพิ่ม CSS var `--chart-pi` ใหม่
3. เพิ่มแถบคู่มือ "📖 คำแนะนำการอ่านหน้านี้" แบบเปิด-ปิดได้ สำหรับผู้ใช้ทั่วไป
   (ไม่ใช่วิศวกร) อธิบายทุกอย่างตั้งแต่จุดประสงค์หน้านี้ แกน X/Y ความหมายเส้น/แท่ง
   แต่ละสี Day-ahead vs Intra-day และคำอธิบายโมเดลครบทั้ง 5 ตัว (NeuralProphet/
   LightGBM/Random Forest/Sum-k LSTM/CNN-LSTM) พร้อมทิ้งคำสั่งเป็นโค้ดคอมเมนต์ไว้
   ว่าถ้ามีโมเดลใหม่ในอนาคตต้องเพิ่มในคู่มือนี้ด้วย

**B. ระบบ Auto-logout เมื่อมีการ deploy โค้ดใหม่** (ทั้งฝั่ง GitHub/Cloudflare และ Railway)
- Backend (`api/src/nongfab_api/auth.py`, `main.py`): ทุก JWT ฝัง `deploy_id`
  ที่สุ่มใหม่ทุกครั้งที่ process เริ่ม (เช่นตอน Railway deploy ใหม่) — token จาก
  รุ่นก่อนหน้าจะถูกปฏิเสธทันทีแม้ยังไม่หมดอายุ เพิ่ม endpoint `GET /version`
  (ไม่ต้อง auth) ให้ frontend poll ได้
- Frontend (`web/src/lib/deployWatch.ts` ใหม่, `lib/api.ts`, `lib/auth.tsx`,
  `components/Layout.tsx`, `components/Login.tsx`): poll `/version` ทุก 1
  นาที + เทียบ `index.html` ที่เสิร์ฟจริง (จับ Cloudflare redeploy ได้ด้วยแม้
  backend ไม่เปลี่ยน) — เมื่อพบว่ามีการอัปเดต จะบังคับออกจากระบบพร้อมข้อความ
  แจ้งเตือนที่หน้า Login
- ทดสอบจริงแบบ end-to-end แล้ว: ล็อกอิน → restart API process จำลอง Railway
  redeploy → ยืนยันว่าเบราว์เซอร์ถูกเด้งออกมาหน้า Login พร้อมข้อความจริง
- ข้อจำกัด: ส่วนตรวจจับ Cloudflare redeploy (เทียบ index.html) ทดสอบแบบ unit
  test ผ่านหมด แต่ยืนยันกับ Cloudflare จริงไม่ได้ (sandbox นี้ build จริงผ่าน
  Cloudflare ไม่ได้)

**C. อัปเดต CLAUDE.md** — เพิ่ม "เปลี่ยนแอค" เป็น trigger คำสั่งสำหรับ Handoff
Report, เพิ่มนโยบายถาวร "ไทยมาก่อนเสมอ" สำหรับข้อมูลเวลา/สภาพอากาศ, และเพิ่ม
convention ให้ append ทุก Handoff Report ลงไฟล์นี้ (`HANDOFF.md`) ด้วย

ทุกอย่าง push ขึ้น branch `claude/solar-optimization-forecasting-jryux7` แล้ว
(commit ล่าสุด `7c2261a` ก่อนไฟล์นี้)

### บริบทและสถานะปัจจุบัน (Current Context & State)

- Test suite: backend 114 tests ผ่าน, frontend 125 tests ผ่าน (tsc/vitest/oxlint สะอาดหมด)
- Branch เดียวที่ใช้งานทั้ง session นี้: `claude/solar-optimization-forecasting-jryux7`
- **โมดูล Financial (`/financial`) ยังใช้ตัวเลขสมมติอยู่** — CAPEX (฿30,000/kWp
  ประมาณ), ค่าไฟ PEA (฿4.0/kWh เดา), WACC (8%), BOI tax holiday (สมมติ = ไม่มี)
  มีแค่ภาษีนิติบุคคล 20% ที่เป็นตัวเลขจริง ถ้าพร้อมให้ตัวเลขจริง 4 ตัวนี้เมื่อไหร่
  บอกได้เลย จะนำไปแทนที่ default ใน `financial/src/nongfab_financial/model.py`
- ยังไม่ได้เริ่ม: bias correction กับข้อมูลจริงจาก Huawei FusionSolar (ติดที่ยังไม่มี
  สิทธิ์เข้าถึงระบบ Huawei)
- ค้างเรื่องหนึ่งที่ยังไม่ได้ตอบกลับ: รอบทดสอบ Sum-k LSTM ก่อนหน้านี้ พบว่ามันยังไม่
  เคยชนะการแข่งขันเลยสักชั่วโมงในข้อมูลสังเคราะห์ (LightGBM ชนะเกือบหมด) — ยังไม่ได้
  ตัดสินใจว่าจะปรับเกณฑ์แข่งขันหรือปล่อยไว้แบบนี้

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **⚠️ อย่าลืมกด Deploy บน Railway ด้วยตัวเอง** — รอบนี้แก้โค้ดฝั่ง `api/`
   (auth.py, main.py, ws_live.py) ซึ่ง Railway auto-deploy ยังไม่ทำงาน ต้องเข้าไป
   กดปุ่ม "Deploy" สีม่วงเองที่ Railway dashboard (api service → Deployments tab)
   ไม่งั้นระบบ auto-logout ฝั่ง backend จะยังไม่ทำงานจริงบนเว็บที่ใช้งานอยู่ ส่วน
   Cloudflare (frontend) จะ auto-deploy ให้เอง
2. ถ้ามีงานใหม่ที่จะสั่งต่อ ให้บอกได้เลยตามปกติ
3. ถ้าพร้อมให้ตัวเลขจริงของ Financial module (CAPEX/ค่าไฟ/WACC/BOI) ส่งมาได้เลย
   เพื่อแทนที่ placeholder

---

## 2026-07-18 12:21 ICT

**Track 1 — เนื้อหาเชิงวิชาการ** (branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ไม่ใช่งานเขียนโค้ด แต่เป็นการตกลง**แบ่งหน้าที่ถาวรระหว่าง 2 บัญชี** เพื่อไม่ให้
เขียนโค้ดชนกัน บันทึกไว้เป็นกติกาถาวรใน `CLAUDE.md` แล้ว (หัวข้อ "Two-track
division of labor between the two accounts"):

- **Track 1 — เนื้อหาเชิงวิชาการ** (บัญชีนี้ / branch
  `claude/solar-optimization-forecasting-jryux7`): Forecast, Financial, 3D
  View, Simulation และฟีเจอร์เชิงวิศวกรรม/data-science อื่นๆ ดูแล `api/`,
  `forecast/`, `financial/`, `simulation/`, `ingestion/`, `libs/`, `features/`
- **Track 2 — หน้าตา/Interface** (อีกบัญชี / branch
  `claude/solar-website-modules-msyvv5`): ความสวยงามของเว็บ, UI/UX, AI
  assistant popup ที่ช่วยผู้ใช้และตอบคำถาม, ระบบเชื่อมต่อ/ติดต่อกันระหว่างผู้ชม
  ส่วนใหญ่อยู่ใน `web/` แต่ไม่ใช่ทั้งหมด (ดูหมายเหตุด้านล่าง)

**หมายเหตุเรื่องขอบเขตใน `web/`**: โฟลเดอร์ frontend ใช้ร่วมกันทางกายภาพ
แบ่งกันที่ "ประเภทงาน" ไม่ใช่ตามโฟลเดอร์ล้วนๆ — Track 1 ดูแลการสร้างหน้า/
ฟีเจอร์ใหม่ที่นำเสนอเนื้อหาเชิงวิศวกรรม (กราฟใหม่ ผลลัพธ์โมเดลใหม่ field
ข้อมูลใหม่) แม้ไฟล์จะอยู่ใต้ `web/src/pages/` ก็ตาม ส่วน Track 2 ดูแลความสวยงาม/
UX ล้วนๆ, AI assistant components, ระบบ styling, และฟีเจอร์โซเชียล/เครือข่าย

### บริบทและสถานะปัจจุบัน (Current Context & State)

ถ้าบัญชีนี้ (Track 2) ถูกขอให้ทำงานที่ชัดเจนว่าเป็นของอีก Track ให้แจ้งผู้ใช้
สั้นๆ ก่อน (ไม่ใช่ทำเงียบๆ หรือปฏิเสธเลย) แล้วให้ผู้ใช้ตัดสินใจว่าจะให้ข้ามมาทำ
ที่นี่เลยหรือรอรอบของอีกบัญชี — ดูรายละเอียดเต็มใน `CLAUDE.md`

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. บัญชีนี้ (Track 2 - อีกบัญชี) เมื่อเปิด session ใหม่ ให้เช็ค `git branch
   --show-current` เทียบกับ `CLAUDE.md`'s Two-track section เพื่อยืนยันว่า
   ตัวเองคือ Track ไหน
2. งานที่ค้างของ Track 1 (ดู entry ด้านบน): กด Deploy บน Railway ด้วยตัวเอง
   (ยังไม่ยืนยันว่าคลิกแล้ว), รอตัวเลขจริงของ Financial module
3. ยังไม่มีงาน Track 2 (UI/UX, AI assistant, ระบบเครือข่ายผู้ชม) เริ่มไว้ใน
   session นี้เลย - รอผู้ใช้สั่งงานตรงกับบัญชีนั้นได้เลย
