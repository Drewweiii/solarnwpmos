# PTTLNG Nong Fab (LMPT2) — Solar Forecasting
## Technical Analysis & Project Knowledge Base

> เอกสารนี้เป็น knowledge base สำหรับโครงการพยากรณ์กำลังผลิต solar ที่ PTTLNG Nong Fab
> (ISB / GIS / จุดที่ 3) อ้างอิงจาก case study `solarforecast2025.pdf` (อ.จิตโกมุท ทรงศิริ, CUEE)
> และ SLD 3 แผ่นของโครงการ PPA25.0008. ใช้เป็น context ให้ Claude Code ตอนสร้าง website.

---

## 1. ข้อมูลระบบ Solar (จาก SLD — PPA25.0008-PTTLNG-EE-001)

| จุด | สถานะ | PV Module | จำนวนแผง | DC (kWp) | Inverter | AC (kW) | DC/AC | Power Optimizer |
|-----|-------|-----------|---------|----------|----------|--------|-------|-----------------|
| **GIS** | ติดตั้งแล้ว มีข้อมูล | Trina TSM-NEG21C.20 (715 Wp) | 84 | 60.06 | 1× Huawei SUN2000-50KTL-M3 | 50 | **1.20** | Huawei MERC-1300W-P × 42 |
| **ISB** | ติดตั้งแล้ว มีข้อมูล | Trina TSM-NEG21C.20 (715 Wp) | 196 | 140.14 | 3× Huawei SUN2000-50KTL-M3 | 150 | **0.93** | Huawei MERC-1300W-P × 98 |
| **จุดที่ 3** | design เสร็จ ยังไม่ติดตั้ง | (ยังไม่ระบุใน SLD ที่ให้มา) | – | – | – | – | – | – |

- **รวม DC = 200.20 kWp** (60.06 + 140.14) — ตรงกับชื่อโครงการ "200.20kW"
- ตรวจสอบ: 84 × 715 = 60,060 W ✓ ; 196 × 715 = 140,140 W ✓
- Monitoring: มี Janitza UMG96RM power meter + Smart Logger + Monitoring Box ทั้งสองจุด
  (แสดงว่ามีข้อมูล **กำลังไฟฟ้า P** แน่นอน; ต้องยืนยันว่ามี **pyranometer วัด I** ในไซต์หรือไม่)
- โครงสร้างไฟฟ้า: SMDB (indoor) → tie-in → เชื่อมเข้า LV switchgear ของ substation
  (GIS: 0300-SG-4-001B/C ; ISB: MDB เดิม)

### 1.1 นัยของ DC/AC ratio ต่อการพยากรณ์ (สำคัญมาก)

**GIS (DC/AC = 1.20) → มี inverter clipping**
- เมื่อ irradiance สูง กำลัง DC เกิน 50 kW → inverter จำกัดที่ 50 kW → **P อิ่มตัว (saturate)**
- ความสัมพันธ์ P = β₁·I + β₀ ที่ PDF สมมติว่า linear **ใช้ไม่ได้ในช่วง clip**
- โมเดล direct-P แบบ linear จะ **over-predict ช่วงกลางวัน** ที่แดดจัด
- แนวทาง: (a) indirect — พยากรณ์ I ก่อน แล้ว convert ด้วย `P = min(β₁·I + β₀, 50)`
  หรือ (b) ใช้ tree/NN ที่เรียนรู้ saturation ได้เอง (clipping เป็น deterministic → เรียนง่าย)

**ISB (DC/AC = 0.93) → ไม่มี clipping**
- DC สูงสุด < AC rating → P เกาะกับ I เชิงเส้นตลอดช่วง
- Direct approach + linear/any model ทำงานสะอาด เป็นไซต์ที่ "ง่าย" กว่าในเชิงโมเดล

**ข้อควรระวัง — Zero export / Curtailment (PDF น.130):**
โรงงาน LNG อาจมีนโยบายห้ามจ่ายไฟย้อนกลับ ทำให้ P ถูกจำกัดต่ำกว่าที่ผลิตได้จริง →
P หลุดความสัมพันธ์กับ I ต้องเช็คข้อมูลจริง ถ้าพบต้องใช้ load จริงประกอบ หรือกรองช่วง curtail ออก

---

## 2. บทวิเคราะห์ Case Study (solarforecast2025.pdf)

### 2.1 กรอบแนวคิดหลัก
- **What to forecast**: irradiance (I) หรือ power (P) — direct vs indirect approach
- **Horizon**: minute-ahead (5–60 นาที, ใช้ cloud), hour-ahead (1–6 ชม., NWP+satellite),
  day-ahead (1–7 วัน, NWP เป็นหลัก)
- **3 framework ตาม data availability** (น.23):
  1. **IPC** — มี irradiance + power + cloud → เทรนเต็มรูปแบบ
  2. **P** — มีแค่ power → ใช้ NWP/clear-sky เป็น input
  3. **No measurement** — รู้แค่ installed capacity → pre-trained model + plant factor
- **PV conversion model**: P = αI หรือ P = α₁I + α₂T_cell + α₃I·T_cell
- **Deterministic vs Probabilistic**: จุดเดียว vs prediction interval (PI) / quantile

### 2.2 สรุปผลลัพธ์เชิงประจักษ์จาก 4 โครงการ (ใช้อ้างอิงการเลือกโมเดล)

| ปี | ไซต์/ขนาด | Horizon | โมเดลที่ทดสอบ | ผลลัพธ์เด่น |
|----|-----------|---------|---------------|-------------|
| 2019 | CUEE 8kW rooftop | hour-ahead | RF, SVR, MARS, ANN | **RF ดีที่สุด** ทั้ง RMSE และ MBE (แยกตาม time-of-day + k-step) |
| 2023 | 56 ไซต์ | 4-h ahead (irradiance) | SVR, LightGBM, ANN, CNN-LSTM + cloud motion | **SVR/ANN > LightGBM** สำหรับ cloud-motion feature; CNN-LSTM ดีช่วงเช้า; block-matching ดี ≤120 นาที, Horn-Schunck ดี horizon สูง |
| 2024 | MEA multi-site | day & hour ahead | NeuralProphet, LSTM, LightGBM, ANN | **NeuralProphet เด่น hour-ahead** โดยรวม; **LSTM ต้องจูนหนัก** มักได้ MAE/MBE สูงถ้าไม่จูนดี |
| 2025 | probabilistic PI | hour-ahead, 15 นาที | Sum-k LSTM (common+distributed) | ให้ PI **แคบกว่า** งานก่อนหน้า ที่ coverage เท่ากัน |

### 2.3 บทเรียนสำคัญ (โยงเข้าโครงการเราได้ตรงๆ)
1. **LSTM ไม่ใช่คำตอบอัตโนมัติ** — ในทุก case study LSTM underperform ถ้าไม่มี data มากพอ + งบจูนสูง
   (2023: CNN-LSTM มี 5.17M params แต่ sample แค่ 271k → overparameterized)
2. **Tree-based (RF/LightGBM) คุ้มค่าที่สุดสำหรับ hour-ahead** — compact, จูนน้อย, robust, แม่นดี
3. **NeuralProphet** ดีเมื่อต้องการ decomposition ที่ตีความได้ (trend/seasonal/AR/exogenous)
4. **รูปแบบ error ตายตัว**: error ต่ำช่วงเช้า/เย็น สูงช่วงเที่ยง (ความแปรปรวนเมฆสูง); error โตตาม horizon
5. **เทียบกับ commercial ยังมีช่องว่าง**: CNN-LSTM NRMSE 25.7%/28.8% (60/120 นาที) vs SolCast 4.3%/6.4%
   → data/sensor คุณภาพดี = ผลพยากรณ์ดี (คุ้มกว่าไปทุ่มกับโมเดลซับซ้อน)

---

## 3. ข้อดี–จุดเด่น–จุดด้อยของ Model / Optimization แต่ละแบบ ตาม Horizon

### 3.1 เปรียบเทียบตัวโมเดล (สำหรับ solar forecasting)

| โมเดล | จุดเด่น | จุดด้อย | เหมาะกับ horizon | หมายเหตุสำหรับ PTTLNG |
|-------|---------|---------|-------------------|------------------------|
| **Linear / PV conversion** | เร็ว, baseline, ตีความได้, ทำ adaptive (RLS/Kalman) ง่าย | จับ nonlinear ไม่ได้; **พังที่ clipping** | PV conversion, day-ahead baseline | ใช้กับ ISB ได้ดี; GIS ต้อง clip-aware |
| **Tree (RF, LightGBM)** | compact, เทรนเร็ว, จูนน้อย, robust, จับ interaction ได้, ไม่กิน data | **extrapolate ไม่ได้** (degradation/capacity โต), ไม่มี memory (ต้อง engineer lag), output เป็นขั้นบันได | **hour-ahead (แนะนำเริ่มที่นี่)** | เรียนรู้ clipping ของ GIS ได้เอง ✓ |
| **SVR** | generalize ดีกับ data น้อย, ε-tube ทน noise, เด่นกับ cloud-motion feature | scalar output (ต้อง H submodel), จูน C/ε/kernel ไว, scale ไม่ดีกับ big data | hour-ahead จุดเดียว | ทางเลือกสำรองของ tree |
| **ANN (feedforward)** | multi-output native, nonlinear, ยืดหยุ่น | จูน + เสี่ยง overfit, bias ตามช่วงเวลา (over-est บ่าย) | multi-step static | ดีเมื่อ feature engineer ครบ |
| **LSTM** | memory ในตัว, จับ sequence ยาว, multi-step | **กิน data มาก, จูนยาก, หนัก, มัก lag** | data เยอะ + งบจูนสูง | เก็บไว้ทีหลัง ไม่ใช่ตัวแรก |
| **NeuralProphet** | decomposition ตีความได้, รับ future regressor ในตัว, เด่น daily cycle | additive → interaction ซับซ้อนจำกัด | **hour & day-ahead** | ดีสำหรับ dashboard ที่ต้องอธิบายผล |
| **CNN / CNN-LSTM** | ใช้ภาพ satellite/cloud ตรงๆ, จับ spatial cloud motion | หนักมาก (param >> sample), data-loss ของภาพย้อนหลัง, ยังสู้ commercial ไม่ได้ | minute–hour ahead (วิจัย) | เกินความจำเป็นเฟสแรก |

### 3.2 เปรียบเทียบ Model Configuration (การจัดโครงสร้างโมเดล)

| รูปแบบ | ข้อดี | ข้อด้อย | ใช้เมื่อ |
|--------|-------|---------|---------|
| **Multi scalar-output** (submodel ต่อ k-step) | เลือก feature ต่อ horizon ได้อิสระ | ต้องดูแลหลายโมเดล | tree/SVR ทำ multi-step |
| **Common + Distributed** (LSTM ร่วม + head เบา) | ประหยัด, ดีกับ probabilistic | ออกแบบซับซ้อนกว่า | 2025 ใช้ทำ PI |
| **Parallel — weather classification** | จับ dynamics ต่อสภาพอากาศ | ต้องมี data พอในแต่ละ regime | data เยอะ, อากาศแปรปรวน |
| **Parallel — time split** (submodel ต่อชั่วโมง) | ตรงกับ error ที่ต่างตามเวลา | โมเดลเยอะ | ตรงกับรูปแบบ solar |
| **Adaptive (RLS/Kalman/online)** | ตาม degradation/seasonal drift อัตโนมัติ | เสี่ยง drift ถ้า data เพี้ยน | **operation ระยะยาว (เหมาะ PTTLNG)** |
| **Cascade / Bias-correction** | โมเดล 2 แก้ residual/แก้ bias NWP | pipeline ยาว | day-ahead + NWP |

### 3.3 เปรียบเทียบ Hyperparameter Optimization

| วิธี | ข้อดี | ข้อด้อย | ใช้กับ |
|------|-------|---------|--------|
| **Grid search** | ครบทุก combination, reproducible | แพงมากเมื่อ param เยอะ | tree grid เล็กๆ |
| **Random search** | efficient กว่า grid, ตั้งงบได้ | ไม่ครบทุกจุด | default ที่ดี |
| **Bayesian optimization** | sample-efficient, ใช้ผลก่อนหน้าเลือกจุดต่อไป | setup ซับซ้อนกว่า | เมื่อ 1 การเทรนแพง (LSTM/NN/CNN) |

**คำแนะนำ mapping optimization → horizon:**
- **minute-ahead**: cloud motion + tree/SVR; optimization = random search (ต้องเร็ว รอบ retrain ถี่)
- **hour-ahead**: LightGBM/RF หรือ NeuralProphet; random → Bayesian ถ้ามีงบ
- **day-ahead**: NeuralProphet / bias-corrected NWP; Bayesian (เทรนไม่บ่อย จูนละเอียดได้)

### 3.4 หลักการประเมินผล (จาก PDF — ต้องทำใน dashboard)
- ใช้ **daytime เท่านั้น** (zenith 0–85°) มิฉะนั้น MAE/RMSE จะดูดีเกินจริง (~×0.5, ×0.71)
- **normalization factor**: อย่าใช้ installed capacity ถ้าแผงเสื่อม (จะดูดีเกินจริง) →
  ใช้ช่วง **p5–p95** ของ y จะสมเหตุสมผลกว่า
- error e = ŷ − y : e>0 = over-estimate, e<0 = under-estimate
- รายงาน **per-hour** และ **per-lead-time (k-step)** เสมอ
- Probabilistic: **PICP** (coverage, สูงดี) + **PINAW** (width, ต่ำดี) + **Winkler score**

---

## 4. แผนการนำไปใช้กับ PTTLNG (แนะนำ)

### 4.1 กลยุทธ์ต่อจุด
- **ISB (ไม่ clip)** — direct approach; เริ่มด้วย LightGBM/RF hour-ahead + NeuralProphet เทียบ; linear baseline
- **GIS (clip 1.20)** — indirect (forecast I → convert clip-aware) **หรือ** tree ที่เรียน saturation;
  แยกโมเดลจาก ISB เพราะพฤติกรรมต่างกัน
- **จุดที่ 3 (ยังไม่ติดตั้ง)** — framework "No measurement": transfer โมเดลจาก ISB/GIS
  แล้ว scale ด้วย plant factor (อัตราส่วน installed capacity + orientation/tilt จาก design)
  → นี่คือหัวใจของโหมด **simulation** บนเว็บ

### 4.2 Feature ที่ควรมี (ตาม PDF น.38)
- measurement: I(t), P(t), T, RH, WS, cloud index (ถ้ามี)
- future regressor: clear-sky irradiance I_clr(t+k), NWP (I, T, RH), solar zenith cos θ(t+k)
- synthesized: EMA ของ I, clear-sky index k(t) = I/I_clr

### 4.3 ลำดับความสำคัญของ error ที่ต้องเฝ้า
1. ช่วงเที่ยงที่เมฆแปรปรวน (error สูงสุด)
2. GIS ช่วง clip (bias เชิงบวกถ้าใช้ linear)
3. ช่วง curtailment (ถ้ามี)

---

## 5. คำถามที่ต้องยืนยันกับข้อมูลจริงก่อนสร้างโมเดล/เว็บ
1. ข้อมูล ISB/GIS: granularity (1 นาที? 15 นาที?), ช่วงเวลา (กี่เดือน/ปี), format (CSV/DB/API)?
2. มี pyranometer วัด irradiance ในไซต์ไหม? (ตัดสิน IPC vs P framework)
3. มี zero-export/curtailment จริงไหม? มี log ของ setpoint ไหม?
4. จุดที่ 3: มี design spec (จำนวนแผง, tilt, azimuth, inverter) ให้ scale plant factor ไหม?
5. Horizon เป้าหมายหลัก: hour-ahead อย่างเดียว หรือ day-ahead ด้วย?
