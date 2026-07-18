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

## 2026-07-18 12:49 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7` — ใช้ branch ร่วมกับ
Track 1 ตามที่ตกลงไว้ใน `CLAUDE.md`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

1. **แถบอุณหภูมิ 24 ชม. แบบเลื่อนตามเวลาจริง** (commit `7e0013f`, ก่อนหน้า
   entry นี้แต่ยังไม่เคยลง HANDOFF.md): เอาแถบอุณหภูมิแบบ 4 checkpoint คงที่
   เดิมออก แทนด้วย `WeatherStrip` component ที่ดึงข้อมูลจริงจาก NWP ผ่าน
   endpoint ใหม่ `GET /weather/strip` (`api/src/nongfab_api/routes_weather.py`)
   คำนวณตำแหน่ง block ให้สัมพันธ์กับเวลาจริงแบบต่อเนื่อง (CSS transform +
   transition 1s linear ต่อ tick) ตาม spec ที่ผู้ใช้ยกตัวอย่างไว้ (14:00 ตรง
   กลางพอดี, 14:30 ช่องว่างตรงกลาง ฯลฯ) - มี fallback synthetic ถ้าข้อมูลจริง
   ไม่ครบ 80% ของช่วงเวลา
2. **มาสคอตตัวการ์ตูนน่ารักๆ** (`web/src/components/Mascot.tsx` + `.css`):
   ตัวอาทิตย์การ์ตูน SVG วาดเอง มุมขวาล่างของทุกหน้า หันซ้าย-ขวาช้าๆ
   (keyframe 7s) มีแสงเรืองอ่อนๆ pulse รอบตัว (keyframe 3.2s) เคารพ
   `prefers-reduced-motion` ตามรูปตัวอย่างที่ผู้ใช้ส่งมา
3. **AI assistant v1 แบบไม่มีค่าใช้จ่าย** (`web/src/lib/assistant.ts`,
   `AssistantPanel.tsx/.css`, `AIAssistant.tsx`): ระบบ rule-based
   (keyword-matching ต่อ intent list) ไม่เรียก LLM API ใดๆ เลย - ตอบได้ทั้ง
   (ก) ช่วยใช้งานเว็บ/นำทาง (ข) คำถามข้อมูลจริงในระบบ (กำลังไฟตอนนี้,
   พลังงานวันนี้, พยากรณ์, capacity, อุณหภูมิ - ดึงจาก endpoint จริงทั้งหมด)
   (ค) ความรู้ทั่วไป (kWp, irradiance, plant factor, forecast horizon คือ
   อะไร) มี quick-reply chips 4 ปุ่มให้กดเริ่มโดยไม่ต้องพิมพ์ มาสคอตทำหน้าที่
   เป็นปุ่ม toggle เปิด/ปิดแชทในตัว (การตัดสินใจของฉันเอง ไม่ได้ถามผู้ใช้แยก
   แต่แจ้งไว้ตรงๆ)
4. Commit `b1afc1f`/`d17adae` (หลัง rebase ทับงานของ Track 1 ที่ push มาใหม่
   ระหว่างนั้น - `d129364` แก้ build พัง จาก `ForecastDataSource` export หาย)
   - push ขึ้น branch แล้ว, `tsc --noEmit` ผ่าน, tests ผ่านหมด (16 tests: 10
   ที่ `assistant.test.ts` + 6 ที่ `AIAssistant.test.tsx`), verify ด้วย
   Playwright จริงทั้ง light/dark mode แล้ว (คลิก quick-reply "ตอนนี้ผลิตไฟ
   เท่าไหร่" ได้คำตอบ 306.0 kW ตรงกับ KPI card หน้า dashboard พอดี)

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ผู้ใช้ย้ำชัดเจนว่า**ไม่ต้องการเสียเงินเพิ่มเลย** - ห้ามเพิ่ม LLM API แบบเสีย
  เงิน (Anthropic/Gemini/อื่นๆ) เข้ามาแทนระบบ rule-based นี้โดยไม่ถามก่อน
- ผู้ใช้อธิบายขอบเขตงานของ Track 2 (บัญชีนี้) ไว้ชัดว่ามี "ระบบเครือข่าย
  ผู้ชม" ด้วย และเมื่อถามกลับ (multi-select) ผู้ใช้ตอบว่า "ทุกอย่างที่ว่ามา
  เลย" คือ: (1) แชทเรียลไทม์ระหว่างผู้ชมด้วยกัน (2) presence indicator (ใคร/
  กี่คนออนไลน์อยู่) (3) แบบฟอร์ม contact/comment ง่ายๆ (4) ช่องทางส่งข้อความ/
  feedback ถึง admin โดยเฉพาะ - **ยังไม่ได้เริ่มสร้างส่วนนี้เลยแม้แต่ชิ้นเดียว**
- โครงสร้าง intent ใน `assistant.ts`: intent ความรู้ทั่วไป (`knowledge_*`)
  ต้องอยู่ *ก่อน* intent ที่ดึงข้อมูลจริง (`current_power` ฯลฯ) ใน array
  เพราะ keyword ชนกันได้ (เช่น "kwp") - ถ้าจะเพิ่ม intent ใหม่ให้ระวังลำดับนี้
- pattern WebSocket ที่มีอยู่แล้วให้ reuse ได้: `api/src/nongfab_api/ws_live.py`
  (auth ผ่าน `?token=` query param เพราะ browser set header ตอน handshake
  ไม่ได้) - น่าจะใช้เป็นฐานสำหรับแชทเรียลไทม์/presence ได้เลย
- **Railway ยังไม่ auto-deploy** (ปัญหาเดิม) - แต่ session นี้ไม่ได้แตะ `api/`
  ฝั่ง business logic ที่มีผลต่อ production จริงจัง (เพิ่ม endpoint ใหม่
  `/weather/strip` เท่านั้นซึ่งอยู่ก่อน entry นี้แล้ว) - เผื่อไว้: ถ้ายังไม่ได้
  กด Deploy บน Railway หลัง `7e0013f` ก็ต้องกดด้วย
- **Financial module ยังใช้ placeholder ทั้งหมด** (CAPEX/tariff/WACC/BOI) -
  ยังไม่มีตัวเลขจริงจากผู้ใช้ (นี่คืองานของ Track 1 เป็นหลัก แต่ทั้งสอง
  account ควรเตือนถ้าเจอผู้ใช้คุยเรื่องนี้)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งานถัดไปที่ผู้ใช้ขอไว้แล้วแต่ยังไม่เริ่ม**: ระบบเครือข่ายผู้ชมทั้ง 4 ส่วน
   (แชทเรียลไทม์, presence, contact form, admin feedback channel) - ก่อน
   เริ่มเขียนโค้ดจริง ควรถามผู้ใช้เรื่อง design specifics บางจุดก่อน (เช่น
   แชทเป็น public ทั้งเว็บหรือแยกห้อง, admin feedback ต้องมี UI หน้า admin
   แยกไหมหรือพอแค่เก็บลง DB ให้ดูทีหลัง) ตาม instruction "ถามก่อนตัดสินใจ
   เสมอ"
2. ถ้า session ต่อไปเป็น Track 1: ไม่มีอะไรใหม่จาก Track 2 ที่กระทบ `api/`
   business logic นอกจาก `/weather/strip` endpoint (เพิ่มไฟล์ใหม่ ไม่แก้ของ
   เดิม) - build ผ่านแล้วหลัง merge
3. ถ้าแตะ `api/` เพิ่มเติม (เช่น ทำ WebSocket ใหม่สำหรับแชทผู้ชม) อย่าลืมเตือน
   เรื่อง Railway manual deploy ตามหัวข้อใน `CLAUDE.md`

## 2026-07-18 13:09 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

สร้าง **ระบบเครือข่ายผู้ชมครบทั้ง 4 ส่วน** ตามที่ผู้ใช้ขอ ("ทุกอย่างที่ว่ามา
เลย") - commit `54041a9`:

1. **แชทเรียลไทม์แบบห้องเดียวรวมทั้งเว็บ** (ผู้ใช้ยืนยันผ่านคำถามที่ถาม: "ห้อง
   เดียวรวมทั้งเว็บ" ไม่แยกตามหน้า/โซน) - `api/src/nongfab_api/ws_chat.py`
   (`GET /ws/chat`, auth ผ่าน `?token=`) broadcast ข้อความให้ทุก client ที่ต่อ
   อยู่ พร้อม replay ประวัติ 50 ข้อความล่าสุดตอน connect (`ChatStore`, ตาราง
   `chat_messages` ใหม่)
2. **Presence indicator** - `ConnectionManager` ใน `ws_chat.py` นับจำนวน
   socket ที่ต่ออยู่ (ต่อ process เดียว ไม่มี pub/sub ข้าม process เพราะ deploy
   นี้รันแค่ 1 process) broadcast เป็น event `presence` ทุกครั้งที่มีคนเข้า/ออก
   - แสดงเป็น badge ตัวเลขที่ปุ่ม toggle ของ widget
3. **แบบฟอร์ม contact/feedback** + **ช่องทางถึง admin โดยเฉพาะ** (ผู้ใช้ตอบ
   ว่าอยากได้ทั้งสองอย่างรวมกัน ไม่ใช่แยก 2 ฟีเจอร์) -
   `api/src/nongfab_api/routes_feedback.py` (`POST /feedback` ทุก role ที่
   login แล้วส่งได้, `GET /feedback` admin เท่านั้น) ตาราง `feedback_messages`
   ใหม่ - **ไม่มี** ระบบ reply/resolve (ผู้ใช้ไม่ได้ขอ ตั้งใจทำแบบง่ายที่สุด)
4. **หน้า admin ดูข้อความในเว็บ** (ผู้ใช้ยืนยันผ่านคำถามที่ถามว่าต้องการ UI ใน
   เว็บ ไม่ใช่แค่เก็บ DB) - หน้าใหม่ `/admin/feedback`
   (`web/src/pages/AdminFeedbackPage.tsx`) ขึ้น nav bar เฉพาะ role admin,
   guard เส้นทางด้วย `RequireAdmin` ใน `App.tsx` (ไม่ใช่แค่ซ่อนลิงก์ nav)
5. Frontend UI: `web/src/components/VisitorNetwork.tsx` + `.css` - widget
   ลอยมุมซ้ายล่าง (มาสคอต/AI assistant อยู่มุมขวาล่างอยู่แล้ว) รวมแชท+feedback
   เป็น 2 แท็บในหน้าต่างเดียว ไม่ทำเป็นปุ่มลอยแยก 4 ปุ่มเพราะจะรกเว็บเกินไป
   (เป็นการตัดสินใจของฉันเอง ไม่ได้ถามผู้ใช้แยก แต่แจ้งไว้ตรงๆ)
6. **เปลี่ยน public viewer login เป็น `pttlng`/`12345`** ตามที่ผู้ใช้ระบุตรงๆ
   (`api/src/nongfab_api/auth.py`'s `DEMO_USERS`, เดิมคือ
   `viewer`/`viewer-demo-pw`) - อัปเดต README ทั้ง 2 ไฟล์ + test ที่ hardcode
   credential เดิมด้วยแล้ว
7. Bug ที่เจอจาก test จริง (ไม่ใช่แค่เดา): ตอนแรก `VisitorNetwork.tsx` เรียก
   `useChatSocket()` **สองครั้ง** (ที่ widget เองสำหรับนับ online, และใน
   `ChatTab` สำหรับข้อความ) ทำให้เปิด WebSocket connection ซ้อนกัน 2 เส้นต่อ
   widget 1 ตัว - แก้โดยเรียก hook แค่ครั้งเดียวใน `VisitorNetwork` แล้วส่ง
   state ลงไปเป็น prop ให้ `ChatTab` แทน
8. ทดสอบครบ: backend pytest ใหม่ 12 ตัวผ่าน (test_ws_chat.py,
   test_routes_feedback.py) + suite เต็ม 130 ตัวผ่าน, frontend vitest ใหม่ 10
   ตัวผ่าน + suite เต็ม 163 ตัวผ่าน, `tsc --noEmit` ผ่าน, verify จริงด้วย
   Playwright (2 browser context จำลอง admin กับ viewer แยกกัน) - ยืนยันว่า
   ข้อความจาก viewer ขึ้นที่ admin แบบเรียลไทม์จริง, presence นับถูก (2→3),
   feedback ที่ viewer ส่งไปโผล่ในหน้า admin inbox จริง, เวลาที่แสดงเป็น
   Asia/Bangkok (ICT) ตาม standing policy, ทดสอบ dark mode แล้วด้วย

### บริบทและสถานะปัจจุบัน (Current Context & State)

- Login credential สาธารณะสำหรับผู้ชมตอนนี้คือ **`pttlng` / `12345`** (role
  viewer) - แจกให้ผู้ชมใช้เข้าแชท/ส่ง feedback ได้ - บัญชี `admin`/
  `admin-demo-pw` และ `operator`/`operator-demo-pw` ยังเหมือนเดิม
- `/ws/chat` เป็น in-memory connection manager ต่อ process เดียว (ไม่มี
  Redis pub/sub) - ถ้า deploy จริงมีมากกว่า 1 API process/instance พร้อมกัน
  เมื่อไหร่ ผู้ชมที่ต่อกับ process ต่างกันจะไม่เห็นข้อความกัน ต้องแก้เพิ่ม
  ตอนนั้น (ตอนนี้ deploy เป็น 1 process จึงยังไม่ใช่ปัญหา)
- ยังไม่มี migration SQL ถูกรันจริงบน production Postgres (Railway) -
  `create_tables_on_startup` (default true) จะสร้างตารางให้อัตโนมัติตอน
  deploy ครั้งถัดไป เหมือนตาราง `users` เดิม แต่ `db/migrations/
  0005_chat_and_feedback.sql` ก็มีไว้เป็น source of truth คู่กันแล้ว
- **Railway ยังไม่ auto-deploy** - session นี้แตะ `api/` เพิ่ม endpoint ใหม่
  (`/ws/chat`, `/feedback`) และตาราง DB ใหม่ - **ต้องกด Deploy บน Railway
  ด้วยตัวเองหลัง push นี้** ถ้ายังไม่ได้กด
- Financial module ยังใช้ placeholder ทั้งหมด (ไม่เปลี่ยนแปลงจาก entry ก่อน
  หน้า)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งาน Track 2 ที่ผู้ใช้ระบุไว้ทั้งหมดตอนนี้เสร็จครบแล้ว** (มาสคอต, AI
   assistant, แชท, presence, feedback form, admin inbox) - รอผู้ใช้สั่งงาน
   เพิ่มเติม หรือ polish/ขัดเกลาตามฟีดแบ็กที่จะได้รับ
2. **ต้องกด Deploy บน Railway ด้วยตัวเอง** (purple "Deploy" button, tab
   Deployments ของ service `api`) เพื่อให้ `/ws/chat` และ `/feedback`
   endpoint ใหม่ + ตาราง DB ใหม่ใช้งานได้จริงบน production - ยังไม่ยืนยันว่า
   กดแล้วหรือยัง
3. แจ้งผู้ใช้เรื่อง credential ใหม่ `pttlng`/`12345` ให้เอาไปแปะ/แจกจริงตามที่
   ตั้งใจไว้ (เว็บไซต์เอง ป้ายหน้างาน ฯลฯ) - session นี้แค่ implement ฝั่งระบบ
   ให้เท่านั้น
4. ถ้ามีคนถามเรื่อง production data volume ของ `chat_messages` ในอนาคต
   (ยังไม่มี retention/cleanup policy) - เป็นจุดที่ยังไม่ได้ทำไว้ ถ้า
   production มีข้อความเยอะมากอาจต้องเพิ่ม pagination ที่ GET /feedback หรือ
   cap ประวัติแชทให้เก่ากว่านี้ถูกลบทิ้ง

## 2026-07-18 13:42 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ผู้ใช้ขอเพิ่มเติม 2 เรื่องสำหรับระบบแชทที่เพิ่งสร้างไป (entry ก่อนหน้า) -
ทำเสร็จแล้ว commit `9f059b2`:

1. **ระบบตั้งชื่อ + เลือก avatar แบบ LINE** สำหรับ viewer/operator - เหตุผล
   สำคัญ: login ของ viewer (`pttlng`/`12345`) เป็น credential ที่ใช้ร่วมกัน
   หลายคนพร้อมกันได้ ดังนั้น `username` เดียวไม่พอจะแยกว่าใครเป็นใครในแชท -
   เพิ่ม `web/src/lib/chatProfile.ts` (catalog avatar อิโมจิ 12 แบบ + สุ่ม
   `clientId` ต่อ browser เก็บใน localStorage) และหน้าฟอร์มตั้งค่าก่อนเริ่ม
   แชทครั้งแรก (`ProfileSetup` ใน `VisitorNetwork.tsx`) มีปุ่มแก้ไขทีหลังได้
   (ปุ่มดินสอ) - **admin ไม่ต้องทำส่วนนี้เลย** ระบบ force ชื่อ "admin" +
   avatar "crown" 👑 ให้อัตโนมัติ ทั้งฝั่ง UI (ข้าม picker) และฝั่ง backend
   (`ws_chat.py` ไม่เชื่อค่าที่ client ส่งมาสำหรับ role admin เด็ดขาด)
2. **เลื่อนดูข้อความเก่าได้ (scroll-back)** - เพิ่ม `GET /chat/history?
   before_id=` endpoint (`ws_chat.py`) โหลดข้อความเก่าทีละหน้าเมื่อเลื่อนขึ้น
   บนสุดของแชท (infinite scroll, คง scroll position ไว้ไม่กระโดด)
3. **ระบบแจ้งเตือนข้อความที่ยังไม่ได้อ่าน แบบ LINE/Messenger** - badge สีแดง
   (ใช้ `--danger` แทนสีม่วงเดิมที่เคยโชว์ online count) นับจำนวนข้อความใหม่
   ที่เข้ามาระหว่างที่ไม่ได้เปิดดูแท็บแชทอยู่ เก็บ `lastReadMessageId` ไว้ใน
   localStorage เพื่อให้ค่านี้อยู่ข้ามการ reload หน้าเว็บด้วย (ไม่ใช่แค่ใน
   session เดียว) - เคลียร์อัตโนมัติทันทีที่เปิดแท็บแชทดู
4. เพิ่ม `client_id` เข้าไปใน schema/protocol ของข้อความแชทด้วย (ไม่ใช่แค่
   `username`) เพื่อให้ตรวจจับ "ข้อความของตัวเอง" (สำหรับ bubble style ชิดขวา)
   ถูกต้องแม้จะ login ด้วย username เดียวกันหลายคนพร้อมกัน - migration ใหม่
   `db/migrations/0006_chat_profile_and_history.sql` เพิ่ม 3 column
   (`display_name`, `avatar`, `client_id`) ลงตาราง `chat_messages` เดิม
5. **บั๊กจริงที่เจอจาก Playwright live verify** (ไม่ใช่แค่ unit test): admin
   เห็นฟอร์มตั้งชื่อ/avatar ทั้งที่ไม่ควรเห็นเลย - สาเหตุคือ `role` จาก
   `useAuth()` เป็น `null` ชั่วขณะหนึ่ง render หลัง login เสร็จ (เพราะ
   `AuthProvider` ถอดรหัส JWT claims ผ่าน `useEffect` ไม่ใช่ synchronous)
   แล้วค่า `null` นั้นดันถูก "จำ" ไว้ถาวรใน `useState` lazy initializer ของ
   `VisitorNetwork` (evaluate แค่ครั้งเดียวตอน mount) ทำให้ admin ถูกเข้าใจผิด
   ว่าไม่ใช่ admin ไปตลอด - แก้โดยคำนวณเงื่อนไข admin ใหม่ทุก render แทน
6. ทดสอบครบ: unit/component tests ใหม่/แก้ไข ผ่านหมด (backend 22 ตัวที่
   test_ws_chat.py+test_routes_feedback.py+test_login.py, suite เต็ม 135 ตัว
   ผ่าน / frontend suite เต็ม 170 ตัวผ่าน) `tsc --noEmit` ผ่าน verify จริงผ่าน
   Playwright จำลอง 2 browser (admin + viewer) ยืนยันครบทุกจุด: admin ไม่เห็น
   picker, viewer เห็น picker ครั้งแรกแล้วหายไปหลัง reload (persist สำเร็จ),
   badge แจ้งเตือนขึ้นเลข 1 ตอนปิดหน้าต่างแล้วมีข้อความใหม่ และหายไปทันทีที่
   เปิดดู, admin เห็นชื่อ+avatar ที่ viewer เลือกจริง

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ระหว่าง push งานนี้ push ชนกับงานของ Track 1 สองรอบ (ทั้ง entry ก่อนหน้า
  และรอบนี้) - ใช้ `git pull --rebase` แก้ทุกครั้ง ไม่มี merge conflict เกิดขึ้น
  จริงสักครั้ง เพราะ Track 1/2 แยกไฟล์กันชัดเจนตามที่ตกลงไว้ - build/test
  ผ่านหมดหลัง rebase ทุกครั้งเช่นกัน
- Client-side `chatProfile.ts` ใช้ `crypto.randomUUID()` - รองรับ browser
  สมัยใหม่ทั้งหมดที่เว็บนี้ target อยู่แล้ว ไม่ต้องมี polyfill
- ยังไม่มีการ resolve/reply ให้ feedback (ตามที่ตั้งใจไว้แต่แรก - ผู้ใช้ไม่ได้
  ขอ) และยังไม่มี retention policy ให้ `chat_messages` (ข้อความสะสมไปเรื่อยๆ
  ไม่มีวันลบอัตโนมัติ) - เหมือน entry ก่อนหน้าที่เคยเตือนไว้แล้ว
- **Railway ยังไม่ auto-deploy** - session นี้แก้ `api/` เพิ่มเติมอีก (endpoint
  ใหม่ `GET /chat/history`, protocol `/ws/chat` เปลี่ยน, ตาราง DB เพิ่ม 3
  column) - ต้องกด Deploy บน Railway เองอีกครั้งหลัง push นี้ด้วย (รวมกับที่
  ค้างจาก entry ก่อนหน้าถ้ายังไม่ได้กด)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งาน Track 2 ที่ผู้ใช้ระบุไว้ล่าสุดเสร็จครบแล้ว** (profile picker,
   scroll-back, unread badge) - รอผู้ใช้สั่งงานเพิ่มเติม หรือฟีดแบ็กจากการ
   ทดลองใช้จริง
2. **ต้องกด Deploy บน Railway ด้วยตัวเอง** อีกครั้ง (purple "Deploy" button,
   tab Deployments ของ service `api`) - migration `0006_chat_profile_and_
   history.sql` ต้องรันบน production Postgres ด้วย (หรือปล่อยให้
   `create_tables_on_startup` จัดการก็ได้ถ้ายังไม่เคย deploy ตาราง
   `chat_messages` มาก่อนเลย - แต่ถ้า deploy ตารางเดิมไปแล้วตั้งแต่ entry
   ก่อนหน้า ต้องรัน migration SQL เพิ่มคอลัมน์จริงๆ ไม่งั้น column ใหม่จะไม่มี)
3. ถ้าผู้ใช้อยากได้ retention policy สำหรับ `chat_messages` หรือระบบ reply
   ให้ feedback ในอนาคต ยังไม่มีใครเริ่มทำไว้เลย

---

## 2026-07-18 14:06 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ผู้ใช้ถามตามด้วย 2 คำถาม + 1 คำขอเพิ่มเติมเกี่ยวกับระบบ profile แชทที่เพิ่งทำ
ไป (entry ก่อนหน้า) - ตอบ+ทำเสร็จแล้ว commit `b03fc06`:

1. **ยืนยัน (ไม่ต้องแก้โค้ด)**: profile (ชื่อ+avatar) เก็บใน localStorage ของ
   browser ไม่ผูกกับ session login - logout แล้ว login ใหม่ด้วยเครื่อง/
   browser เดิม ไม่ต้องตั้งใหม่
2. **เจอ + แก้บั๊กจริง**: ปุ่มแก้ไขโปรไฟล์ (✏️) ที่มีอยู่แล้วเปิดฟอร์มว่างเปล่า
   ทุกครั้งแทนที่จะเติมชื่อ/avatar ปัจจุบันให้ - แก้ให้ prefill ค่าปัจจุบันแล้ว
   พร้อมเพิ่มปุ่ม "ยกเลิก" (`ProfileSetup` รับ `initial: ChatProfile | null`
   ใน `VisitorNetwork.tsx`)
3. **ทำใหม่**: ผู้ใช้ขอให้ **admin เปลี่ยนชื่อ+avatar ได้เหมือน viewer/
   operator ด้วย** แต่เวลาแสดงให้คนอื่นเห็นให้ขึ้นคำว่า "admin" นำหน้าชื่อ -
   ลบ special-case เดิมที่ force admin เป็นชื่อ "admin"+avatar "crown" ตายตัว
   ออกทั้งหมด (`chatProfile.ts`'s `adminProfile()`/`ADMIN_AVATAR` ลบทิ้ง,
   `VisitorNetwork.tsx` ไม่เช็ค `role === 'admin'` อีกต่อไป - ทุก role ผ่าน
   picker เดียวกันหมด) แล้วย้าย logic การ "บังคับ prefix" ไปทำที่ **backend**
   แทน (`ws_chat.py`): เมื่อ role เป็น admin ระบบจะเติม `"admin "` นำหน้าชื่อที่
   เลือกไว้เสมอ (`ADMIN_NAME_PREFIX`) ก่อนบันทึก/ส่งต่อ - **client ฝั่งไหนก็
   เอาออกไม่ได้** เพราะบังคับที่ server ไม่ใช่ UI ส่วน avatar เลือกได้อิสระจาก
   avatar catalog เดียวกับทุกคน ไม่ force เป็น crown อีกต่อไป

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ผลลัพธ์ที่ผู้ชมคนอื่นเห็นตอนนี้: admin ตั้งชื่อ "สมชาย" + เลือก avatar
  "lion" → คนอื่นเห็นเป็น "admin สมชาย" พร้อม avatar สิงโตในแชท (verify จริง
  ด้วย Playwright แล้ว - ดู screenshot ที่อธิบายไว้ใน commit message)
- `AVATAR_OPTIONS` (12 แบบ, `web/src/lib/chatProfile.ts`) เป็น catalog เดียว
  ที่ทุก role เลือกได้ตอนนี้ - ไม่มี avatar สงวนไว้เฉพาะ role ใดแล้ว
- ข้อความแชทเก่าที่เคยถูกบันทึกด้วย avatar "crown" (จาก entry ก่อนหน้าที่
  admin ยัง force อยู่) จะ fallback ไป avatar ตัวแรกใน catalog เวลาแสดงผล
  (`avatarById()` ไม่รู้จัก id "crown" อีกต่อไป) - เป็นแค่เรื่อง cosmetic ของ
  ข้อความเก่า ไม่กระทบข้อมูลจริงหรือฟังก์ชันอื่น
- ทดสอบครบ: backend suite เต็ม 139 ตัวผ่าน (รวม test ใหม่ที่ตรวจ prefix
  บังคับ + client ปลอม prefix ไม่ได้), frontend suite เต็ม 172 ตัวผ่าน `tsc`
  ผ่าน verify จริงด้วย Playwright (admin + viewer คนละ browser context)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งานที่ผู้ใช้ขอไว้ล่าสุดเสร็จครบแล้ว** - รอฟีดแบ็กหรือคำสั่งเพิ่มเติม
2. **ต้องกด Deploy บน Railway ด้วยตัวเอง** อีกครั้ง (ยังไม่ยืนยันว่ากดแล้ว
   ตั้งแต่ entry ก่อนหน้าด้วยซ้ำ) - รอบนี้ไม่มี schema เปลี่ยนเพิ่ม (ใช้
   column เดิมจาก `0006_chat_profile_and_history.sql`) แค่ logic การ prefix
   เปลี่ยนที่ backend เท่านั้น
3. ยังไม่มี retention policy สำหรับ `chat_messages` เหมือนที่เตือนไว้ใน entry
   ก่อนหน้า

## 2026-07-18 14:27 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ผู้ใช้ขอปรับปรุง AI assistant ครั้งใหญ่ - ตั้งชื่อ "น้อง Solar" (เพศชาย) พร้อม
ฟีเจอร์ใหม่ 2 อย่าง - ทำเสร็จแล้ว commit `ada0b4b`:

1. **ตั้งชื่อ "น้อง Solar" เป็นตัวละครเพศชาย** - เปลี่ยนคำพูดทั้งหมดใน
   `assistant.ts` จากหญิง (หนู/ค่ะ/คะ) เป็นชาย (ผม/ครับ) ทุกจุด รวมถึง
   greeting ใน `AssistantPanel.tsx` และหัวข้อ panel ("น้อง Solar - ผู้ช่วย AI")
2. **Popup ใหญ่หน้า login** (`LoginWelcome.tsx` ใหม่) - เด้งอัตโนมัติทุกครั้งที่
   มาหน้า login (ไม่ persist ว่าเคยปิดแล้ว) มีน้อง Solar ตัวใหญ่ทักทาย แนะนำ
   ฟีเจอร์เว็บ 6 อย่างแบบย่อ และบอก credential สำหรับ viewer (`pttlng`/
   `12345`) ชัดเจน ปิดได้ 3 ทาง (ปุ่ม ×, ปุ่ม CTA, คลิก backdrop)
3. **น้องไปโผล่หน้าตั้งชื่อ+เลือก avatar ด้วย** (`VisitorNetwork.tsx`'s
   `ProfileSetup`) - ดึงตัวการ์ตูนมาแสดงเหนือฟอร์ม พร้อมข้อความพูดแทนตัว
   ("น้อง Solar: ตั้งชื่อและเลือก avatar...ครับ")
4. **ตัวใหญ่ขึ้น** - ปุ่มลอย mascot จาก 68px → 108px (มือถือ 84px) พร้อมขยับ
   ตำแหน่ง panel ให้ไม่ทับกัน
5. **แสดงอารมณ์ได้** - รีแฟกเตอร์ SVG ตัวการ์ตูนออกเป็น component แยก
   `MascotFace.tsx` (ใช้ร่วมกัน 3 จุด: ปุ่มลอย, login popup, profile setup)
   รับ prop `mood: 'idle' | 'happy' | 'sad'` เปลี่ยนรูปปาก + เพิ่ม sparkle
   (happy) หรือหยดน้ำตา (sad) - ตอบคำถามได้จริง = ยิ้มกว้าง, ตอบไม่ได้/fetch
   พัง = หน้าเศร้า, auto กลับเป็นหน้าปกติหลัง 4 วิ (`AIAssistant.tsx` คุม
   timer) ฝั่ง logic เพิ่มฟังก์ชันใหม่ `answerQuestionWithMood()` ใน
   `assistant.ts` ที่ห่อ `answerQuestion()` เดิมไว้ (ไม่กระทบ caller/test เดิม
   ที่ยังใช้ string return แบบเดิมอยู่)
6. ทดสอบครบ: frontend suite เต็ม 182 ตัวผ่าน (เพิ่ม test ใหม่หลายจุดรวมถึง
   เช็ค mood เปลี่ยนจริงจากการอ่าน SVG `d` attribute ของปาก) `tsc` ผ่าน
   verify จริงด้วย Playwright เห็นทั้ง popup login, mascot ตัวใหญ่บน
   dashboard, mascot ในฟอร์ม profile, และทั้ง 3 mood (idle/happy/sad) จริง
   ในเบราว์เซอร์

### บริบทและสถานะปัจจุบัน (Current Context & State)

- Popup หน้า login ไม่มี persistence (ไม่เก็บ localStorage ว่าเคยปิดแล้ว) -
  จะเด้งทุกครั้งที่กลับมาหน้า login (เช่นหลัง sign out) ตามที่ผู้ใช้ขอแบบ
  ตรงตัว - ถ้าฟีดแบ็กมาว่ารำคาญ ค่อยเพิ่ม localStorage flag ทีหลังได้
- ระหว่าง live-verify เจอเรื่อง screenshot บางจุดถ่ายเร็วเกินไป (ก่อน CSS
  ของ dev server โหลดเสร็จ) ทำให้ดูเหมือนมี bug ภาพซ้อนกัน - ไม่ใช่ bug จริง
  แค่ race condition ของสคริปต์ verify เอง (แก้โดยเพิ่ม wait ก่อน screenshot)
  ไม่กระทบโค้ด production
- ไม่มีการเปลี่ยน backend เลยในรอบนี้ (ทั้งหมดเป็นฝั่ง `web/` ล้วนๆ) - **ไม่ต้อง
  กด Railway deploy สำหรับงานรอบนี้** แต่ยังมีงานค้างจาก entry ก่อนๆ ที่อาจ
  ยังไม่ได้กด (ดู entry ก่อนหน้า)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งานที่ผู้ใช้ขอไว้ล่าสุดเสร็จครบแล้ว** - รอฟีดแบ็กหรือคำสั่งเพิ่มเติม
2. ถ้าผู้ใช้บ่นว่า popup login เด้งบ่อยเกินไป ให้เพิ่ม localStorage flag แบบ
   "ปิดแล้วไม่เด้งอีกในเซสชันนี้/browser นี้" - ยังไม่ได้ทำไว้ตอนนี้เพราะผู้ใช้
   ขอแบบเด้งทุกครั้งตรงๆ
3. Backend ยัง pending การ deploy ค้างจาก entry ก่อนหน้า (schema
   `0006_chat_profile_and_history.sql` + logic prefix "admin ") - เตือนซ้ำ
   ไว้เผื่อลืม

## 2026-07-18 14:44 ICT

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม** (บัญชีนี้ /
branch `claude/solar-optimization-forecasting-jryux7`)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ผู้ใช้ส่งรูปโลโก้ 5 องค์กรมาให้ (PTT LNG, PE LNG, Electrical Engineering
Chula, Chula Engineering ACTNOW, Chulalongkorn University) ขอให้ใส่เหนือ
หน้า login และท้ายเว็บหลัก พร้อม favicon ของเว็บเอง - ทำเสร็จแล้ว commit
`65b8737`:

1. **ดึงรูปที่ผู้ใช้ส่งมาได้จริง** - รูปที่ส่งมาในแชทไม่ได้ถูกเซฟเป็นไฟล์ใน
   `/root/.claude/uploads/` เหมือน attachment ทั่วไป (มีแต่ของเก่าตั้งแต่
   14 ก.ค.) แต่หาเจอว่าถูกเก็บเป็น base64 อยู่ใน JSONL transcript ของ session
   เอง (`/root/.claude/projects/.../*.jsonl`) - เขียนสคริปต์ python ดึง
   base64 image blocks ออกมา decode เป็นไฟล์จริง แล้ว verify ด้วยการเปิดดูรูป
   เทียบกับที่ผู้ใช้ส่งมาทีละรูปจนมั่นใจว่าตรงกัน 100% ก่อนเอาไปใช้ (เผื่อ
   session ถัดไปเจอสถานการณ์คล้ายกัน - ผู้ใช้ส่งรูปมาแต่หาไฟล์ไม่เจอใน
   uploads ปกติ ให้ลองเช็ค JSONL transcript แบบนี้)
2. **ครอปรูปให้เรียบร้อย** - บางรูปมี transparent padding เยอะมาก (เช่น Chula
   Engineering ACTNOW มี whitespace รอบข้อความเยอะมาก) ใช้ Pillow (`pip
   install Pillow`) crop ตาม bounding box ของ pixel ที่ไม่ใช่ transparent ก่อน
   เซฟเป็น PNG ใน `web/public/logos/`
3. **ออกแบบ favicon + site logo ของเว็บเอง** (ผู้ใช้ถามว่าเคยทำไว้รึยัง - ยัง
   ไม่เคย เดิม favicon เป็น placeholder ของ Vite scaffold ตั้งแต่วันแรก ไม่เคย
   เปลี่ยน) - ใช้ตัวการ์ตูนน้อง Solar เองเป็นฐาน (SVG path เดียวกับใน
   `MascotFace.tsx` เป๊ะๆ เพื่อความสอดคล้องของ brand): `favicon.svg` แบบง่าย
   ให้อ่านออกแม้ที่ 16x16, และ `site-logo.svg` แบบเต็มรูป (ไอคอน+ตัวหนังสือ
   "Nong Fab / Solar EMS") สำหรับใช้เป็น "โลโก้ของเว็บเอง" ในแถวโลโก้ ยังแก้
   `<title>` จาก "web" (default เดิม) เป็น "Nong Fab Solar EMS" ด้วยเลย
4. **สร้าง `OrgLogos.tsx`** component ใช้ร่วมกัน 2 จุด: หน้า login (เหนือฟอร์ม
   sign-in, ขนาดใหญ่กว่า) และ footer ท้ายทุกหน้าที่ login แล้ว (เล็กกว่า) -
   เรียง 6 โลโก้ (site logo ของเว็บเอง + 5 องค์กร) แถวเดียวกันแบบ responsive
   wrap
5. **Footer ไม่บังเนื้อหาเว็บเด็ดขาดตามที่ผู้ใช้กำชับ** - เพิ่ม `<footer>`
   แบบ normal document flow (ไม่ใช้ position:fixed) ต่อท้าย `<main>` ใน
   `Layout.tsx` ทำให้มีแต่ดันหน้าเว็บให้สูงขึ้น ไม่มีทางไปทับเนื้อหา
   dashboard หรือปุ่มลอย mascot/แชทที่มุมล่างทั้งสองได้เลย เพิ่ม
   padding-bottom เยอะพอ (140px) กันไม่ให้แถวโลโก้ไปชนปุ่มลอยพอดีด้วย
6. **แก้ contrast bug ที่เจอจาก live verify**: ตัวหนังสือ "Nong Fab" ใน
   site-logo.svg (สีเข้ม #1f2430) อ่านไม่ออกเลยตอน dark mode - แก้โดยใส่
   `<style>@media (prefers-color-scheme: dark)` ไว้ข้างในไฟล์ SVG เอง (SVG
   ที่โหลดผ่าน `<img>` ยัง evaluate media query ของตัวเองตาม OS/browser
   preference ได้ปกติ)
7. ทดสอบครบ: frontend suite เต็ม 184 ตัวผ่าน (เพิ่ม `OrgLogos.test.tsx`)
   `tsc` ผ่าน verify จริงด้วย Playwright ทั้ง light/dark mode ทั้งหน้า login
   และ footer เห็นโลโก้ครบ 6 อัน ไม่มีการซ้อนทับกับปุ่มลอยเลย

### บริบทและสถานะปัจจุบัน (Current Context & State)

- **เทคนิคใหม่ที่ได้เรียนรู้**: เวลาผู้ใช้ส่งรูปมาในแชทแต่หาไฟล์ไม่เจอใน
  `/root/.claude/uploads/<session-id>/` (ซึ่งมักมีแต่ไฟล์เก่าจาก context
  ตอนต้น session) ให้ลองดึงจาก JSONL transcript ของ session ที่
  `/root/.claude/projects/-home-user-solarnwpmos/<session-id>.jsonl` แทน -
  รูปที่ส่งมาใหม่ล่าสุดจะอยู่เป็น `image` content block พร้อม
  `source.data` เป็น base64 ในนั้น
- ไฟล์โลโก้ทั้งหมดอยู่ที่ `web/public/logos/` (ptt-lng.png, pe-lng.png,
  ee-chula.png, chula-engineering.png, chula-university.png, site-logo.svg)
  - เสิร์ฟตรงจาก Vite public folder ไม่ต้อง import
- ยังไม่ได้ทำระบบ favicon หลายขนาด (apple-touch-icon, PNG fallback สำหรับ
  browser เก่าที่ไม่รองรับ SVG favicon) - ใช้แค่ SVG เดียวตามที่ scaffold
  เดิมตั้งไว้แล้ว (เพียงพอสำหรับ browser สมัยใหม่ทั้งหมด)

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **งานที่ผู้ใช้ขอไว้ล่าสุดเสร็จครบแล้ว** - รอฟีดแบ็กหรือคำสั่งเพิ่มเติม
2. รอบนี้ไม่แตะ backend เลย - **ไม่ต้อง** กด Railway deploy สำหรับงานรอบนี้
   แต่ยังมีงานค้างจาก entry ก่อนๆ ที่อาจยังไม่ได้กด (ดู entry ก่อนหน้า)

---

## 2026-07-18 14:46 ICT

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

งาน Track 1 ตอบสนอง 4 ข้อที่ผู้ใช้ขอเรื่อง "การแข่งขันของโมเดล" (model
competition) ในหน้า Forecast:

1. **Backend - เปิดเผย RMSE ของทั้ง 3 โมเดล ไม่ใช่แค่ตัวที่ชนะ**:
   `HourAheadKStepModel` (`forecast/hour_ahead.py`) เพิ่ม field
   `candidate_rmse_by_lead_hour: dict[int, dict[str, float]]` -
   `training.py`'s `_train_hour_ahead_kstep()` populate จากตัวเลขที่คำนวณอยู่
   แล้ว (ของเดิมแค่ log ลง MLflow แล้วทิ้ง ไม่เคยเก็บไว้บน model object) ใช้
   `getattr(..., {})` เพื่อ backward-compat กับโมเดลเก่าที่ train ก่อนมี
   field นี้ (ไม่ต้อง retrain) - `predict_hour_ahead_kstep()` ส่งออกเป็น
   column `candidate_errors`, `serving.py`'s `ForecastPoint` เพิ่ม field
   เดียวกัน, `local_store.py`'s `forecast_history` table เพิ่มคอลัมน์ JSON
   พร้อม migration อัตโนมัติสำหรับ DB เก่า, ผ่านทั้ง 2 API routes
   (`api/routes_forecast.py` และ `forecast/api.py`)
2. **Frontend - เส้น error 3 สีแยกตามโมเดลในกราฟหลัก**: แทนที่เส้นประสีเทา
   เส้นเดียว (เดิมโชว์แค่ตัวชนะ) ด้วย 3 เส้นสี LightGBM (เขียว)/Random
   Forest (ส้ม)/Sum-k LSTM (ฟ้า) - สีเดียวกับจุดสีบนกราฟเดิม ใช้ tooltip
   รวม Generated power + Forecast + RMSE ทั้ง 3 โมเดล + Prediction interval
   ในกล่องเดียว (ตามที่ผู้ใช้ขอ)
3. **Frontend - แถบ "การแข่งขันของโมเดล" แยกใหม่**: panel ใหม่ทั้งหมด
   (`ModelCompetitionPanel` ใน `ForecastPage.tsx`) แสดงกราฟแท่งเทียบ RMSE
   ทั้ง 3 โมเดลต่อชั่วโมงล่วงหน้า (+1h ถึง +6h) แท่งของโมเดลที่ชนะทึบ (opacity
   1) แท่งที่แพ้จาง (opacity 0.3) - แสดงตลอดเวลาไม่ขึ้นกับ toggle
   Day-ahead/Intra-day (เหมือน panel Minute-ahead)
4. **เสนอ metric เปรียบเทียบโมเดลแบบอื่น**: ตามที่ผู้ใช้เปิดโอกาสให้เสนอ -
   เพิ่ม "spread" (ผลต่าง RMSE สูงสุด-ต่ำสุดของโมเดลที่แข่งกันในชั่วโมงนั้น)
   เป็นของแถมเบาๆ ในแถบการแข่งขัน (โชว์ใน tooltip) เพราะข้อมูลพร้อมอยู่แล้ว
   ไม่ต้องแก้ backend เพิ่ม - ส่วน metric แบบ "live ensemble disagreement"
   (ส่วนเบี่ยงเบนของค่าพยากรณ์สดจริงระหว่าง 3 โมเดล ไม่ใช่แค่ validation
   RMSE) เสนอไว้ในคำแนะนำการอ่านหน้า (guide panel) ว่าเป็นแนวคิดที่มีประโยชน์
   จริง แต่ยังไม่ได้ทำ เพราะต้องเก็บโมเดลที่แพ้ทั้งหมดไว้ inference คู่ขนาน
   ตลอดเวลา (ตอนนี้ระบบเก็บแค่โมเดลที่ชนะต่อ lead hour) เป็นงาน backend ที่
   ใหญ่กว่านี้มาก - รอผู้ใช้ตัดสินใจว่าอยากให้ทำต่อไหม
5. **Guide panel**: เพิ่ม section ใหม่ "ค่าความคลาดเคลื่อน (RMSE) คืออะไร
   และทำไมถึงสำคัญ" ใน `ViewerGuidePanel` อธิบาย RMSE คืออะไร/ทำไมสำคัญ/ใช้
   แบบ held-out validation ไม่ใช่ training/ทำไมเลือก RMSE ไม่ใช่ MAE/ความ
   ต่างเส้น 3 สี vs. แถบแข่งขัน/ความหมายของ spread ครบตามที่ผู้ใช้ขอ

**ทดสอบครบ**: backend 135 (forecast) + 137 (api) ผ่านหมด (13 test ใหม่),
frontend 177 ผ่านหมด (7 ใหม่ใน `chartData.test.ts`, 2 ใหม่ใน
`ForecastPage.test.tsx`), `tsc --noEmit` ผ่าน **live-verify จริงผ่าน
Playwright**: boot `uvicorn` จริง + train โมเดลจริงผ่าน dev API, login เข้า
dashboard จริง, ยืนยันเส้น 3 สี+tooltip รวม, ยืนยัน opacity ของแท่งชนะ/แพ้
ตรงจาก SVG attribute จริง (ไม่ใช่แค่มองด้วยตา), ยืนยัน guide panel ใหม่
render ถูกต้อง

### บริบทและสถานะปัจจุบัน (Current Context & State)

- **เจอปัญหา branch ไม่ตรงกันตอนต้น turn นี้**: คำสั่งระดับ system บอกให้ใช้
  branch `claude/solar-website-modules-msyvv5` แต่ branch นั้นไม่มีอยู่จริง
  บน remote เลย ในขณะที่งานทั้งหมดของ session นี้ (รวม Track1/Track2 handoff
  system, HANDOFF.md นี้เอง) อยู่บน `claude/solar-optimization-forecasting-
  jryux7` - ถามผู้ใช้แล้ว ผู้ใช้ยืนยันให้ push ไปที่ jryux7 ตามเดิม
  (คำสั่ง branch ที่ระบบให้มาผิด/ไม่ตรงกับ session นี้จริง)
- Field ใหม่ `candidate_errors` เป็น `null`/`{}` เสมอสำหรับ minute/day/
  physics-baseline horizon - มีความหมายเฉพาะ hour-ahead เท่านั้น (เหมือน
  field `error` เดิม)
- โมเดลที่ train ไปแล้วก่อนหน้านี้ (ถ้ามีบน production MLflow registry) จะไม่
  มี `candidate_rmse_by_lead_hour` จนกว่าจะ retrain ใหม่ - ไม่ error แค่โชว์
  `candidate_errors: {}` ไปก่อน (graceful degradation ตามที่ตั้งใจไว้)
- **Railway ยังไม่ auto-deploy** (ตามปกติ) - session นี้แก้ `api/` (
  `routes_forecast.py`) และ `forecast/` (ซึ่ง `api/` depend อยู่) เพิ่มเติม -
  ต้องกด Deploy บน Railway เองหลัง push (purple "Deploy" button, tab
  Deployments ของ service `api`)
- ไฟล์ทดสอบชั่วคราวที่สร้างระหว่าง verify (`dev.db`, `mlflow.db`,
  `real_data.db`, `verify-tmp*.mjs`) ลบออกหมดแล้วก่อน commit - `git status`
  สะอาด

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **ต้องกด Deploy บน Railway ด้วยตัวเอง** หลัง push นี้ (ดูรายละเอียดด้านบน)
   - ไม่งั้น production API จะยังไม่มี field `candidate_errors` ใหม่
2. **รอ feedback จากผู้ใช้เรื่อง live ensemble disagreement metric** - เสนอ
   ไว้แล้วว่ามีประโยชน์แต่เป็นงาน backend ใหญ่กว่านี้ (ต้องเก็บโมเดลที่แพ้
   ไว้ inference คู่ขนาน) ถ้าผู้ใช้อยากได้ค่อยเริ่มออกแบบรายละเอียดเพิ่ม
3. โมเดลจริงบน production ยังไม่ได้ retrain หลัง deploy รอบนี้ - เมื่อ
   retrain รอบถัดไปเกิดขึ้น (อัตโนมัติผ่าน adaptive retrain loop) ค่า
   `candidate_errors` จะเริ่มมีข้อมูลจริงให้ผู้ใช้เห็นบน dashboard
4. ยังไม่มีการปรับเกณฑ์การแข่งขันให้ Sum-k LSTM มีโอกาสชนะมากขึ้น (ยังไม่เคย
   ชนะ lead hour ไหนเลยจากการทดสอบ synthetic data ทั้งหมด) - ค้างมาจาก
   session ก่อนหน้า ยังไม่มีการตัดสินใจจากผู้ใช้ อาจจะไม่จำเป็นแล้วเพราะตอนนี้
   โชว์ RMSE ของทั้ง 3 โมเดลให้เห็นความโปร่งใสแทน

---

## 2026-07-18 17:11 ICT

**Track 1 — เนื้อหาเชิงวิชาการ (Content/Engineering)**

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

ผู้ใช้ขอให้เส้น "กำลังไฟฟ้าที่ผลิตได้จริง" (เดิมเป็นแท่งสีม่วง แสดงแค่วันนี้)
ย้อนหลังได้หลายวันเหมือนเส้น Forecast พร้อมแยกสีตามความใหม่ของข้อมูล และขอ
เพิ่มเติมที่กราฟ Minute-ahead ด้วย - ทำเสร็จแล้วครบทุกข้อ:

1. **Backend ใหม่ทั้งหมด** - `/performance/{zone}` เดิมไม่มีการเก็บข้อมูลย้อนหลัง
   เลย (คำนวณสดทุกครั้ง เฉพาะ "วันนี้") จึงสร้างกลไกใหม่: `record_generated_
   power()` (บันทึกค่าจริงทุกครั้งที่ poll), `backfill_generated_power_
   history()` (seed ย้อนหลัง 72 ชม. ตอน boot ด้วย physics-baseline เหมือนที่ทำ
   ให้ฝั่ง Forecast ไปแล้ว), `generated_power_history()` (อ่านกลับ) - ใช้ตาราง
   `forecast_history` เดิมซ้ำ (ไม่สร้างตารางใหม่) ผ่าน pseudo-horizon tag
   `"generated"` เพิ่ม field `history` ใน response ของ `/performance/{zone}`
2. **แยกสี 3 ระดับตามที่ผู้ใช้ระบุ**: (1) ก่อนวันนี้ = สีน้ำตาล/ทอง (2) วันนี้
   ที่ผ่านไปแล้ว = สีชมพู (3) ค่าล่าสุด/ปัจจุบัน = สีม่วงเดิม (ตามที่ผู้ใช้ขอ
   ให้ใช้สีเดิมต่อ) - แทนที่แท่งสีม่วงอันเดียวด้วยเส้น 3 สีในกราฟหลัก
3. **Minute-ahead panel**: (4.1) เพิ่มเส้นพยากรณ์ย้อนหลัง ~30 นาที ใช้สีเดิม
   (ใช้ `useForecastHistory` hook ตัวเดียวกับกราฟหลัก) (4.2) เพิ่มเส้นข้อมูล
   จริง 3 สีเดียวกับข้อ 2 ทับบนกราฟนี้ด้วย (ใช้ข้อมูลรายชั่วโมงเพราะไม่มี
   ข้อมูลจริงระดับนาที)
4. **บั๊กจริงที่เจอจาก live-test**: สีแรกที่เลือกให้ "ก่อนวันนี้" (indigo
   #4338ca) พอเอาขึ้นจริงแล้วดูใกล้เคียงกับสีน้ำเงินของเส้น Forecast มาก
   จนแยกไม่ออก (ตรงข้ามกับเป้าหมายของ feature นี้เป๊ะๆ) - เจอจาก screenshot
   จริงไม่ใช่แค่เดา แก้เป็นสีน้ำตาล/ทอง (#92400e/#d97706) แทน เพราะเป็น hue
   เดียวที่ยังไม่ถูกใช้ในกราฟนี้เลย (น้ำเงิน/เขียว/ส้ม/ฟ้าอมเขียว/แดง/ม่วง/
   ชมพู ถูกใช้หมดแล้ว)
5. ทดสอบครบ: backend forecast 140 + api 141 ผ่านหมด (11 test ใหม่), frontend
   204 ผ่านหมด (12 ใหม่ใน chartData/timeScrub/ForecastPage tests) `tsc`
   ผ่าน **live-verify จริงผ่าน Playwright**: boot uvicorn จริง ยืนยัน fresh
   boot มี history 72 แถวทันที (ไม่มี cold-start gap), เปิด dashboard จริง
   ยืนยันสีทั้ง 3 ระดับ + tooltip ถูกต้อง + dark mode + ทำงานร่วมกับเส้น error
   3 สีของโมเดลใน Intra-day ได้โดยไม่ชนกัน

### บริบทและสถานะปัจจุบัน (Current Context & State)

- **ตอบคำถามผู้ใช้เรื่อง PVOutput.org ระหว่างทำงาน**: เช็คแล้วไม่มีร่องรอยว่า
  เคยทดสอบจริง - ในอดีตแค่ "พิจารณาแล้วพักไว้" เพราะ PVOutput/NREL PVDAQ/
  Ausgrid ให้ข้อมูลกำลังผลิตจริงของ**โรงงานอื่น** ไม่ใช่หนองฟาบเอง เลยใช้แทน
  telemetry จริงไม่ได้ - ใช้ PVGIS แทนแล้ว (แต่ใช้แค่ฝั่งสภาพอากาศ ไม่ใช่กำลัง
  ผลิต) ถ้าผู้ใช้ทดสอบ PVOutput.org แล้วเจอข้อมูลของหนองฟาบจริง ค่อยกลับมาคุย
  ต่อได้
- Field ใหม่ `history` ใน `/performance` เป็นข้อมูลจาก physics-baseline
  ประมาณการเช่นเดียวกับที่ใช้ backfill ฝั่ง Forecast - ไม่ใช่ telemetry จริง
  (ระบบนี้ไม่มี telemetry จริงจากที่ไหนเลยตามที่เตือนไว้ตลอด) แต่จะเริ่มมีค่า
  จาก live poll จริงสะสมไปเรื่อยๆ นับจากนี้ (ทับค่า backfill ทีละชั่วโมง)
- **Railway ยังไม่ auto-deploy** - session นี้แก้ `api/` (`routes_performance.
  py`, `ingestion_scheduler.py`) และ `forecast/` (`serving.py`) เพิ่มเติม -
  ต้องกด Deploy บน Railway เองหลัง push (purple "Deploy" button, tab
  Deployments ของ service `api`)
- ไฟล์ทดสอบชั่วคราวที่สร้างระหว่าง verify (`dev.db`, `mlflow.db`,
  `real_data.db`, `verify-tmp*.mjs`) ลบออกหมดแล้วก่อน commit - `git status`
  สะอาด

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **ต้องกด Deploy บน Railway ด้วยตัวเอง** หลัง push นี้ - ไม่งั้น
   production `/performance` จะยังไม่มี field `history` ใหม่ และจะไม่เริ่ม
   สะสมข้อมูลจริงเลย
2. รอ feedback ผู้ใช้เรื่อง PVOutput.org (ดูรายละเอียดด้านบน) - ถ้าอยากให้
   ลองต่อ หรือมีผลทดสอบมาแล้ว บอกได้เลย
3. งานที่ผู้ใช้ขอไว้ล่าสุดเสร็จครบทั้ง 4 ข้อ (สี 3 ระดับ + Minute-ahead
   ย้อนหลัง + ข้อมูลจริงทับกราฟ minute) - รอ feedback หรือคำสั่งเพิ่มเติม
