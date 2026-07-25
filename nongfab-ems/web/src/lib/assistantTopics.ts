// The menu structure behind น้อง Solar's guided Q&A browsing ("หมวดคำถาม"):
// three top-level categories, each holding a handful of topic groups, each
// holding a few concrete sub-questions. This file only defines the *menu*
// (labels/keywords/navigation) - the actual answer text for each
// sub-question lives in assistantContent.ts, kept separate so the content
// (which the user expects to keep growing over many future sessions,
// especially category 1.3 "การใช้เว็บนี้") can be edited on its own without
// touching this structural file.
//
// A sub-question's `question` field doubles as the exact text sent through
// the normal assistant pipeline when its button is clicked (assistant.ts
// matches on it as a long, near-unique keyword) AND as the "user" chat
// bubble text shown for that click - so phrase it as a real question, not
// a menu label (use `label` for the short button text instead).

export interface AssistantSubQuestion {
  id: string
  /** Short button text. */
  label: string
  /** Full question text - sent through the normal pipeline when clicked. */
  question: string
}

export interface AssistantTopicGroup {
  id: string
  title: string
  /** Bare keywords that, typed alone with no other intent match, trigger a
   * clarifying menu of this group's sub-questions (see findClarifyGroup). */
  keywords: string[]
  subQuestions: AssistantSubQuestion[]
  /** Set on groups describing an operator/admin-only page (Simulation,
   * Financial - see Layout.tsx/App.tsx's RequireOperator, 2026-07-18).
   * groupsForRole() below drops these from the browsable "การใช้เว็บนี้"
   * menu for a viewer, since offering a menu button for a page they can't
   * open is worse than not mentioning it. The underlying answer (in
   * assistantContent.ts) still exists and still notes the restriction, for
   * anyone who reaches it a different way (e.g. typing the exact question). */
  viewerHidden?: boolean
}

export interface AssistantTopicCategory {
  id: string
  emoji: string
  title: string
  description: string
  groups: AssistantTopicGroup[]
}

export const TOPIC_CATEGORIES: AssistantTopicCategory[] = [
  {
    id: 'system',
    emoji: '🔧',
    title: 'ความรู้เรื่องระบบ Solar',
    description: 'แผงโซลาร์ อินเวอร์เตอร์ ออปติไมเซอร์ และหลักการออกแบบระบบ',
    groups: [
      {
        id: 'solar_basic',
        title: 'Solar cell / พลังงานแสงอาทิตย์',
        keywords: ['solar cell', 'เซลล์แสงอาทิตย์', 'พลังงานแสงอาทิตย์'],
        subQuestions: [
          { id: 'solar_what', label: 'Solar cell คืออะไร', question: 'Solar cell คืออะไร' },
          { id: 'solar_how', label: 'ผลิตไฟได้ยังไง', question: 'แผงโซลาร์ผลิตไฟได้ยังไง' },
        ],
      },
      {
        id: 'panel',
        title: 'แผงโซลาร์',
        keywords: ['แผงโซลาร์', 'แผงคือ', 'module คือ', 'โมดูลคือ'],
        subQuestions: [{ id: 'panel_what', label: 'แผงโซลาร์คืออะไร', question: 'แผงโซลาร์คืออะไร' }],
      },
      {
        id: 'inverter',
        title: 'Inverter',
        keywords: ['inverter', 'อินเวอร์เตอร์'],
        subQuestions: [
          { id: 'inv_what', label: 'Inverter คืออะไร', question: 'Inverter คืออะไร' },
          { id: 'inv_important', label: 'สำคัญยังไง', question: 'Inverter สำคัญยังไง' },
          { id: 'inv_huawei', label: 'ทำไมใช้ Huawei', question: 'ทำไมโครงการนี้ใช้ inverter ยี่ห้อ Huawei' },
        ],
      },
      {
        id: 'optimizer',
        title: 'Optimizer',
        keywords: ['optimizer', 'ออปติไมเซอร์'],
        subQuestions: [
          { id: 'opt_what', label: 'Optimizer คืออะไร', question: 'Optimizer คืออะไร' },
          { id: 'opt_why', label: 'มีไว้ทำไม', question: 'Optimizer มีไว้ทำไม' },
        ],
      },
      {
        id: 'vdrop',
        title: 'Vdrop / Vrise',
        keywords: ['vdrop', 'vrise', 'แรงดันตก', 'แรงดันเกิน'],
        subQuestions: [
          { id: 'vd_what', label: 'Vdrop/Vrise คืออะไร', question: 'Vdrop และ Vrise คืออะไร' },
          { id: 'vd_why', label: 'ทำไมสำคัญ', question: 'ทำไม Vdrop Vrise ถึงสำคัญ' },
        ],
      },
      {
        id: 'standard',
        title: 'กฎหมาย/มาตรฐาน',
        keywords: ['กฎหมายโซลาร์', 'มาตรฐานโซลาร์', 'ระเบียบการติดตั้ง'],
        subQuestions: [
          { id: 'std_law', label: 'กฎหมาย/ระเบียบที่เกี่ยวข้อง', question: 'มีกฎหมายหรือระเบียบอะไรบ้างที่เกี่ยวข้องกับการออกแบบระบบโซลาร์' },
        ],
      },
      {
        id: 'marine',
        title: 'มาตรฐาน Marine',
        keywords: ['marine', 'ไอเกลือ', 'กันสนิม'],
        subQuestions: [{ id: 'marine_what', label: 'มาตรฐาน Marine คืออะไร', question: 'มาตรฐาน marine ในการออกแบบระบบโซลาร์คืออะไร' }],
      },
      {
        id: 'mounting',
        title: 'โครงยึดแผง (Mounting)',
        keywords: ['mounting', 'โครงยึดแผง', 'ขาตั้งแผง'],
        subQuestions: [
          { id: 'mount_what', label: 'ออกแบบ Mounting ต้องคำนึงถึงอะไร', question: 'การออกแบบโครงยึดแผงโซลาร์ (mounting) ต้องคำนึงถึงอะไรบ้าง' },
        ],
      },
      {
        id: 'panel_care',
        title: 'ประสิทธิภาพ / การดูแลแผง',
        keywords: ['ฝุ่นเกาะแผง', 'ล้างแผง', 'แผงเสื่อม', 'degradation', 'soiling', 'แผงร้อน', 'แผงสกปรก'],
        subQuestions: [
          { id: 'care_soiling', label: 'ฝุ่นเกาะแผงมีผลไหม', question: 'ฝุ่นหรือสิ่งสกปรกเกาะแผงโซลาร์มีผลกับการผลิตไฟไหม' },
          { id: 'care_degradation', label: 'แผงเสื่อมสภาพยังไง', question: 'แผงโซลาร์เสื่อมสภาพยังไง ใช้งานได้นานแค่ไหน' },
          { id: 'care_temp', label: 'ยิ่งร้อนยิ่งดีไหม', question: 'อากาศยิ่งร้อนยิ่งแดดแรง แผงโซลาร์ผลิตไฟได้ดีขึ้นไหม' },
        ],
      },
      {
        id: 'faq_practical',
        title: 'คำถามที่พบบ่อย (โซลาร์ในชีวิตจริง)',
        keywords: ['กลางคืน', 'ฝนตก', 'ไฟดับ', 'แบตเตอรี่', 'ลูกเห็บ', 'เก็บไฟ'],
        subQuestions: [
          { id: 'faq_night', label: 'กลางคืนผลิตไฟได้ไหม', question: 'ตอนกลางคืนแผงโซลาร์ยังผลิตไฟได้ไหม' },
          { id: 'faq_rain', label: 'ฝนตก/หน้าฝนยังผลิตได้ไหม', question: 'ฝนตกหรือหน้าฝนแผงโซลาร์ยังผลิตไฟได้ไหม' },
          { id: 'faq_blackout', label: 'ไฟดับใช้ไฟโซลาร์ได้ไหม', question: 'ตอนไฟฟ้าดับ ระบบโซลาร์ยังจ่ายไฟให้ใช้ได้ไหม' },
          { id: 'faq_battery', label: 'มีแบตเตอรี่เก็บไฟไหม', question: 'โรงไฟฟ้าโซลาร์นี้มีแบตเตอรี่เก็บไฟไว้ใช้กลางคืนไหม' },
        ],
      },
    ],
  },
  {
    id: 'energy',
    emoji: '⚡',
    title: 'ความรู้เรื่องระบบพลังงาน',
    description: 'ค่าไฟ ทำไม Solar สำคัญ EF Carbon Credit Carbon Footprint Net Zero',
    groups: [
      {
        id: 'bill',
        title: 'ค่าไฟฟ้า',
        keywords: ['ค่าไฟ', 'บิลไฟ'],
        subQuestions: [{ id: 'bill_calc', label: 'ค่าไฟฟ้าคิดยังไง', question: 'ค่าไฟฟ้าคิดยังไง' }],
      },
      {
        id: 'why_solar',
        title: 'ทำไม Solar สำคัญ',
        keywords: ['ทำไมโซลาร์สำคัญ', 'ทำไมต้องติดโซลาร์'],
        subQuestions: [{ id: 'why_solar', label: 'ทำไม Solar สำคัญ', question: 'ทำไม solar ถึงสำคัญ' }],
      },
      {
        id: 'ef',
        title: 'ค่า EF',
        keywords: ['emission factor', 'ค่า ef'],
        subQuestions: [{ id: 'ef_what', label: 'EF คืออะไร', question: 'ค่า EF คืออะไร' }],
      },
      {
        id: 'carbon_credit',
        title: 'Carbon Credit',
        keywords: ['carbon credit', 'คาร์บอนเครดิต'],
        subQuestions: [{ id: 'cc_what', label: 'Carbon Credit คืออะไร', question: 'Carbon Credit คืออะไร' }],
      },
      {
        id: 'carbon_footprint',
        title: 'Carbon Footprint',
        keywords: ['carbon footprint', 'คาร์บอนฟุตพริ้นท์', 'รอยเท้าคาร์บอน'],
        subQuestions: [{ id: 'cf_what', label: 'Carbon Footprint คืออะไร', question: 'Carbon Footprint คืออะไร' }],
      },
      {
        id: 'net_zero',
        title: 'Net Zero',
        keywords: ['net zero', 'เน็ตซีโร่'],
        subQuestions: [{ id: 'nz_what', label: 'Net Zero คืออะไร', question: 'Net Zero คืออะไร' }],
      },
      {
        id: 'grid_sell',
        title: 'การขายไฟ / เชื่อมสายส่ง',
        keywords: ['ขายไฟ', 'ppa', 'ไฟเข้ากริด', 'on-grid', 'ออนกริด'],
        subQuestions: [
          { id: 'grid_ppa', label: 'ขายไฟให้การไฟฟ้ายังไง', question: 'โรงไฟฟ้าโซลาร์ขายไฟให้การไฟฟ้ายังไง' },
          { id: 'grid_ongrid', label: 'On-grid ต่างจากมีแบตยังไง', question: 'ระบบ on-grid ไม่มีแบตเตอรี่ ต่างจากระบบที่มีแบตเตอรี่ยังไง' },
        ],
      },
    ],
  },
  {
    id: 'forecasting',
    emoji: '📈',
    title: 'หลักการพยากรณ์การผลิตไฟ',
    description: 'ระบบพยากรณ์ทำงานยังไง ใช้โมเดลอะไรบ้าง รับข้อมูลจากไหน แม่นแค่ไหน',
    groups: [
      {
        id: 'forecast_overview',
        title: 'ภาพรวมระบบพยากรณ์',
        keywords: ['ระบบพยากรณ์ทำงานยังไง', 'โมเดลพยากรณ์'],
        subQuestions: [
          { id: 'fc_how', label: 'พยากรณ์ทำงานยังไง (ภาพรวม)', question: 'ระบบพยากรณ์การผลิตไฟฟ้าทำงานยังไง' },
          { id: 'fc_horizons', label: 'ทำไมต้องมี 3 ระยะเวลา', question: 'ทำไมระบบต้องพยากรณ์ถึง 3 ระยะเวลา' },
          { id: 'fc_models', label: 'แต่ละระยะใช้โมเดลอะไร ทำไม', question: 'พยากรณ์แต่ละระยะเวลาใช้โมเดลอะไร ทำไมถึงเลือกโมเดลนั้น' },
          { id: 'fc_data', label: 'ข้อมูลมาจากไหนบ้าง', question: 'โมเดลพยากรณ์เอาข้อมูลมาจากไหนบ้าง' },
        ],
      },
      {
        id: 'forecast_advanced',
        title: 'รายละเอียดเชิงลึก',
        keywords: ['model competition', 'การแข่งขันโมเดล', 'physics baseline', 'prediction interval'],
        subQuestions: [
          { id: 'fc_competition', label: 'Model Competition คืออะไร', question: 'การแข่งขันของโมเดล (Model Competition) คืออะไร' },
          { id: 'fc_interval', label: 'ช่วงความไม่แน่นอนคืออะไร', question: 'ช่วงความไม่แน่นอน (Prediction Interval) ในกราฟคืออะไร แม่นแค่ไหน' },
          { id: 'fc_physics', label: 'Physics baseline คืออะไร', question: 'Physics baseline คืออะไร ทำไมบางทีไม่ได้ใช้ AI พยากรณ์' },
          { id: 'fc_retrain', label: 'โมเดลเรียนรู้ใหม่บ่อยแค่ไหน', question: 'โมเดลพยากรณ์มีการเรียนรู้ข้อมูลใหม่บ่อยแค่ไหน' },
          { id: 'fc_accuracy', label: 'รู้ได้ยังไงว่าแม่นแค่ไหน', question: 'รู้ได้ยังไงว่าพยากรณ์การผลิตไฟแม่นแค่ไหน' },
        ],
      },
      {
        // Added 2026-07-25 (Track 1). The site now labels the provenance of
        // every number it shows (Forecast's 9-variable table, the EGAT panel,
        // the Settings origin chips), so the assistant needed answers for the
        // obvious follow-up: "where did this number come from, and is it
        // measured or computed?" - the honest answer being the point.
        id: 'data_provenance',
        title: 'ตัวเลขในเว็บนี้มาจากไหน',
        keywords: ['ข้อมูลมาจากไหน', 'ที่มาของข้อมูล', 'เชื่อได้ไหม', 'วัดจริงไหม', 'กฟผ', 'egat'],
        subQuestions: [
          {
            id: 'data_table_source',
            label: 'ตารางสภาพอากาศเอาค่ามาจากไหน',
            question: 'ตารางสภาพอากาศ 9 ช่องในหน้า Forecast เอาค่ามาจากไหน',
          },
          {
            id: 'data_no_sensor',
            label: 'ไม่มีเซนเซอร์หน้างาน แล้วเชื่อได้ไหม',
            question: 'เว็บนี้ไม่มีเซนเซอร์วัดอากาศที่หน้างาน แล้วตัวเลขเชื่อถือได้แค่ไหน',
          },
          {
            id: 'data_egat',
            label: 'ตัวเลขไฟทั้งประเทศมาจากไหน',
            question: 'ตัวเลขระบบไฟฟ้าทั้งประเทศที่เอามาเทียบกับหนองแฟบ มาจากไหน',
          },
          {
            id: 'data_official',
            label: 'ค่าไฟ/ค่าคาร์บอนอ้างอิงจากอะไร',
            question: 'ค่าไฟต่อหน่วยกับค่าการปล่อยคาร์บอนที่เว็บนี้ใช้ อ้างอิงจากประกาศไหน',
          },
        ],
      },
    ],
  },
  {
    id: 'website',
    emoji: '🌐',
    title: 'การใช้เว็บไซต์นี้',
    description: 'แต่ละหน้าดูอะไรได้บ้าง (หมวดนี้จะอัปเดตเพิ่มเรื่อยๆ ตามฟีเจอร์ใหม่)',
    groups: [
      {
        id: 'page_forecast',
        title: 'หน้า Forecast',
        keywords: [],
        subQuestions: [{ id: 'page_forecast', label: 'หน้า Forecast ใช้ดูอะไร', question: 'หน้า Forecast ในเว็บนี้ใช้ดูอะไรได้บ้าง' }],
      },
      {
        id: 'page_simulation',
        title: 'หน้า Simulation',
        keywords: [],
        viewerHidden: true,
        subQuestions: [{ id: 'page_simulation', label: 'หน้า Simulation ใช้ดูอะไร', question: 'หน้า Simulation ในเว็บนี้ใช้ทำอะไรได้บ้าง' }],
      },
      {
        id: 'page_financial',
        title: 'หน้า Financial',
        keywords: [],
        viewerHidden: true,
        subQuestions: [{ id: 'page_financial', label: 'หน้า Financial ใช้ดูอะไร', question: 'หน้า Financial ในเว็บนี้ใช้ดูอะไรได้บ้าง' }],
      },
      {
        id: 'page_3d',
        title: 'หน้า 3D View',
        keywords: [],
        subQuestions: [{ id: 'page_3d', label: 'หน้า 3D View ใช้ดูอะไร', question: 'หน้า 3D View ในเว็บนี้ใช้ดูอะไรได้บ้าง' }],
      },
      {
        id: 'page_energy_report',
        title: 'หน้า Energy Report',
        keywords: ['ประหยัดค่าไฟ', 'คาร์บอนเครดิต', 'carbon credit', 'ลด co2', 'ugt'],
        subQuestions: [
          { id: 'page_energy_report', label: 'หน้า Energy Report ใช้ดูอะไร', question: 'หน้า Energy Report ในเว็บนี้ใช้ดูอะไรได้บ้าง' },
          { id: 'energy_savings', label: 'ดูค่าไฟที่ประหยัด/คาร์บอนได้ไหม', question: 'โซลาร์ช่วยประหยัดค่าไฟและลดคาร์บอนได้เท่าไหร่ ดูตรงไหน' },
        ],
      },
      {
        id: 'page_irradiance',
        title: 'แผนที่ความเข้มแสง (ในหน้า 3D View)',
        keywords: [],
        subQuestions: [
          { id: 'page_irradiance', label: 'แผนที่ความเข้มแสงอยู่ตรงไหน', question: 'แผนที่ความเข้มแสง (irradiance map) ในเว็บนี้อยู่ตรงไหน ใช้ดูอะไรได้บ้าง' },
        ],
      },
      {
        id: 'page_chat',
        title: 'แชทคุยกับผู้ชมคนอื่น',
        keywords: [],
        subQuestions: [{ id: 'page_chat', label: 'แชทกับผู้ชมคนอื่นใช้ยังไง', question: 'แชทคุยกับผู้ชมคนอื่นในเว็บนี้ใช้ยังไง' }],
      },
    ],
  },
]

export const ALL_TOPIC_GROUPS: AssistantTopicGroup[] = TOPIC_CATEGORIES.flatMap((c) => c.groups)

/** A bare keyword (e.g. someone just typing "inverter" with no specific
 * question) matches a group here - the caller then offers that group's
 * sub-questions as a clarifying menu instead of guessing which one they meant. */
export function findClarifyGroup(question: string): AssistantTopicGroup | null {
  const lower = question.toLowerCase()
  for (const group of ALL_TOPIC_GROUPS) {
    if (group.keywords.some((kw) => lower.includes(kw))) return group
  }
  return null
}

export function findGroupBySubQuestionId(subQuestionId: string): AssistantTopicGroup | null {
  return ALL_TOPIC_GROUPS.find((g) => g.subQuestions.some((sq) => sq.id === subQuestionId)) ?? null
}

export function findCategoryById(categoryId: string): AssistantTopicCategory | null {
  return TOPIC_CATEGORIES.find((c) => c.id === categoryId) ?? null
}

export function findGroupById(groupId: string): AssistantTopicGroup | null {
  return ALL_TOPIC_GROUPS.find((g) => g.id === groupId) ?? null
}

/** A category's groups, filtered to what the given role can actually reach -
 * drops `viewerHidden` groups (Simulation/Financial) when `role === 'viewer'`,
 * unfiltered for every other role (including unknown/missing role, so this
 * never over-hides by default). */
export function groupsForRole(category: AssistantTopicCategory, role: string | null | undefined): AssistantTopicGroup[] {
  if (role !== 'viewer') return category.groups
  return category.groups.filter((g) => !g.viewerHidden)
}
