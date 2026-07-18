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
