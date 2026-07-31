# ย้าย API จาก Railway ไป Hugging Face Spaces (2026-07-26)

เขียนตอนเครดิตฟรีของ Railway หมดและเว็บล่ม เอกสารนี้คือขั้นตอนกู้ให้กลับมารัน
โดยไม่เสียเงิน

## ทำไมเลือก Hugging Face Spaces

ตัวตัดสินคือ **แรม** `api/src/nongfab_api/config.py` บันทึกไว้เองว่าคอนเทนเนอร์นี้
กิน **~665 MB ตอน idle** จากการ import mlflow / neuralprophet / neuralforecast /
lightgbm / torch — เป็นค่า import ล้วนๆ ไม่ใช่ค่าทำงาน

| แพลตฟอร์ม | RAM ฟรี | ผลกับแอปนี้ |
|---|---|---|
| **Hugging Face Spaces** | **16 GB** | รันได้ทันที ไม่ต้องแก้โค้ดก่อน |
| Render (free) | 512 MB | **OOM ตั้งแต่บูต** |
| Koyeb (free) | 512 MB | **OOM ตั้งแต่บูต** |
| Fly.io | ไม่มี free tier แล้ว | ต้องจ่าย |
| Google Cloud Run | ตามใช้จริง | ได้ แต่ **ต้องผูกบัตร** + cold start 20–40 วิ |

Hugging Face จึงเป็นตัวเดียวที่ทั้งฟรีจริง ไม่ต้องใช้บัตร และแรมพอโดยไม่ต้อง
แก้โค้ดก่อน ซึ่งสำคัญมากตอนเว็บล่มอยู่

## ข้อจำกัดที่ต้องรู้ก่อน ไม่ใช่รู้ทีหลัง

1. **หลับหลังไม่มีทราฟฟิก 48 ชม.** ตื่นเองเมื่อมีคนเข้า แต่ครั้งแรกช้าเพราะ
   image หนัก — **ก่อนเดโมให้เปิดเว็บทิ้งไว้ล่วงหน้าสัก 5 นาที**
2. **ดิสก์เป็น ephemeral** ทุกอย่างที่เขียนลงไฟล์จะหายเมื่อ Space restart หรือ
   rebuild ได้แก่ ผู้ใช้/รหัสผ่าน, settings ที่ publish, ประวัติแชท, และโมเดลที่
   เทรนไว้ (`mlruns/`) — ดูหัวข้อ "ทำให้ข้อมูลไม่หาย" ข้างล่าง
3. **repo เป็น public** อยู่แล้ว และ Space ฟรีก็ public — **ห้ามใส่ความลับใน
   โค้ด** ทุกอย่างต้องผ่าน Secrets ของ Space

## ขั้นตอน

### 1. สร้าง Space

1. ไป https://huggingface.co/new-space
2. **Owner** = บัญชีคุณ · **Space name** เช่น `nongfab-solar-api`
3. **License** ตามสะดวก
4. **Space SDK** เลือก **Docker** → **Blank**
5. **Hardware** = `CPU basic · 2 vCPU · 16 GB` (ฟรี)
6. **Visibility** = Public (Space ฟรีต้อง public)
7. กด **Create Space**

### 2. ดันโค้ดขึ้น Space

Space คือ git repo ของ Hugging Face เอง และ **build context คือรากของ Space**
โฟลเดอร์ `nongfab-ems/` จึงต้องกลายเป็นรากนั้น — ที่รากนี้มี `Dockerfile` กับ
YAML frontmatter ใน `README.md` เตรียมไว้ให้แล้ว

```bash
# ในเครื่องคุณ ที่รากของ repo GitHub
git remote add hf https://huggingface.co/spaces/<USER>/nongfab-solar-api
git subtree push --prefix=nongfab-ems hf main
```

ครั้งต่อไปที่จะอัปเดต ใช้คำสั่งบรรทัดล่างซ้ำได้เลย

> ถ้า `git subtree push` ถูกปฏิเสธเพราะประวัติไม่ตรงกัน ให้บังคับครั้งแรกครั้งเดียว:
> `git push hf $(git subtree split --prefix=nongfab-ems main):refs/heads/main --force`

Hugging Face จะเริ่ม build เอง ดู log ได้ที่แท็บ **Logs → Build** ของ Space
รอบแรกนานหน่อย (~10–20 นาที) เพราะต้องติดตั้ง torch/mlflow ทั้งกอง

### 3. ตั้งค่า Secrets ของ Space

ที่ Space → **Settings** → **Variables and secrets** ใส่:

| ชื่อ | ประเภท | ค่า |
|---|---|---|
| `API_JWT_SECRET_KEY` | Secret | สุ่มยาวๆ (เช่น `openssl rand -hex 32`) |
| `API_CORS_ORIGINS` | Variable | โดเมนหน้าเว็บบน Cloudflare Pages |
| `API_ENABLE_BACKGROUND_INGESTION` | Variable | `true` |
| `API_ENABLE_BACKGROUND_RETRAINING` | Variable | `false` |
| `API_TIMESCALE_DSN` | Secret | ดูหัวข้อถัดไป |

> `API_CORS_ORIGINS` ต้องเป็นโดเมนหน้าเว็บจริง ไม่ใช่โดเมนของ Space —
> ถ้าใส่ผิดเบราว์เซอร์จะบล็อกทุก request และหน้าเว็บจะว่างเปล่าโดยไม่มี error
> ที่มองเห็น

### 4. ชี้หน้าเว็บมาที่ Space

URL ของ Space คือ
`https://<USER>-nongfab-solar-api.hf.space`

ที่ Cloudflare Pages → Settings → Environment variables ตั้ง
`VITE_API_URL` เป็น URL นั้น แล้ว redeploy หน้าเว็บ

### 5. ตรวจว่ากลับมาแล้วจริง

```bash
curl -s https://<USER>-nongfab-solar-api.hf.space/healthz
curl -s https://<USER>-nongfab-solar-api.hf.space/version
```

## ทำให้ข้อมูลไม่หาย (ทำต่อได้ทีหลัง ไม่ต้องทำตอนกู้)

ดิสก์ของ Space ฟรีเป็น ephemeral ดังนั้น SQLite ที่เก็บ user/settings/chat จะ
รีเซ็ตทุกครั้งที่ restart วิธีแก้ที่ยังฟรี: ใช้ Postgres ฟรีจากภายนอก

1. สมัคร https://neon.tech (free tier ถาวร ไม่ต้องใช้บัตร)
2. สร้าง project → คัดลอก connection string
3. แปลงเป็นรูปแบบ asyncpg แล้วใส่เป็น Secret `API_TIMESCALE_DSN`:
   `postgresql+asyncpg://<user>:<pass>@<host>/<db>`

ส่วน `mlruns/` (โมเดลที่เทรนแล้ว) ยังหายอยู่ ซึ่งรับได้เพราะ
`enable_background_retraining=false` อยู่แล้ว และระบบ backfill ตอน startup
อยู่แล้ว — แต่แปลว่าหลัง restart แต่ละครั้งจะยังไม่มีโมเดลจนกว่าจะเทรนรอบแรก

## ถ้าอยากประหยัดกว่านี้อีก (ไม่จำเป็นตอนนี้)

สามอย่างที่ลดภาระได้จริง เรียงตามผลต่อแรง:

1. **lazy import** ของ mlflow/torch/neuralprophet — 665 MB → ~150–250 MB
   ทำให้ย้ายไป Render/Koyeb (512 MB) ได้ด้วย เป็นการไม่ผูกกับเจ้าใดเจ้าหนึ่ง
2. **ย้าย ingestion ไป GitHub Actions cron** — repo เป็น public ดังนั้น
   Actions ฟรีไม่จำกัด ไม่ต้องให้ API ตื่นมา poll ทุก 10 นาที
3. **ตัด Postgres ทิ้ง** ใช้ SQLite (`aiosqlite` เป็น dependency อยู่แล้ว)
   ถ้ายอมรับได้ว่าข้อมูลรีเซ็ตตอน restart
