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

---

## 2026-07-18T10:10:09Z

**Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม**
(เขียนถึงเพื่อน Track 1 — เนื้อหาเชิงวิชาการ/Engineering ด้วย เพราะ entry
นี้แตะ `api/` เล็กน้อย ดูหัวข้อ deploy reminder ด้านล่าง)

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

1. **ขยายโลโก้/หน้า login ให้ใหญ่และเด่นขึ้น** ตามฟีดแบ็กว่า "โลโก้มันเล็กไป":
   - `OrgLogos.css`: แถวโลโก้หน้า login สูงจาก 46px → 76px (footer 28px →
     38px), เพิ่ม gap/padding ให้พอดีหน้าเว็บมากขึ้น
   - `LoginWelcome.css`: popup แนะนำของน้อง Solar ใหญ่ขึ้นชัดเจน (max-width
     480px → min(94vw, 860px), มาสคอต 140px → 200px, หัวข้อ/เนื้อหา/ปุ่มฟอนต์
     ใหญ่ขึ้นทั้งหมด, ปรับรายการฟีเจอร์เป็น 2 คอลัมน์บนจอกว้างเพื่อจัดระเบียบ)
   - `App.css` (`.login-form`): ช่องกรอก username/password ใหญ่ขึ้นชัดเจน
     (font 20px, padding 16px, border 2px, label 18px ตัวหนา) ตามคำขอ
     "คนแก่จะได้เห็นแล้วกรอกได้"
2. **ตอบคำถาม Feedback admin-only**: ยืนยันแล้วว่า `/admin/feedback` ถูกปิด
   เฉพาะ admin จริง 3 ชั้น - (1) nav link condition ใน `Layout.tsx`
   (`role === 'admin'`), (2) `RequireAdmin` wrapper ใน `App.tsx` เด้งกลับ
   `/forecast` ถ้าไม่ใช่ admin, (3) `GET /feedback` มี
   `require_role("admin")` ฝั่ง backend คืน 403 ให้ viewer/operator เสมอ
   (มี test `test_viewer_cannot_list_feedback` ยืนยันอยู่แล้ว) - ไม่มีช่องโหว่
3. **สร้าง `SiteCredit.tsx`** - แถบเครดิตผู้พัฒนาเว็บ แสดงในตำแหน่งเดียวกับ
   nav "Feedback" แต่สำหรับ viewer/operator เท่านั้น เนื้อหา**เว้นว่างไว้ก่อน
   ตามคำสั่งผู้ใช้** (ยังไม่ส่ง credit text จริงมาให้ + Claude Code credit
   ใกล้หมด) - component มี prop `text` default เป็น const ว่าง ถ้าไม่มีข้อความ
   จะ `return null` ไม่แสดงอะไรเลย พอ user ส่งข้อความเครดิตจริงมาทีหลังแค่ใส่
   string ใน `CREDIT_TEXT` ก็จะโผล่อัตโนมัติ ไม่ต้องแก้ที่อื่น
4. **เจอและแก้ bug จริงของปัญหา "login pttlng/12345 ไม่ได้"**: ผู้ใช้ถามว่า
   Railway deploy 2 ทาง (Track1 + Track2) ชนกันหรือเป็นที่ Cloudflare -
   **ไม่ใช่ทั้งสองอย่าง** สาเหตุจริงคือ bug ใน `auth.py`:
   `seed_demo_users_if_empty()` เดิมจะ seed demo accounts เฉพาะตอนตาราง
   `users` "ว่างเปล่าทั้งหมด" เท่านั้น - แต่ฐานข้อมูล Postgres บน Railway ถูก
   seed ไปนานแล้วตั้งแต่ตอนสร้าง Module 6 (ด้วย `viewer`/`viewer-demo-pw`
   ชุดเดิม) ก่อนที่จะมีการเปลี่ยน `DEMO_USERS` ให้เป็น `pttlng`/`12345`
   (task #102) ดังนั้นตารางไม่เคย "ว่าง" อีกเลย ทำให้ account `pttlng` ใหม่
   ไม่เคยถูกสร้างจริงบน production - popup ต้อนรับหน้า login โฆษณา
   credential ที่ไม่มีอยู่จริงในฐานข้อมูล **แก้แล้ว**: เปลี่ยนเป็น
   `seed_demo_users()` ที่เช็คทีละ username (`get_by_username`) แทน สร้างเฉพาะ
   account ที่ยังไม่มี ปลอดภัยกับ user จริงเสมอ (ไม่แตะ/ไม่ทับ), เรียกได้ทุก
   startup - ทดสอบ end-to-end แล้วโดยจำลอง DB เก่าของ Railway (มีแค่
   `admin`/`operator`/`viewer` ชุดเดิม) แล้ว boot API ขึ้นมาใหม่ ยืนยันว่า
   `pttlng`/`12345` login ผ่านจริง (พร้อมกับ `viewer`/`viewer-demo-pw` เดิมก็
   ยังใช้ได้ปกติ ไม่ทับของเก่า)
5. **ทดสอบครบทุกชั้น**: backend `pytest` 140/140 ผ่าน (เพิ่ม 3 test ใหม่ให้
   `seed_demo_users`), frontend `vitest` 186/186 ผ่าน (เพิ่ม `SiteCredit.
   test.tsx`), `tsc --noEmit` ผ่าน, live verify ด้วย Playwright จริง (ไม่ใช่
   แค่ unit test): หน้า login ทั้ง light/dark mode เห็นโลโก้/ฟอร์มใหญ่ขึ้น
   ชัดเจน, login เป็น admin เห็น nav "Feedback", login เป็น pttlng/operator
   ไม่เห็น nav นั้น (ไม่มี layout พัง), และยืนยัน `pttlng`/`12345` login
   สำเร็จจริงผ่าน API ที่จำลองสภาพ DB เดิมของ Railway

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ไฟล์หลักที่แก้: `web/src/components/OrgLogos.css`, `LoginWelcome.css`,
  `App.css`, `Layout.tsx` (ใหม่: `SiteCredit.tsx`/`.css` + test),
  `api/src/nongfab_api/auth.py` (`seed_demo_users_if_empty` →
  `seed_demo_users`, logic เปลี่ยนจาก table-empty เป็น per-account),
  `main.py` (เรียกชื่อ method ใหม่), `tests/test_auth.py`, `api/README.md`
- **`SiteCredit.tsx`** ยังไม่มีเนื้อหาจริง - รอ user ส่งชื่อ/ข้อความเครดิตมา
  แล้วใส่ใน `CREDIT_TEXT` const ในไฟล์นั้น (ปัจจุบันเป็น `''` ว่างเปล่า)
- **สำคัญสำหรับ Track 1**: entry นี้แตะ `api/src/nongfab_api/auth.py` และ
  `main.py` ซึ่งปกติเป็นพื้นที่ของ Track 1 - เหตุผลที่ Track 2 แก้เองคือ
  bug นี้เกิดจาก feature ที่ Track 2 สร้างเอง (`pttlng` demo account สำหรับ
  ระบบ visitor network/chat ที่ต้อง sign-in) และเป็น fix ที่ปลอดภัย/scope
  แคบมาก (แค่เปลี่ยนเงื่อนไข seed ให้เช็คทีละ account) - ถ้า Track 1 อยาก
  ตรวจทานโค้ดส่วนนี้เพิ่มเติมยินดีมาก
- คำถามเรื่อง Railway auto-deploy จาก 2 บัญชี: ตามความเข้าใจของ session นี้
  (ไม่ได้เข้าไปดู Railway dashboard จริง) การที่ทั้งสองบัญชี push ไปที่
  branch เดียวกัน (`claude/solar-optimization-forecasting-jryux7`) ตามลำดับ
  (ไม่ได้ push พร้อมกันจริงๆในเสี้ยววินาทีเดียวกัน) ปกติไม่ทำให้ Railway
  "เลือกทำแค่อันเดียว" - Railway (ถ้า auto-deploy ทำงานจริง) จะ deploy
  commit ล่าสุดสุดของ branch ซึ่งรวมงานทั้งสองบัญชีอยู่แล้วเพราะเป็น branch
  history เดียวกัน กรณีที่ "งานของอีกบัญชียังไม่โผล่ในเว็บ" น่าจะเป็นเพราะ (ก)
  ยังไม่ได้กด Deploy บน Railway (ดู standing reminder), หรือ (ข)
  auto-deploy ที่เพิ่งปรับยังไม่ได้ทำงานจริงตามที่ Railway แสดง - แนะนำให้
  เช็คที่ Railway dashboard → api service → Deployments tab ว่า commit ล่าสุด
  ขึ้นจริงหรือยัง เคสนี้ยืนยันแล้วว่า**ไม่ใช่สาเหตุของปัญหา login pttlng** -
  นั่นเป็น bug ในโค้ด seed ที่แก้ไปแล้วข้างบน

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **⚠️ Reminder: entry นี้แตะ `api/` (auth.py, main.py)** - ตาม standing
   reminder ต้องกด "Deploy" บน Railway dashboard เองด้วยมือ (api service →
   Deployments tab → ปุ่มสีม่วง) เพื่อให้ fix ของ `pttlng` login ไปโผล่จริงบน
   production - ถ้า auto-deploy ที่ user เพิ่งปรับทำงานได้แล้วจริงๆ อาจไม่ต้อง
   กด แต่ควรเช็คใน Railway dashboard ให้แน่ใจว่า deploy ล่าสุดมี commit นี้จริง
2. รอ user ยืนยันว่า login ด้วย `pttlng`/`12345` บน production ใช้ได้แล้ว
   หลัง deploy รอบนี้ขึ้นจริง
3. รอ user ส่งข้อความเครดิตจริงสำหรับใส่ใน `SiteCredit.tsx`'s `CREDIT_TEXT`
4. Financial module ยังใช้ placeholder เหมือนเดิม (ไม่ได้แตะรอบนี้) -
   ยังรอ CAPEX/PEA tariff/WACC/BOI ตัวจริงจาก user อยู่

## 2026-07-18 18:35 ICT

**Track 1 - เนื้อหาเชิงวิชาการ (Content/Engineering)**

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

- **แก้ bug จริง - กราฟ "การแข่งขันของโมเดล (Model Competition)" ว่างเปล่า
  (มีแกน+legend แต่ไม่มีแท่งกราฟเลย)**: root cause คือ `web/src/lib/
  chartData.ts`'s `buildCompetitionRows()` มี grace window ผิด (`now - 1h`
  แทนที่จะเป็น `now` ตรงๆ ตามที่ docstring ของฟังก์ชันเองบอกไว้) ทำให้ชั่วโมง
  ที่เพิ่งผ่านไปหมาดๆ (ไม่มี candidate_errors แล้วเพราะหลุดจาก live k-step
  window ไปแล้ว) หลุดเข้ามาปนกับ 6 จุดพยากรณ์จริง โดนติดป้าย "+1h" ผิดๆ
  (แท่งว่างหมด) แล้วดันจุด +6h ตัวจริงหลุดออกจาก cap 6 แถวไปเลย - แก้เป็น
  `>= nowMs` เฉยๆ ตรงตาม docstring พร้อม regression test ใหม่ที่จำลอง
  สถานการณ์นี้ตรงๆ
- **เปลี่ยนแกน x ของ Model Competition** จากป้าย relative "+1h..+6h" เป็น
  เวลาอ้างอิงจริง (`formatDateHourIct`, เหมือนกราฟอื่นในหน้านี้) เอียงป้าย
  กันทับ, เพิ่มตัวเลขค่าบนแท่งกราฟ (`LabelList`) ให้อ่านค่าได้โดยไม่ต้องชี้เมาส์
- **ตรวจแล้ว: "แยกตามโซน All/GIS/ISB/Jetty" ทำงานถูกต้องอยู่แล้ว** - เช็คตรง
  จาก `/forecast/{zone}/hour` เห็นค่าต่างกันจริงในแต่ละโซน และ verify ผ่าน
  screenshot ว่าสลับแท็บแล้วแท่งกราฟเปลี่ยนค่าจริง - ที่ดูเหมือน "ค้างที่ All"
  คือผลจาก bug ข้อแรกที่ทำให้ทุกแท็บว่างเหมือนกันหมดจนแยกไม่ออก ไม่ใช่ bug
  เรื่อง zone แยกต่างหาก
- **ตรวจแล้ว: generated power ไม่โผล่ในอนาคตแล้ว** (`truncateGeneratedToNow`
  ที่มีอยู่แล้วตั้งแต่รอบก่อนทำงานถูกต้อง, verify ผ่าน screenshot ทั้ง
  All/GIS/ISB/Jetty ทั้ง Day-ahead/Intra-day) - screenshot ที่ user ส่งมา
  (แสดงแท่งสีม่วง "Generated power" อันเดียว) เป็นภาพเก่าก่อน deploy เส้น
  3 สีล่าสุด ไม่ใช่ bug ที่ยัง repro ได้จริงในโค้ดปัจจุบัน
- **ตรวจแล้ว: Day-ahead ไม่ถึง 72 ชม./3 วัน ไม่ใช่ code bug** - โค้ดรองรับ
  72 ชม. ถูกต้องทั้ง synthetic fallback (ยืนยันตรง: ให้ 144 จุดเป๊ะ = อดีต 72
  + อนาคต 72) และ real-data path (ไม่มี cap ปลอมนอกจาก `[:72]` จากบนลงล่าง)
  - ระยะที่เห็นจริงขึ้นกับว่า real NWP อนาคตสะสมมาไกลแค่ไหนจาก live poller
  เท่านั้น เจอ stale config ระหว่างตรวจ: `ingestion/nwp`'s
  `_default_forecast_hours()` ยังจำกัด 48ชม. ทั้งที่ Day-ahead ขยายเป็น
  72ชม.ไปนานแล้ว (คนละตัวกับ `api/config.py`'s ที่ถูกต้องอยู่แล้ว 72ชม.
  ซึ่งเป็นตัวที่ live poller ใช้จริง) - แก้ให้ตรงกันแล้ว เผื่อใครอาศัย default
  ตัวนี้ตรงๆ ในอนาคต
- **แก้ bug ดวงอาทิตย์ใน 3D view เล็กเกินไป**: ระยะโคจร+ขนาดลูกบอลเดิม fix
  ตายตัวค่าเดียว ไม่ scale ตามขนาดจริงของแต่ละโซน (โดยเฉพาะ Jetty ที่กระจาย
  ยาว ~1.25กม.) แก้ให้ scale ตาม `bounds.focus.span` ของแต่ละโซนจริง พร้อม
  เพิ่ม glow halo รอบดวงอาทิตย์ให้เห็นชัดขึ้นมาก - verify ผ่าน screenshot
  จริงหลังหมุนกล้อง (เทียบสี pixel `#fde047` ในภาพ ไม่ใช่แค่เดาจากตา)
  - **พบเพิ่มเติมนอกโจทย์**: กล้องเริ่มต้น (ก่อนหมุนเอง) ของ 3D view บ่อยครั้ง
    ไม่ครอบตำแหน่งดวงอาทิตย์ปัจจุบันเลย (นอก view frustum) ไม่ว่าขนาดจะใหญ่
    แค่ไหน - ยืนยันว่าเป็นปัญหาเดิมที่มีอยู่ก่อนแก้รอบนี้ (คำนวณเทียบกับค่า
    fix เดิมแล้วก็ตกขอบเหมือนกัน) ยังไม่ได้แก้ - ต้องหมุนกล้องเอง
    (OrbitControls ปกติ) ถึงจะเห็น เสนอเป็นตัวเลือกทำต่อในข้อ next steps
    ด้านล่าง ไม่ได้ทำเองโดยไม่ถามเพราะแตะ logic กล้องที่ใหญ่กว่านี้ (เชื่อมกับ
    ปุ่ม "reset camera" ด้วย)
- Test ทั้งหมดผ่าน: web 229/229 (`tsc` clean, `oxlint` clean), `ingestion/
  nwp` 41 passed/5 skipped (`ruff check` clean), `api` 142 passed (ไม่ถูก
  กระทบรอบนี้ ไม่ได้แตะ `api/` โดยตรง)
- Commit + push แล้ว (merge เข้ากับงานของ Track 2 ที่ push มาระหว่างทาง
  เรียบร้อย ไม่มี conflict ค้าง - แก้ conflict เดียวที่เกิดใน `web/README.md`
  โดยเก็บ entry ของทั้งสอง track ไว้ครบ)
- ตอบคำถามนอกเรื่องโค้ด 2 ข้อ: (1) PVOutput.org/NREL PVDAQ/Ausgrid - ไม่
  แนะนำให้เปลี่ยนไปใช้ตัวอื่นแทน PVOutput เพราะติดข้อจำกัดเดียวกันหมด (ข้อมูล
  จริงแต่คนละโรงงาน) ทางแก้จริงคือรอสิทธิ์ Huawei FusionSolar ของ Nong Fab
  เอง; (2) เทียบ forecasting กับกรอบอ้างอิงอาจารย์ Jitkomut Songsiri - สรุป
  ว่า core architecture ตรงกันแล้ว แต่ยังมี 3 จุดเสริม (parallel models by
  time-of-day, bias-correction cascade แบบสองขั้นจริง, baseline linear
  regression) ที่ค้างรอข้อมูลจริงเหมือนกันหมด ไม่ใช่ "เสร็จสมบูรณ์ถาวร"

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ไฟล์หลักที่แก้รอบนี้: `web/src/lib/chartData.ts` (`buildCompetitionRows`),
  `web/src/pages/ForecastPage.tsx` (`ModelCompetitionPanel`), `web/src/
  components/Solar3DScene.tsx` (sun marker sizing), `ingestion/nwp/src/
  nwp_ingestion/config.py` (`_default_forecast_hours`) - พร้อม test +
  README entries คู่กันทุกจุด (`web/README.md`, `ingestion/nwp/README.md`)
- **วิธี debug ที่ใช้รอบนี้ (มีประโยชน์ถ้าเจอ bug แบบ "ดูเหมือนพัง แต่โค้ด
  อ่านแล้วดูถูก" อีก)**: อย่าเดาจาก screenshot/โค้ดอย่างเดียว - รัน local dev
  servers เอง (`uvicorn` จาก venv `/tmp/forecast-venv` + `vite dev` ที่
  `localhost:5173`/`localhost:8000`, login `pttlng`/`12345`) แล้วยิง curl
  เช็ค response จริงของ endpoint ตรงๆ ก่อนสรุปสาเหตุ - แม่นกว่าเดาเยอะ
  สำหรับปัญหา 3D sun ใช้สคริปต์ Python สแกนสี pixel (`#fde047`) ในภาพ
  screenshot จริงเพื่อยืนยันว่า render จริงหรือไม่ (แม่นกว่าเดาจากภาพเฉยๆ ที่
  อาจเล็กเกินจะสังเกตด้วยตา)
- venv `/tmp/forecast-venv` ตอนเจอตอนแรกขาด `nongfab-financial` กับ `pvgis-
  ingestion` (session ก่อนหน้าคงสร้าง venv ไว้ก่อนสองแพ็กเกจนี้จะถูกสร้าง) -
  ติดตั้งเพิ่มแล้วด้วย `pip install -e ./financial -e ./ingestion/pvgis` -
  ถ้า session หน้าเจอ `ModuleNotFoundError` แบบเดียวกันตอนรัน local server
  ให้เช็คตรงนี้ก่อน
- 2 เรื่องที่ "ตรวจแล้วไม่ใช่ code bug จริง" (generated power โผล่อนาคต,
  day-ahead ไม่ถึง 72ชม.) ไม่ได้แก้โค้ดเพิ่มเพราะพิสูจน์แล้วว่าโค้ดถูกต้องอยู่
  แล้ว/ขึ้นกับข้อมูลจริงที่สะสมมา ไม่ใช่ defect - ถ้า user เทสบน production
  แล้วยังเจออยู่ ให้สงสัยเรื่อง Railway ยังไม่ deploy ล่าสุดก่อน (ดู next
  steps ข้อ 1) หรือ browser cache เก่า ไม่ใช่รีบแก้โค้ดใหม่ทันที
- ส่ง 2 prompt สำหรับ Track 2 ให้ user ในแชทแล้วรอบนี้ (ข้อ 2 - ซ่อน
  Financial/Simulation จาก viewer role, ข้อ 3 - รวม Irradiance Map+3D View
  เป็นแท็บเดียว) - **ยังไม่ได้ implement เอง** เพราะเป็นงานฝั่ง UI/nav ตาม
  นโยบาย two-track (root `CLAUDE.md`) - รอ user ส่งต่อให้บัญชี Track 2

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **⚠️ Reminder: entry นี้แตะ `ingestion/nwp/`** ซึ่งเป็น dependency ของ
   `api/` (ดู root `CLAUDE.md`'s standing note - `ingestion/` อยู่ในลิสต์
   dependency ที่ต้อง deploy ด้วย) - ถ้า user อยากให้ Day-ahead บน
   production ใช้ `forecast_hours` default ที่แก้แล้ว ต้องกด "Deploy" เองที่
   Railway dashboard (`api` service → Deployments tab → ปุ่มสีม่วง) เหมือน
   เดิม เพราะ auto-deploy ยังใช้ไม่ได้ (ยกเว้น user ยืนยันว่าเพิ่งแก้แล้วจริง)
2. รอ user ตอบว่าอยากให้ทำต่อเรื่อง "กล้อง 3D auto-follow ดวงอาทิตย์" ไหม -
   พบเป็น side-finding รอบนี้ (กล้องเริ่มต้นไม่ครอบดวงอาทิตย์เสมอไป) ยังไม่ได้
   ทำเพราะแตะ logic กล้อง/reset-camera ที่ใหญ่กว่าขอบเขตเดิม
3. รอ user ตอบว่าอยากให้ลอง "ผสม real+synthetic estimate" สำหรับ Day-ahead
   ที่ยังไปไม่ถึง 72ชม.เต็มไหม (เสนอไว้เป็นทางเลือก ไม่ใช่สิ่งที่ควรทำเองแบบ
   ไม่ถาม เพราะเปลี่ยนความหมายของ "real" data_source)
4. รอ user ส่ง 2 prompt (hide Financial/Simulation, รวม Irradiance
   Map+3D View) ให้บัญชี Track 2 แล้วติดตามผลว่าทำเสร็จหรือยัง
5. Financial module ยังใช้ placeholder เหมือนเดิม (ไม่ได้แตะรอบนี้) - ยังรอ
   CAPEX/PEA tariff/WACC/BOI ตัวจริงจาก user อยู่

## 2026-07-18 18:46 ICT

**Track 1 - เนื้อหาเชิงวิชาการ (Content/Engineering)**

⚠️ **แจ้ง Track 2**: entry ก่อนหน้า (17:11 นี้เอง) เพิ่งเสนอ prompt ให้ไปทำ
"ซ่อน Financial/Simulation จาก viewer role" ที่ Track 2 - แต่ user สั่งกลับมา
ทันทีว่าให้ Track 1 ทำเองตรงนี้เลย (**ทำเสร็จแล้วในรอบนี้** - ไม่ต้องทำซ้ำ
ฝั่ง Track 2) ส่วน prompt ที่ 2 (รวมแท็บ Irradiance Map + 3D View) ยังคงเป็น
ของ Track 2 เหมือนเดิม ยังไม่มีใครทำ

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

- **ซ่อนแท็บ Simulation/Financial จาก viewer role** (`web/src/App.tsx`,
  `web/src/components/Layout.tsx`): เพิ่ม `RequireOperator` (export จาก
  `App.tsx`, รูปแบบเดียวกับ `RequireAdmin` ที่มีอยู่แล้วสำหรับ
  `/admin/feedback`) ครอบ route `/simulation`/`/financial` กัน viewer เข้า
  ตรงๆ ผ่าน URL ด้วย ไม่ใช่แค่ซ่อน nav link - backend already ปลอดภัยอยู่แล้ว
  (`require_role("operator")` บน `POST /simulate/{zone}`, `POST /financial`)
  เพราะฉะนั้นนี่เป็น UX fix ล้วนๆ ไม่ใช่ security boundary ใหม่
- Test ใหม่ 6 ตัว (`Layout.test.tsx` +3, `App.test.tsx` +3) full suite
  235/235, `tsc`/`oxlint` clean - live-verify ผ่าน Playwright จริง: login
  `pttlng` (viewer) เห็น nav แค่ Forecast/3D View/Energy Report/Irradiance
  Map, พิมพ์ URL ตรงไป `/financial` เด้งกลับ `/forecast` เอง; login `admin`
  เห็นครบทุกแท็บ ใช้ `/financial` ได้ปกติ
- Commit + push แล้ว (ไม่มี upstream commit ใหม่ตอน push รอบนี้ ไม่ต้อง merge)

### บริบทและสถานะปัจจุบัน (Current Context & State)

- นี่คือครั้งเดียวที่ Track 1 ข้ามมาทำงานฝั่ง UI/nav ตาม insturction ตรงจาก
  user (ไม่ใช่การเปลี่ยน policy สองแทร็กถาวร) - งาน UI/UX อื่นๆ ยังเป็นของ
  Track 2 ตามเดิม
- 2D+3D merge (prompt ที่ 2 จาก entry ก่อนหน้า) ยังไม่มีใครเริ่มทำ

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. รอ user ส่ง prompt ที่เหลือ (รวม Irradiance Map + 3D View) ให้ Track 2
2. Next steps ข้ออื่นจาก entry ก่อนหน้า (17:11) ยังค้างเหมือนเดิมทั้งหมด -
   ดูรายการเต็มด้านบน (Railway deploy reminder, กล้อง 3D auto-follow,
   Day-ahead hybrid real+synthetic, Financial module placeholder)

## 2026-07-18 19:39 ICT

**Track 1 - เนื้อหาเชิงวิชาการ (Content/Engineering)**

รอบนี้ user ส่งคลิปวิดีโอ + feedback ยาวมากเรื่องหน้า 3D View (`/3d`) ทั้งหมด
5 ข้อใหญ่ (บางข้อมีข้อย่อย) - สรุปทำเสร็จเกือบทั้งหมดยกเว้นข้อ 5.2 (ฝน) ที่
หยุดถามก่อนเพราะข้อมูลจริงไม่มีอยู่เลย

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

- **(ข้อ 1) อธิบายแถบควบคุมในหน้า 3D View** - ตอบตรงในแชท ไม่ใช่โค้ด: ☀️
  Solar access view / 📊 String view / ▶️⏸ Play-Pause / ↻ Reset camera / 🛰
  สลับพื้น grid-กับ-satellite แถบไล่สีแดง-เขียวมุมขวาบนคือ Solar Access Gauge
  หน้าปัดคือ Compass (azimuth/elevation ดวงอาทิตย์)
- **(ข้อ 2) แก้ดวงอาทิตย์เริ่มต้นไม่ตรงพระอาทิตย์ขึ้นจริง + แก้ animation
  กระตุก**: ค่าเริ่มต้นตอนนี้ดึงจากจุดแรกของ `/sun-path` (ซึ่งกรองเอาเฉพาะ
  ช่วงกลางวันอยู่แล้ว - จุดแรกคือพระอาทิตย์ขึ้นจริงพอดี) แทนเวลาตายตัวเดิม
  - **root cause ของอาการกระตุก**: ของเดิมใช้ `setInterval` ขยับทีละ 15 นาที
    ทุก 400ms แล้วยิง fetch ใหม่ทุกครั้ง ทำให้ดวงอาทิตย์ "กระโดด" ไม่ไหล แก้
    โดยย้าย animation ไปทำงานข้างในของ react-three-fiber's `useFrame` เอง
    (imperative, ไม่มี React re-render ต่อเฟรม ไม่มีการยิง network เพิ่ม)
    แล้ว interpolate ตำแหน่งต่อเนื่องจากจุดข้อมูล sun-path 15 นาทีที่โหลดมา
    ครั้งเดียวทั้งวันอยู่แล้ว - ได้ 60fps จริงๆ ไม่ใช่แค่ลด step ให้ถี่ขึ้น
- **(ข้อ 3) เพิ่มแถบ irradiance ให้เด่นชัด**: การ์ดใหม่โชว์ Clear-sky GHI
  (ค่าเดียวกับหน้า Irradiance Map ที่เวลาเดียวกัน) แยกเด่นจากตัวเลขอื่น
- **(ข้อ 4) เพิ่มเวลากำกับการ simulation + มุมต่างๆ + lat/lon**: บรรทัด
  "กำลังจำลอง (Simulating) 18 กรกฎาคม 2569 - 07:00 น. (ICT)" แบบเดียวกับ
  นาฬิกาหน้า Forecast, เพิ่ม Zenith angle (90-elevation) ข้าง Compass เดิม,
  เพิ่มพิกัด lat/lon จริงของโซนที่เลือกอยู่ (GIS/ISB/Jetty) จาก config จริง
- **(ข้อ 5) บอกขอบเขตวันที่ + ปฏิทิน**: `<input type="date">` เดิมเปิด
  ปฏิทินอยู่แล้ว (เช็คแล้ว ไม่ต้องแก้) - เพิ่ม caption อธิบายแทนการล็อควันที่
  ตายตัว: จำลองตำแหน่งดวงอาทิตย์ได้ทุกวันที่ (คำนวณดาราศาสตร์ ไม่มีข้อจำกัด)
  แต่ Forecast/Actual มีข้อมูลจริงแค่ ~3 วันย้อนหลัง/ล่วงหน้า - มี warning
  โผล่เมื่อวันที่เลือกอยู่นอกช่วงนี้
  - **แถมแก้ bug จริงที่เจอ**: สีแผงตอนนี้ผสม actual+forecast แล้ว (เดิมใช้
    แค่ actual ซึ่งไม่มีค่านอก "วันนี้" ทำให้ทุกแผงโชว์ 0% เสมอเวลาเลื่อนไป
    วันอื่นหรือเวลาในอนาคตของวันนี้ ทั้งที่มีตัวเลข forecast จริงอยู่แล้ว)
- **(ข้อ 5.1) เพิ่ม cloud layer ลอยจริงจากข้อมูลจริง**: สร้าง endpoint ใหม่
  `GET /weather/clouds` ดึงค่าล่าสุดจาก Himawari (`cloud_history` - ตัวเดียว
  กับที่ Sum-k LSTM ใช้อยู่แล้ว) ทั้ง opacity% และ motion vector (ทิศ+ความเร็ว)
  แล้ว render เป็นก้อนเมฆลอยจริงใน 3D scene ลอยตามทิศ/ความเร็วจริง -
  **ข้อจำกัดที่บอกตรงๆ ไม่ปิดบัง**: ระบบเก็บแค่ค่า opacity รวมทั้งโรงงาน
  ไม่ใช่ raster เชิงพื้นที่ (ข้อมูล pixel จริงอยู่ใน MinIO แยกต่างหาก ยังไม่ได้
  ต่อ) เพราะฉะนั้นนี่คือ "มีเมฆ X% ลอยทิศนี้" ตามจริง ไม่ใช่การจำลองเงาบัง
  แผงทีละแผงที่แม่นยำเชิงพื้นที่ - ยังทำแบบนั้นไม่ได้เพราะไม่มีข้อมูลรองรับ
  - **เจอ bug จริงระหว่างสร้าง endpoint นี้**: `cloud_history_df()`/
    `nwp_history_df()` ใน `local_store.py` พังถ้า timestamp ในตารางมีความ
    ละเอียดไม่เท่ากัน (มี/ไม่มี microseconds ปนกัน) - `pd.to_datetime` เดา
    format จากแถวแรกแล้วปฏิเสธแถวอื่นที่ไม่ตรงเป๊ะ เป็น bug จริงที่อาจเกิดใน
    production ได้ ไม่ใช่แค่ปัญหา test - แก้แล้วด้วย `format="ISO8601"`
    พร้อม regression test
- **(ข้อ 5.2 ฝน) หยุดถามก่อน ไม่ทำเอง**: เช็คตรงแล้วว่า **ไม่มีข้อมูลฝน/
  precipitation จริงอยู่ในระบบนี้เลยสักที่** (`ingestion/nwp` ดึงแค่ SSRD กับ
  temp2m จาก GFS ไม่เคยดึง APCP แม้จะอยู่ใน index เดียวกันที่ดึงอยู่แล้วก็ตาม)
  การทำ "ฝนจากข้อมูลจริง" ให้ตรงตามที่ user ขอ ต้องสร้าง ingestion pipeline
  ใหม่ก่อน (ทางที่สมเหตุสมผลที่สุดคือต่อยอด GFS fetch เดิมให้ดึง APCP ด้วย
  ไม่ใช่ต่อ Thai Meteorological Dept แยกใหม่ทั้งหมด) - งานขนาดใหญ่พอสมควร
  เลยหยุดถาม user ก่อนแทนที่จะเดาทำเอง หรือปลอมด้วย heuristic ฤดูกาล (ผิด
  หลักการ "ข้อมูลจริงหรือบอกตรงว่าเป็นค่าประมาณ" ของโปรเจกต์นี้)
- Test ทั้งหมดผ่าน: web 262/262 (`tsc`/`oxlint` clean), `api` 146,
  `forecast` 141 - live-verify ผ่าน Playwright จริงหลายมุม (พระอาทิตย์ขึ้น,
  เที่ยงพร้อมหมุนกล้องเห็นดวงอาทิตย์+เมฆชัดเจน, กด Play แล้วเวลา/ตำแหน่ง
  ขยับจริงไม่ค้าง) ไม่มี console error/warning เลยตลอดการทดสอบ
- Commit + push แล้ว (merge กับงานของ Track 2 ที่ push มาระหว่างทาง
  เรียบร้อย conflict เดียวใน `web/README.md` แก้โดยเก็บ entry ทั้งสอง track)

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ไฟล์หลักที่แก้/เพิ่มรอบนี้: `web/src/pages/Solar3DPage.tsx` (rewrite
  ใหญ่), `web/src/components/Solar3DScene.tsx` (`SunMarker`/`CloudLayer`
  ใหม่), `web/src/lib/solar3d.ts` (`interpolateSunPosition`/`zenithAngleDeg`
  ใหม่), `api/src/nongfab_api/routes_weather.py` (`GET /weather/clouds`
  ใหม่), `forecast/src/nongfab_forecast/local_store.py` (bug fix)
- Pattern ที่ตั้งไว้ให้ session หน้าถ้าจะทำ animation ลื่นๆ ใน 3D scene อีก:
  อย่าใช้ React state + setInterval ขยับทีละก้อนใหญ่ - ให้ทำ animation จริง
  ข้างใน `useFrame` (imperative ref mutation) แล้วค่อย throttle callback
  กลับมาที่ React state แยกต่างหาก (ตัวอย่างเต็มดูที่ `SunMarker`)
- `CloudLayer` เป็น "stylized" ไม่ใช่ physically-accurate - ถ้า user ขอเงา
  บังแผงแบบแม่นยำจริงๆ ในอนาคต ต้องต่อ MinIO raw raster tiles ก่อน (งานใหญ่
  กว่านี้มาก ยังไม่ได้ประเมิน scope)
- ยังไม่ได้ทำ "กล้อง 3D auto-follow ดวงอาทิตย์" (ที่เสนอไว้ใน entry ก่อน
  หน้านี้) - ไม่เกี่ยวกับรอบนี้โดยตรง แต่ยังเป็นคำถามค้างอยู่

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **⚠️ Reminder: รอบนี้แตะ `api/` (routes_weather.py) และ dependency ของมัน
   (`forecast/local_store.py`)** - ต้องกด Deploy เองที่ Railway dashboard
   ถ้าอยากให้ `GET /weather/clouds` กับ bug fix ไปโผล่บน production (auto
   deploy ยังใช้ไม่ได้ตามเดิม)
2. รอ user ตอบคำถามเรื่องฝน (ข้อ 5.2): จะให้สร้าง ingestion pipeline ใหม่
   สำหรับดึง APCP จาก GFS จริงไหม (งานใหญ่ ควรเริ่มเป็น task แยก)
3. รอ user ตอบเรื่องกล้อง 3D auto-follow ดวงอาทิตย์ (ค้างจาก entry ก่อน)
4. รอ user ตอบเรื่อง Day-ahead hybrid real+synthetic (ค้างจาก entry ก่อน)
5. Next steps อื่นจาก entry ก่อนหน้าๆ ยังค้างเหมือนเดิม (Financial module
   placeholder, prompt รวม Irradiance Map+3D View ให้ Track 2)

---

## 2026-07-18 22:12 ICT

**Track 1 - เนื้อหาเชิงวิชาการ (Content/Engineering)**

### สิ่งที่ทำเสร็จแล้ว (Completed Tasks)

User ถามสองเรื่องพร้อมกัน: (1) เช็ค priority list ที่เคยคุยกันไว้ก่อนหน้านี้ว่า
ตอนนี้เป็นยังไงบ้าง โดยประกาศชัดว่า FusionSolar "ทิ้งไปเลยขอไม่ได้เเล้วจริงๆ"
(2) ไฟเขียวให้สร้างฟีเจอร์ฝน (ข้อ 5.2 ที่ค้างไว้จาก entry ก่อนหน้านี้ รอ user
คอนเฟิร์มก่อนเพราะเป็นงาน ingestion pipeline ใหม่)

**A. สรุป priority list + ปิดสถานะ FusionSolar ถาวร**

- Priority list ฉบับเต็มไม่เคย commit ไว้ในไฟล์ไหนเลย (เป็นสิ่งที่ user บอก
  ตรงในแชทช่วง 2026-07-15/16 ก่อนมี `HANDOFF.md` ด้วยซ้ำ) - เจอแค่การอ้างอิง
  อ้อมๆ ใน `forecast/README.md` (บรรทัด 406-408, 464, 524-526 เดิม): ข้อ 3
  คือ "real bias-correction validation", FusionSolar เป็น "top blocker
  สำหรับหลายข้อ" ในลิสต์
- สิ่งที่ทำสำเร็จ/หาทางเลี่ยงได้แล้วโดยไม่ต้องรอ FusionSolar: PVGIS (ทดแทน
  ได้แค่ข้อมูลสภาพอากาศ ไม่ใช่ข้อมูลผลิตไฟจริง - พิจารณา PVOutput/NREL
  PVDAQ/Ausgrid/Kaggle แล้วปฏิเสธหมดเพราะเป็นข้อมูลผลิตไฟจากไซต์อื่น ทดแทน
  ข้อมูลจริงของ Nong Fab เองไม่ได้), Sum-k LSTM (แข่งเป็น candidate ที่ 3
  ได้แล้วโดยไม่ต้องรอ), และการ reframe เป้าหมายโปรเจกต์ทั้งก้อนไปทาง
  Financial module เมื่อ 2026-07-16 (เพราะ forecasting แบบ sub-daily มี
  operational value น้อยที่ไซต์นี้ - ไม่มี battery, ผูกกับ grid เต็มรูปแบบ)
- **ปิดสถานะถาวรตามที่ user สั่งรอบนี้**: แก้ `forecast/README.md` จาก
  "access is pending" เป็น "confirmed permanently unavailable" ทั้ง 2 จุด -
  ข้อ 3 ของ priority list (real bias-correction validation) ปิดถาวร ไม่ใช่
  แค่ค้างรอเหมือนเดิม ระบุชัดในไฟล์ว่า bias-correction cascade ที่ทำไปแล้ว
  จะ validate ได้แค่ทางอ้อม (held-out RMSE กับข้อมูล synthetic/PVGIS) ไป
  ตลอด ไม่ใช่ gap ที่รอปิดในอนาคต

**B. สร้างฟีเจอร์ฝนจริง (ข้อ 5.2) ครบวงจร ตั้งแต่ ingestion ถึง 3D animation**

- **`ingestion/nwp`**: `_build_filter_url` เพิ่ม `var_APCP=on`;
  `_decode_grib_sync` decode field ใหม่ (`precip_mm`, GRIB shortName `tp`)
  แบบ defensive - คืนค่า `None` (ไม่ใช่ `0.0` มั่วๆ) ถ้า subset ไม่มี field
  นี้จริง (verify กับ fixture จริงที่ capture ไว้ก่อนเพิ่ม `var_APCP` แล้ว
  เห็นว่าได้ Dataset เปล่า ไม่ error) `S3GfsBackfillDataSource` ก็ดึง APCP
  เช่นกัน แยก try/except ต่างหากจาก 5 field หลัก (พังแล้วไม่ทำให้ row
  ทั้งแถวพัง) - เจอ quirk จริงของ GFS ระหว่างทำ: f001 มี APCP entry **ซ้ำกัน
  2 บรรทัด** ใน `.idx` จริง (ไม่ใช่ bug parsing) มี test pin ไว้แล้ว
- **`forecast/local_store.py`**: เพิ่ม column `precip_mm` ใน `nwp_history`
  พร้อม migration (`ALTER TABLE` แบบ idempotent เหมือน `candidate_errors`
  เดิม) สำหรับ DB เก่าที่มีอยู่แล้ว
- **`api/routes_weather.py`**: endpoint ใหม่ `GET /weather/precipitation` -
  หาแถวที่ใกล้ "ตอนนี้" ที่สุด (ไม่ใช่แถวสุดท้าย เพราะ `nwp_history` มี
  forecast ล่วงหน้าถึง 72 ชม.) แปลงเป็น intensity band ตามมาตรฐาน WMO
  (light/moderate/heavy) - `available: false` เมื่อไม่มีข้อมูลจริงในช่วงเวลา
  ใกล้พอ ไม่ใช่โกหกว่าฝนไม่ตก
- **Frontend**: `RainLayer` component ใหม่ใน `Solar3DScene.tsx` - ฝนตกจริง
  เป็นเส้น (ไม่ใช่ทรงกลมแบบเมฆ) จำนวนอนุภาคปรับตาม intensity (60/120/200)
  ใช้ `useFrame` แบบเดียวกับ `SunMarker`/`CloudLayer` (animation ใน r3f
  render loop ไม่ใช่ React state) **ไม่ทำหิมะตามที่ user สั่งชัดเจน**
  (`Solar3DPage.tsx` ต่อ hook ใหม่ `usePrecipitationConditions()` เข้ากับ
  scene เหมือน cloud data)
- Test ผ่านหมด: `nwp` 43 passed (5 skip เดิม ไม่เกี่ยวกัน), `forecast` 135
  passed, `api` 155 passed, `web` 264/264 (`tsc`/`oxlint` clean)
- **Live-verify จริง**: boot `uvicorn`+`vite dev`, login ผ่าน `/auth/token`
  จริง, seed ข้อมูลฝนจริง (`precip_mm=6.2`) ผ่าน `RealDataStore` แล้วยิง
  `GET /weather/precipitation` เห็นค่ากลับมาถูกต้อง, เปิด `/3d` ผ่าน browser
  จริง (Playwright) เห็น response เดียวกันไหลถึง frontend และ**เห็นเส้นฝน
  ตกจริงในภาพ 3D** (มี screenshot ยืนยัน) ไม่มี console error/warning เลย
- Commit + push แล้วไปที่ `claude/solar-optimization-forecasting-jryux7`

### บริบทและสถานะปัจจุบัน (Current Context & State)

- ไฟล์หลักที่แก้/เพิ่มรอบนี้: `ingestion/nwp/src/nwp_ingestion/{schemas,
  datasource}.py`, `forecast/src/nongfab_forecast/local_store.py`,
  `api/src/nongfab_api/routes_weather.py`, `web/src/components/
  Solar3DScene.tsx` (`RainLayer` ใหม่), `web/src/pages/Solar3DPage.tsx`,
  `web/src/lib/{types,api,queries}.ts` - README ทั้ง 4 module (`ingestion/
  nwp`, `forecast`, `api`, `web`) มี entry วันที่ 2026-07-18 อธิบายครบ
- **FusionSolar ปิดถาวรแล้ว** - อย่าเสนอ/รอ FusionSolar อีกใน session ถัดไป
  ถ้า user ถามเรื่อง real bias-correction validation อีก ให้บอกตรงว่าปิด
  ถาวรแล้วตามที่ user สั่งเอง ไม่ใช่เรื่องที่ยังเปิดรออยู่
- `precip_mm` เป็นค่า **accumulated ตั้งแต่ init ของ GFS cycle** ไม่ใช่
  mm/hr rate แท้ๆ - endpoint จำกัดแค่ reading ใกล้ "ตอนนี้" เพื่อให้
  approximation นี้สมเหตุสมผล (accumulation window ของ GFS ใกล้ 1 ชม.
  ที่ lead time สั้นๆ) - ถ้าจะทำอะไรที่ต้องใช้ mm/hr แม่นจริง ต้องทำ
  de-accumulation (ลบค่าระหว่าง forecast hour ติดกัน) เพิ่ม ยังไม่ได้ทำ
- **เตือนซ้ำเรื่อง Financial module (จาก CLAUDE.md standing reminder)**:
  `/financial` ยังใช้ placeholder ทั้งหมด (CAPEX ฿30,000/kWp, PEA tariff
  ฿4.0/kWh, WACC 8%, BOI holiday=0) - รอบนี้พูดถึง Financial module อ้อมๆ
  ตอนสรุป priority list (มันคือเป้าหมายที่ reframe ไปแทน forecasting) แต่
  ยังไม่ได้ถามตัวเลขจริงจาก user - ถ้า session หน้าคุยเรื่อง `/financial`
  อีก ให้ถามตัวเลขจริง 4 ตัวนี้จาก user

### เป้าหมายและงานต่อไป (Next Steps for the Next Session)

1. **⚠️ Reminder: รอบนี้แตะ `api/` (routes_weather.py) และ dependency ของมัน
   (`forecast/local_store.py`)** - ต้องกด Deploy เองที่ Railway dashboard
   ถ้าอยากให้ `GET /weather/precipitation` กับ column ใหม่ไปโผล่บน
   production (auto deploy ยังใช้ไม่ได้ตามเดิม)
2. รอ user ตอบเรื่องกล้อง 3D auto-follow ดวงอาทิตย์ (ค้างจาก entry ก่อนหน้า)
3. รอ user ตอบเรื่อง Day-ahead hybrid real+synthetic (ค้างจาก entry ก่อนหน้า)
4. ถ้า user อยากได้ mm/hr rate ที่แม่นกว่านี้สำหรับฝน (ไม่ใช่แค่ accumulated
   ดิบ) ต้องทำ de-accumulation logic เพิ่ม - ยังไม่ได้ประเมิน scope
5. Financial module placeholder (ตัวเลขจริง CAPEX/PEA tariff/WACC/BOI) -
   ยังรอ user เหมือนเดิม
6. Next steps อื่นจาก entry ก่อนหน้าๆ ยังค้างเหมือนเดิม (prompt รวม
   Irradiance Map+3D View ให้ Track 2 - ส่งไปแล้ว รอ Track 2 ทำ)
