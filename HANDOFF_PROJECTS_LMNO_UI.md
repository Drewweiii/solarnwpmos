# งาน L / M / N / O — นวัตกรรมด้าน Interface

> เขียน 2026-07-26 โดย **Track 1 (เนื้อหาเชิงวิชาการ)** ส่งต่อให้ **Track 2 (หน้าตา/Interface)**
>
> user ถามว่า *"มีนวัตกรรมล้ำๆ เกี่ยวๆกับ interface web ไหม แบบทึ่งๆว้าวๆ"* แล้วเลือกครบทั้ง 4 ข้อ
> และสั่งว่า **"เขียนสเปกไว้ให้เพื่อทำ"** → นี่คือสเปกนั้น
>
> Track 1 สำรวจ codebase ให้จบก่อนเขียนแล้ว **ตัวเลขและข้อจำกัดทุกข้อในไฟล์นี้เปิดไฟล์จริงมาแล้ว**
> โดยเฉพาะข้อ L ที่ผลสำรวจ **เปลี่ยนสเปกไปจากที่ user จินตนาการไว้** — อ่านหัวข้อนั้นก่อนเริ่มเขียนโค้ด

---

## ของที่มีอยู่แล้ว — อย่าเสนอ/สร้างซ้ำ

สำรวจ `web/src/` เมื่อ 2026-07-26:

| มีแล้ว | ที่ไหน |
|---|---|
| ฉาก 3D เต็มรูปแบบ (react-three-fiber) | `components/Solar3DScene.tsx` (~1,800 บรรทัด) |
| ดวงอาทิตย์เคลื่อนตามเส้นทางจริง + ดวงจันทร์ **ข้างขึ้นข้างแรมถูกต้อง** | `SunMarker` / `MoonMarker` |
| เมฆลอย + ฝนตก (ขับด้วยข้อมูลจริง) | `CloudLayer` / `RainLayer` |
| ภาพถ่ายดาวเทียมปูพื้น | `SatelliteTilePlane` / `SatelliteGroundPlane` |
| overlay ความเข้มแสงทั้งไซต์ | `showIrradianceOverlay` |
| แผงเปลี่ยนสีตามกำลังผลิตจริง+พยากรณ์ | `PanelMesh` |
| **ควบคุมฉากด้วยมือผ่านกล้อง** (MediaPipe) | `useHandTracking.ts` · `handControl.ts` · `HandPreview.tsx` |
| ผู้ช่วย AI + ระบบจับ intent | `AIAssistant.tsx` · `lib/assistant.ts` (`ASSISTANT_INTENTS`) |
| **อ่านออกเสียง (TTS)** | `lib/tts.ts` — ใช้ `speechSynthesis` ของเบราว์เซอร์ ไม่มี API key |
| แชทผู้ชม + presence + สติกเกอร์ | `VisitorNetwork.tsx` · `ws_chat` · `stickers.ts` |

**ช่องว่างที่ยังไม่มีเลย** (ยืนยันด้วย grep): ไม่มี WebXR · ไม่มี `SpeechRecognition` (มีแต่พูดออก ไม่มีฟังเข้า) ·
`castShadow` มีแค่บน**ตัวมาสคอต** (บรรทัด 1255, 1260) ไม่มีบนแผงเลย

**dependency ปัจจุบัน** (7 ตัว): `@mediapipe/tasks-vision`, `@react-three/drei`, `@react-three/fiber`,
`@tanstack/react-query`, `react`, `react-dom`, `react-router-dom`, `recharts`, `three`

---

# ⚠️ L. เงาจริงบนแผง — **สเปกเปลี่ยนจากที่คุยไว้ อ่านให้จบก่อน**

## สิ่งที่ user จินตนาการ vs สิ่งที่ข้อมูลรองรับ

user อยากได้ "เงาเมฆจริงเคลื่อนผ่านแผง" **ข้อนี้ทำแบบซื่อสัตย์ไม่ได้** และ codebase เขียนบอกไว้เองแล้ว
**สองที่อิสระจากกัน**:

`Solar3DScene.tsx` → `CloudLayer` docstring:
> *"the lightweight cloud_history table only ever stores one site-wide **opacity scalar + a motion
> vector, not a spatial raster** (the raw per-pixel tile arrays live in MinIO, a separate, heavier
> fetch not wired up here) — so this is a stylized ... **not a per-panel shadow simulation**.
> It does not claim to show exactly which panel is shaded at this instant, **since no data source
> in this app currently supports that claim.**"*

`routes_irradiance_map.py` docstring:
> *"why the **sub-2km spatial variation is still interpolated texture** (no per-point raster store
> exists on Railway)"*

แปลว่า: ทั้งเว็บมี "เมฆ" เป็น **ตัวเลขเดียวทั้งไซต์** (% ความทึบ + ทิศ/ความเร็วลม) ไม่มีรูปร่างเมฆเชิงพื้นที่
การวาดขอบเงาเมฆพาดผ่านแถวแผง = **การปั้นรายละเอียดที่ข้อมูลไม่มี** ซึ่งผิดกฎข้อ 1 ของ repo นี้
(เป็นสถานการณ์เดียวกับงาน C ที่ติดเรื่องพิกัดถัง LNG — ต่างกันแค่ติดที่ "ข้อมูลเชิงพื้นที่" แทน "เรขาคณิต")

## ✅ แต่มีของที่ทำได้จริงและว้าวไม่แพ้กัน — และยังไม่มีใครทำ

**เงาจากดวงอาทิตย์เป็นของจริง 100% และตอนนี้ไม่ได้ใช้เลย**

ระบบมีครบแล้ว: ตำแหน่งดวงอาทิตย์จริงรายชั่วโมง (pvlib ผ่าน `/sun-path/{zone}`) · พิกัดมุมแผงทั้ง 4
ที่รังวัดจริง · ระยะแถว · มุมเอียง — แต่ฉาก 3D **ไม่เปิด shadow map เลย** แผงจึงลอยอยู่โดยไม่ทอดเงา

### สิ่งที่ทำ

1. **เปิด shadow map จริงในฉาก** — `<Canvas shadows>` + `DirectionalLight` ที่วาง**ตามเวกเตอร์
   ดวงอาทิตย์จริง** (มีอยู่แล้วใน `SunMarker`, ดึงค่าเดียวกันมาใช้) + `castShadow`/`receiveShadow`
   บน `PanelMesh` และ `BuildingMass`
2. **เงาแถวบังแถว (inter-row shading) จะโผล่มาเองและมันถูกต้องทางฟิสิกส์** — ตอนเช้า/เย็นที่ดวงอาทิตย์ต่ำ
   แถวหน้าจะทอดเงาลงแถวหลังจริงๆ ซึ่ง**ตรงกับที่ `annual_shading_loss_pct` คำนวณเป็นตัวเลขอยู่แล้ว**
   → ครั้งแรกที่ตัวเลข loss กับภาพ 3D พูดเรื่องเดียวกัน นี่คือ digital twin ของจริง
3. **เมฆ = หรี่แสงทั้งไซต์** ไม่ใช่เงาเป็นรูปร่าง — ลด `intensity` ของ DirectionalLight และเพิ่ม ambient
   ตาม % ความทึบจริง พร้อมเขียนกำกับบนหน้าจอว่า "เมฆหรี่แสงทั้งไซต์ ไม่ใช่เงาเฉพาะจุด เพราะข้อมูลเป็นค่าเดียวทั้งไซต์"
4. **เตรียมทางไว้ให้ถังน้ำมัน** — พอ user ส่งพิกัด+ความสูงถัง LNG มา (งาน C) เงาถังจะโผล่ในฉากทันที
   โดยไม่ต้องเขียนอะไรเพิ่ม เพราะ shadow map ทำงานกับ mesh ทุกตัว

### ⚠️ gotcha
- three.js shadow map กับ **วัตถุโปร่งใส (เมฆ) ทอดเงาไม่ได้ตามปกติ** — อย่าพยายามให้ `CloudLayer` cast
  เพราะจะได้เงาทึบเป็นก้อนกลมๆ ซึ่งผิดทั้งฟิสิกส์และผิดทั้งข้อมูล
- shadow map กินเฟรมเรต ต้องตั้ง `shadow-mapSize` พอดี และจำกัด `shadow-camera` ให้ครอบแค่โซนที่ดูอยู่
- ฉากนี้ **สเกลเป็นเชิงสัญลักษณ์** (`BUILDING_HEIGHT_M = 10` เขียนกำกับตัวเองว่า *"Not a measured
  value"*) เงาอาคารจึงยาวตามความสูงที่เดาไว้ ต้องเขียนกำกับ ส่วน**เงาแผงบังแผงใช้เรขาคณิตจริง** จึงเชื่อได้
- **ถ้าจะโฆษณาว่า "เงาจริง" ต้องแยกให้ชัดบนหน้าจอ**ว่าอันไหนมาจากเรขาคณิตที่รังวัดจริง (แผง) อันไหนมาจากค่าสมมติ (อาคาร)

**ถ้า user อยากได้เงาเมฆเป็นรูปร่างจริงๆ** ต้องต่อ MinIO เข้ากับ Railway เพื่อดึง raster ราย pixel
ซึ่งเป็นงาน infra ไม่ใช่งาน UI — **ให้ถาม user ก่อน อย่าเริ่มเอง**

---

# M. AR/VR ดูโรงไฟผ่านมือถือ (WebXR)

## ทำได้เลย ฉากพร้อมอยู่แล้ว

`Solar3DPage` ใช้ react-three-fiber อยู่แล้ว การเติม WebXR คือห่อ `<Canvas>` ด้วย XR store —
ไม่ต้องเขียนฉากใหม่

```
npm i @react-three/xr        # ตัวเดียว ต้อง match major version ของ @react-three/fiber ที่ใช้อยู่
```

- โหมด **AR**: ส่องกล้องที่โต๊ะ → โรงไฟ Nong Fab ทั้งไซต์โผล่ขึ้นมาเป็นโมเดลตั้งโต๊ะ หมุนดูรอบได้
- โหมด **VR**: ใส่ headset แล้วยืนอยู่กลางลานแผง
- ปุ่มเข้าโหมดควรซ่อนอัตโนมัติเมื่ออุปกรณ์ไม่รองรับ (`navigator.xr.isSessionSupported`)
  **อย่าโชว์ปุ่มที่กดแล้วไม่เกิดอะไร**

## ⚠️ ข้อจำกัดที่ต้องบอก user ตรงๆ ก่อนเริ่ม

- **iPhone/iPad Safari ไม่รองรับ WebXR AR** — ใช้ได้เต็มที่บน **Android + Chrome** และ headset
  (Quest/Vision Pro browser) เท่านั้น · ถ้า user จะเอาไปเดโมด้วย iPhone จะพัง **ต้องถามก่อนว่าจะเดโมด้วยอะไร**
- ต้องเป็น **HTTPS** (Cloudflare มีอยู่แล้ว ผ่าน)
- **สเกลฉาก**: ฉากปัจจุบันเป็นหน่วยเชิงสัญลักษณ์ ต้องมี scale factor สำหรับ AR ตั้งโต๊ะ
  (ทั้งไซต์กว้างหลายร้อยเมตร ต้องย่อลงเหลือขนาดโต๊ะ) และ **ต้องมีสเกลบาร์บอกขนาดจริง**
  ไม่งั้นผู้ชมจะอ่านขนาดผิด
- AR กินแบตและ CPU หนัก ควรลดจำนวน mesh/ปิด shadow ในโหมด XR

---

# N. คุยกับน้อง Solar ด้วยเสียง (Web Speech API)

## ทำได้เลย ไม่ต้องเพิ่ม dependency และครึ่งหนึ่งมีอยู่แล้ว

ระบบมี **สองในสามชิ้น**พร้อมแล้ว:

1. ✅ **พูดออก** — `lib/tts.ts` ใช้ `speechSynthesis` (ไม่มี API key ตามกฎ zero-cost ของโปรเจกต์)
   และผ่านการปรับความชัดมาแล้วรอบหนึ่ง (2026-07-18 user บอก *"อยากให้ชัดเจนมากขึ้นอีกเยอะๆ"*)
2. ✅ **เข้าใจคำถาม** — `lib/assistant.ts` มี `ASSISTANT_INTENTS` + `ASSISTANT_FALLBACK_MESSAGE`
   เป็นเครื่องจับ intent ที่ใช้งานอยู่แล้วในช่องแชทของผู้ช่วย
3. ❌ **ฟังเข้า** — ยังไม่มี

จึงเหลือแค่ต่อชิ้นที่ 3: `SpeechRecognition` → ป้อนข้อความเข้า `ASSISTANT_INTENTS` ตัวเดิม → คำตอบวิ่งเข้า
`tts.ts` ตัวเดิม **วงจรปิดครบโดยไม่ต้องสร้างสมองใหม่**

### ต่อยอดที่ทำให้ "ว้าว" ขึ้นอีก
เพิ่ม intent ที่**สั่งให้เว็บทำอะไร** ไม่ใช่แค่ตอบ เช่น "ขอดูพยากรณ์พรุ่งนี้ของ Jetty" → เปลี่ยนโซน +
กดแท็บ Day-ahead + เลื่อนหน้าไปที่กราฟให้เอง (ใช้ `react-router` + state ที่มีอยู่)
รวมกับ **hand tracking ที่มีอยู่แล้ว** จะได้เว็บที่คุมได้ทั้งด้วยมือและเสียง ซึ่งเดโมแล้วน่าจดจำมาก

### ⚠️ gotcha
- `SpeechRecognition` **Chrome/Edge รองรับ · Firefox ไม่รองรับ · Safari รองรับบางส่วน**
  ต้อง feature-detect แล้วซ่อนปุ่มไมค์ถ้าไม่มี (หลักเดียวกับ `tts.ts` ที่ no-op เมื่อไม่รองรับ)
- ตั้ง `lang = 'th-TH'` แต่คำศัพท์เทคนิคเป็นอังกฤษปนไทย ("kWp", "Day-ahead") การรู้จำจะเพี้ยน —
  ควรทำ normalization ก่อนส่งเข้า intent matcher (เช่น "เคดับเบิลยูพี" → "kWp")
- **ต้องขอ permission ไมค์** ควรอธิบายก่อนขอ อย่าเด้ง prompt ทันทีที่โหลดหน้า
- อย่าเปิดไมค์ค้าง ให้กดพูดเป็นครั้งๆ (push-to-talk) — ทั้งเรื่องความเป็นส่วนตัวและแบต

---

# O. คลิกตัวเลขไหนก็ได้ → สืบที่มาของมัน (Provenance Inspector)

## ทำไมข้อนี้คือของที่ "ตรงกับจุดขายของโปรเจกต์นี้ที่สุด"

ไม่หวือหวาเท่า AR แต่เป็นสิ่งที่ **ไม่มี solar dashboard เจ้าไหนทำ** และมันคือการเอาสิ่งที่โปรเจกต์นี้
หมกมุ่นมาตลอด (ความซื่อสัตย์ของข้อมูล) มาทำให้**จับต้องได้**

ไอเดีย: กดเลขใดก็ได้บนเว็บ → ป็อปอัปไล่สายกลับให้ดูว่า
**เลขนี้มาจากไหน → ผ่านโมเดลไหน → ใช้ setting ตัวไหน → setting นั้น origin เป็นอะไร**

### วัตถุดิบมีครบแล้ว แต่**กระจัดกระจาย** — งานหลักคือรวบมันเข้าด้วยกัน

| ชิ้นส่วน | อยู่ที่ไหน |
|---|---|
| `origin` ของทุกค่าที่ปรับได้ (`confirmed`/`as-built`/`literature`/`placeholder`/`tuning`/`derived`) | `settings_registry.py` — **92 ค่า / 10 กลุ่ม** ทุกตัวมี origin + note ภาษาไทย |
| ทะเบียนแหล่งข้อมูลราชการ + ตรวจว่าเอกสารเก่าไปหรือยัง | `official_sources.py` + `GET /sources` |
| ที่มาของค่า soiling (literature vs measured) | `loss_model.py` → `soiling_source` |
| ที่มาของเรขาคณิตแผง (รังวัดเมื่อไร ด้วยอะไร) | `config/assets.yaml` คอมเมนต์ |
| ที่มาของสัดส่วนเชื้อเพลิง | `grid_carbon.py` → `MIX_ORIGIN_ANNUAL` / `MIX_ORIGIN_PUBLISHED` |
| ที่มาของแถบความเชื่อมั่น / ค่าจริงที่ใช้เทียบ | `routes_verification.py` → `reference_note`, `interval_note` |

### วิธีที่ถูก vs วิธีที่จะพัง
❌ **อย่าเขียน tooltip ด้วยมือทีละจุด** — พอค่าเปลี่ยน tooltip จะโกหกทันที และไม่มีเทสจับได้
✅ **ทำ provenance map ที่เครื่องอ่านได้**: เพิ่ม endpoint `GET /provenance/{key}` ที่คืนสายที่มาเป็นโครงสร้าง
แล้ว frontend ทำ component เดียว `<Provenanced valueKey="...">` ห่อตัวเลข — เพิ่มจุดใหม่ = เพิ่ม 1 entry
(หลักเดียวกับที่ `settings_registry.py` ทำสำเร็จมาแล้ว: ประกาศเป็น data → API อธิบายตัวเอง → ฟอร์มเดียวเรนเดอร์ทั้งหมด)

### ⚠️ นี่เป็นงานที่ก้ำกึ่งสองแทร็ก
โครงสร้าง provenance ฝั่ง backend เป็นเนื้อหาเชิงวิชาการ (Track 1) ส่วนตัว UI popup เป็น Track 2
**ควรคุยกับ user ว่าจะแบ่งยังไง** หรือให้บัญชีเดียวทำทั้งเส้นก็ได้ถ้าจะให้จบเร็ว

---

## ลำดับที่แนะนำ

1. **N (เสียง)** — คุ้มที่สุดต่อแรง: ไม่ต้องเพิ่ม dependency, สมอง+เสียงพูดมีแล้ว, เดโมแล้วว้าวทันที
2. **L (เงาดวงอาทิตย์จริง)** — ไม่ต้องเพิ่ม dependency, ทำให้ตัวเลข shading loss กับภาพ 3D ตรงกันครั้งแรก
3. **M (WebXR)** — ว้าวที่สุด แต่ต้องถาม user ก่อนเรื่องอุปกรณ์เดโม (iPhone ใช้ไม่ได้)
4. **O (provenance)** — ใหญ่สุดและก้ำกึ่งสองแทร็ก ควรคุยขอบเขตก่อน

---

## ⛔ ห้ามแตะ (Track 1 ถือครอง / เพิ่งแก้)

ไฟล์จากกะ 2026-07-25/26 ที่ยังไม่ได้ verify บนเบราว์เซอร์จริง:

```
features/poa.py · features/bifacial.py
simulation/{tilt_optimizer,dc_ac_ratio,tou,pipeline}.py
forecast/{sky_condition,ramp,evolution,verification,local_store}.py
api/{grid_carbon,routes_grid_carbon,routes_orientation,routes_dc_ac,routes_bifacial,
     routes_tou,routes_verification,routes_ramp,routes_evolution}.py
web/components/{GridCarbon,Orientation,DcAc,Bifacial,Tou,Ramp,ForecastEvolution,ForecastKpi}*.tsx
web/lib/forecastKpi.ts
```

**งาน I/J/K** (demand charge · PV recycling · power flow) ยังเป็นของคุณเช่นกัน ยังไม่มีใครเริ่ม —
ดู `HANDOFF_PROJECTS_IJK.md`

---

## กติกาที่พลาดแล้วเจ็บ (จดจากที่พลาดมาแล้วจริงๆ)

- **ด่านฝั่ง web มี 3 ตัว ไม่มีตัวไหนครอบตัวอื่น** ต้องรันครบก่อน push:
  `npm run lint` (oxlint) → `npx vitest run` → **`npm run build`** (`tsc -b && vite build`)
  `tsc -b` ตรวจไฟล์เทสด้วย ส่วน `npx tsc --noEmit` ไม่ตรวจ · รอบล่าสุด `tsc -b` จับ unused import
  ที่อีกสองด่านปล่อยผ่าน
- **ฟิลด์ใหม่ใน response type ใส่ `?` เสมอ** ไม่งั้น fixture เก่าทุกตัวพัง (CI #172/#173)
- **ห้ามใส่ type ให้พารามิเตอร์ของ recharts formatter** — narrow ด้วย `typeof` ในบอดี้แทน (พลาดมาแล้ว 3 ครั้ง)
- **`ruff check` ต้องใส่โฟลเดอร์ `tests` ด้วย** → `ruff check <pkg>/src <pkg>/tests`
  CI #185/#186 แดงเพราะรันแค่ `src` และเพราะ ruff รัน**ก่อน** pytest เทสจึงถูก skip ทั้ง job
- **route ใหม่ใต้ `/forecast/{zone}/...` ต้อง register ก่อน `routes_forecast`** ไม่งั้น `{horizon}` กินหมด
- **ห้ามเขียน markdown ในสตริงที่ frontend เรนเดอร์ตรงๆ** — `**ตัวหนา**` จะโผล่เป็นดอกจันบนหน้าจอ
  (เจอจริงใน `routes_bifacial.py` เทสทั้งสองฝั่งปล่อยผ่าน จับได้ตอนเปิดดูหน้าเว็บ)
- ค่าคงที่ใหม่ใส่ `settings_registry.py` ได้ช่องกรอกในหน้า Settings ฟรี (ตอนนี้ **92 ค่า / 10 กลุ่ม**)

## กฎเหล็กเรื่องความซื่อสัตย์ของข้อมูล

ห้ามนำเสนอค่าที่แต่งขึ้นว่าเป็นของจริง ทุกค่าต้องมี `origin` · ถ้าไม่มีข้อมูลให้แสดง "ยังไม่มีข้อมูล" ตรงๆ
**และข้อนี้ใช้กับกราฟฟิกด้วย** — ภาพที่วาดรายละเอียดเกินกว่าที่ข้อมูลรองรับ (เช่นเงาเมฆเป็นรูปร่าง
จากข้อมูลที่เป็นตัวเลขเดียวทั้งไซต์) คือการปั้นข้อมูลเหมือนกัน แค่ปั้นด้วยพิกเซลแทนตัวเลข

**ถามก่อนตัดสินใจเสมอ** และถ้าประเมินว่างานยาวจนเครดิตอาจหมดกลางทาง ให้เตือน user **ก่อน** เริ่ม

จบงานแล้วเขียน Handoff Report ภาษาไทย 3 หัวข้อ + แท็ก Track แล้ว **append** ลง `HANDOFF.md`
