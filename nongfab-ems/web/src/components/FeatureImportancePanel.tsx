// Feature-importance panel for the Forecast page (2026-07-24) - shows how much
// each input drives the hour-ahead model, with the new marine/aerosol features
// (salt spray, AOD, dust, PM) highlighted so the user can see how much the
// newly-added variables actually contribute. Data from GET
// /forecast/{zone}/feature-importance (see routes_forecast.py); renders an
// honest "not trained yet" state when the model doesn't exist, never a
// fabricated chart.
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useFeatureImportance } from '../lib/queries'

export interface FeatureImportancePanelProps {
  zone: string
}

// Internal model feature name -> short friendly (Thai) label.
const FEATURE_LABELS: Record<string, string> = {
  ssrd_w_m2: 'I (แสงอาทิตย์)',
  temp2m_c: 'T (อุณหภูมิ)',
  power_lag1: 'กำลังไฟก่อนหน้า',
  clear_sky_ssrd_w_m2: 'I_clr (ท้องฟ้าใส)',
  cloud_index: 'ดัชนีเมฆ (CI)',
  wind_speed_ms: 'ความเร็วลม',
  relative_humidity_pct: 'ความชื้น (RH)',
  precip_mm: 'ฝน',
  salt_soiling_index: 'ละอองเกลือ (salt)',
  aod_550nm: 'AOD (ละอองลอย)',
  dust: 'ฝุ่นแร่ (dust)',
  pm2_5: 'PM2.5',
  pm10: 'PM10',
}

const NEW_COLOR = '#0d9488' // teal - the 2026-07-24 marine/aerosol features
const BASE_COLOR = '#64748b' // slate - the original features

function labelFor(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature
}

export function FeatureImportancePanel({ zone }: FeatureImportancePanelProps) {
  const query = useFeatureImportance(zone)

  const rows =
    query.data?.items.map((it) => ({
      name: labelFor(it.feature),
      pct: it.importance * 100,
      isNew: it.is_new,
    })) ?? []

  return (
    <section className="feature-importance-panel" aria-label="Feature importance">
      <h3 className="forecast-minute-title">ความสำคัญของตัวแปรต่อโมเดล (Feature importance)</h3>
      <p className="forecast-error-subtitle">
        โมเดล Hour-ahead ให้น้ำหนักแต่ละตัวแปรมากแค่ไหน — ตัวแปรทางทะเล/ละอองลอยที่เพิ่มใหม่แสดงเป็น
        <span className="feature-importance-legend-new"> สีเขียว</span>
      </p>

      {query.isLoading && <p className="forecast-status">Loading…</p>}

      {!query.isLoading && (!query.data || !query.data.available || rows.length === 0) && (
        <p className="forecast-status">
          ยังไม่มีโมเดล (แบบต้นไม้) ที่เทรนแล้วสำหรับโซนนี้ จึงยังคำนวณความสำคัญของตัวแปรไม่ได้ —
          จะปรากฏเมื่อมีข้อมูลสะสมพอให้เทรนโมเดล (ไม่แสดงกราฟปลอม)
        </p>
      )}

      {!query.isLoading && query.data?.available && rows.length > 0 && (
        <>
          {query.data.new_features_total != null && (
            <p className="feature-importance-headline">
              ตัวแปรใหม่ (ทะเล/ละอองลอย) รวมกันมีน้ำหนัก{' '}
              <strong>{(query.data.new_features_total * 100).toFixed(1)}%</strong> ของการตัดสินใจของโมเดล
            </p>
          )}
          <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 26)}>
            <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
              <XAxis type="number" unit="%" domain={[0, 'dataMax']} />
              <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: unknown) => (typeof v === 'number' ? `${v.toFixed(1)}%` : String(v))} />
              <Bar dataKey="pct" name="ความสำคัญ" radius={[0, 4, 4, 0]}>
                {rows.map((r) => (
                  <Cell key={r.name} fill={r.isNew ? NEW_COLOR : BASE_COLOR} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="forecast-status forecast-status-caption">
            คำนวณจากค่า importance ของโมเดลต้นไม้ (LightGBM/Random Forest) เฉลี่ยข้ามช่วงเวลาพยากรณ์ +1h..+6h —
            เป็นความสำคัญเชิงสัมพัทธ์ (รวมกัน 100%) ไม่ใช่หน่วยพลังงาน
          </p>
        </>
      )}
    </section>
  )
}
