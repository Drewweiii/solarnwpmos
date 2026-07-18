// Mirrors the Pydantic response models in api/src/nongfab_api/*.py - kept to
// the fields the dashboard actually reads (backend models carry more optional
// survey/equipment detail than listed here; extra JSON keys are simply
// ignored by TypeScript's structural typing).

export interface LatLon {
  lat: number
  lon: number
  elevation_m: number | null
  note: string | null
}

export interface ModuleSpec {
  name: string
  power_w: number
  technology: string
  efficiency_pct: number
}

export interface InverterDetail {
  model: string
  count: number
  ac_kw_each: number
  efficiency_pct: number
}

export interface Zone {
  id: string
  name_full: string
  ac_capacity_kw: number
  dc_capacity_kwp: number
  dc_ac_ratio: number
  module_count: number
  module_power_w: number
  inverter_model: string
  inverter_count: number
  centroid: LatLon
  simulated: boolean
  module_detail: ModuleSpec | null
  inverter_detail: InverterDetail | null
}

export interface AssetRegistry {
  zones: Zone[]
}

export type ForecastHorizon = 'minute' | 'hour' | 'day'

export interface ForecastPoint {
  timestamp: string
  pred: number
  lower: number | null
  upper: number | null
  // Which model produced this point - "lightgbm"/"random_forest" for
  // hour-ahead (a real per-lead-hour auto-select result), a fixed
  // "cnn_lstm"/"neuralprophet" for minute-/day-ahead, or null for the
  // physics-only fallback (no ML model ran). Drives the dashboard's
  // green/orange dot coloring on the Intra-day chart.
  algorithm: string | null
  // The winning algorithm's own held-out validation RMSE for this lead hour
  // (hour-ahead only) - a measured "how far off was this model on data it
  // didn't train on" figure, not a live/real-time error. null where no such
  // metric exists (minute/day/physics-baseline).
  error: number | null
  // Every hour-ahead candidate's own validation RMSE for this lead hour, not
  // just the winner's `error` above - e.g. { lightgbm: 1.2, random_forest:
  // 1.5, sum_k_lstm: 1.4 }. Lets the dashboard plot all three models' error
  // side by side (ForecastPage's per-model error lines + the Model
  // Competition panel), not just whichever one won. null/{} where no such
  // per-candidate breakdown exists (minute/day/physics-baseline, or a point
  // served from a model trained before this field existed).
  candidate_errors: Record<string, number> | null
}

export interface ForecastResponse {
  zone: string
  horizon: ForecastHorizon
  issued_at: string
  model_version: number
  points: ForecastPoint[]
  data_source: string
  // "ml" once a real model is trained, "physics_baseline" while too little
  // real history has accumulated - see forecast/serving.py's
  // get_forecast_with_fallback() docstring. The dashboard uses this to
  // caption the prediction-interval band honestly (fixed +/-20% placeholder
  // vs. a real quantile model's output), not to imply it's ML when it isn't.
  model_type: string
}

export interface WeatherStripPoint {
  timestamp: string
  temp_c: number
  ssrd_w_m2: number
}

// "real" once GET /weather/strip finds real accumulated NWP data covering
// (most of) the requested window, "synthetic" otherwise - see
// routes_weather.py's own docstring. Drives the same honest-labeling
// convention as ForecastResponse.data_source. Named/exported (not just
// inlined on WeatherStripResponse below) so WeatherStrip.tsx can type its
// own `dataSource` prop against it too.
export type ForecastDataSource = 'real' | 'synthetic'

export interface WeatherStripResponse {
  data_source: ForecastDataSource
  points: WeatherStripPoint[]
}

export interface HourlyPoint {
  timestamp: string
  ac_kw: number
  ssrd_w_m2: number
  temp_c: number
}

// Persisted actual/generated power for *previous* days (2026-07-18) -
// `hourly` above is always "today" only (synthetic-per-request, no
// persistence - see api/routes_performance.py's own docstring). Backed by
// a genuine, incrementally-accumulated log of this route's own live
// reading at each poll, backfilled on cold start with a physics-baseline
// estimate - see forecast/README.md's "Actual/generated power history"
// entry. Only timestamp/ac_kw - no ssrd/temp breakdown for history.
export interface GeneratedPowerPoint {
  timestamp: string
  ac_kw: number
}

export interface PerformanceResponse {
  zone: string
  simulated_zone: boolean
  latitude: number
  longitude: number
  ac_energy_kwh_today: number
  poa_irradiance_kwh_per_m2_today: number
  performance_ratio: number
  specific_yield_kwh_per_kwp_today: number
  loss_breakdown: Record<string, number>
  hourly: HourlyPoint[]
  history: GeneratedPowerPoint[]
  cloud_factor: number
}

export interface SimulateRequest {
  extra_cloud_attenuation_pct?: number
  curtailment_pct?: number
  degradation_pct_per_year?: number
  years_since_commissioning?: number
  extra_cloud_attenuation_std_pct?: number
  curtailment_std_pct?: number
  degradation_std_pct_per_year?: number
  monte_carlo_n_samples?: number
}

export interface SimulatePointOut {
  timestamp: string
  baseline_ac_kw: number
  adjusted_ac_kw: number
  lower: number | null
  upper: number | null
}

export interface SimulateResponse {
  zone: string
  simulated_zone: boolean
  points: SimulatePointOut[]
  loss_breakdown: Record<string, number>
}

// Every field here overrides one of financial/nongfab_financial/model.py's
// FinancialAssumptions defaults - see that module's own docstring for which
// are documented placeholders (CAPEX/tariff/WACC/BOI) vs. real facts
// (Thailand's standard corporate tax rate).
export interface FinancialRequest {
  capex_thb?: number
  opex_pct_of_capex_per_year?: number
  tariff_thb_per_kwh?: number
  tariff_escalation_pct_per_year?: number
  opex_escalation_pct_per_year?: number
  discount_rate_pct?: number
  tax_rate_pct?: number
  boi_tax_holiday_years?: number
  degradation_pct_per_year?: number
  lifetime_years?: number
}

export interface CashFlowYearOut {
  year: number
  ac_energy_kwh: number
  avoided_cost_thb: number
  opex_thb: number
  tax_thb: number
  net_cash_flow_thb: number
  cumulative_undiscounted_cash_flow_thb: number
  cumulative_discounted_cash_flow_thb: number
}

export interface FinancialResponse {
  installed_dc_capacity_kwp: number
  year_1_ac_energy_kwh: number
  capex_thb: number
  npv_thb: number
  irr_pct: number | null
  lcoe_thb_per_kwh: number
  simple_payback_years: number | null
  discounted_payback_years: number | null
  cash_flows: CashFlowYearOut[]
}

export interface SolarPosition {
  azimuth_deg: number
  elevation_deg: number
}

export interface Panel {
  block_id: string
  row: number
  col: number
  east_m: number
  north_m: number
  width_m: number
  slant_height_m: number
  solar_access_pct: number
}

export interface StringEstimate {
  block_id: string
  string_index: number
  module_count: number
  avg_solar_access_pct: number
  estimated_power_kw: number
}

export interface StringBalance {
  block_id: string
  strings: StringEstimate[]
  imbalance_kw: number
  max_allowed_kw: number | null
  exceeds_limit: boolean
}

export interface GeometryResponse {
  zone: string
  simulated_zone: boolean
  at: string
  tilt_deg: number
  azimuth_deg: number
  row_pitch_m: number
  sun: SolarPosition
  average_solar_access_pct: number
  panels: Panel[]
  string_balance: StringBalance[]
}

export interface SunPathPoint {
  time: string
  azimuth_deg: number
  elevation_deg: number
}

export interface SunPathResponse {
  zone: string
  date: string
  points: SunPathPoint[]
}

export interface SystemSummary {
  ac_capacity_kw: number
  dc_capacity_kwp: number
  dc_ac_ratio: number
  module_count: number
  module_power_w: number
  array_area_m2: number | null
  inverter_model: string
  inverter_count: number
}

export interface AnnualSummary {
  ac_energy_kwh: number
  specific_yield_kwh_per_kwp: number
  performance_ratio: number
}

export interface SLDString {
  id: string
  modules: number
}

export interface SLDBlock {
  id: string
  inverter_model: string
  inverter_ac_kw: number
  mppt_count: number
  strings: SLDString[]
}

export interface SLDData {
  module_model: string | null
  module_power_w: number
  optimizer_model: string | null
  optimizer_ratio_modules_per_optimizer: number | null
  blocks: SLDBlock[]
  approximate_string_distribution: boolean
}

export interface MonthlyEnergyEstimate {
  month: number
  ac_energy_kwh: number
  is_rainy_season: boolean
}

export interface LifecycleEstimate {
  year_1_ac_energy_kwh: number
  year_25_ac_energy_kwh: number
  year_25_pct_of_year_1: number
  lifetime_ac_energy_kwh: number
  degradation_pct_per_year_assumed: number
}

export interface EnergyReportResponse {
  zone: string
  simulated_zone: boolean
  system_summary: SystemSummary
  annual: AnnualSummary
  loss_breakdown_pct: Record<string, number>
  co2_saved_kg_per_year: number
  trees_equivalent_per_year: number
  avg_solar_access_pct: number
  monthly: MonthlyEnergyEstimate[]
  lifecycle: LifecycleEstimate
  sld: SLDData
}

export interface IrradianceGridPoint {
  lat: number
  lon: number
  ghi_w_m2: number
  cloud_factor: number
}

export interface ZonePin {
  id: string
  name_full: string
  lat: number
  lon: number
  ac_capacity_kw: number
  simulated: boolean
  ghi_w_m2: number
  cloud_factor: number
  estimated_ac_kw: number
  plant_factor: number
  boundary: { lat: number; lon: number }[]
}

export interface IrradianceMapResponse {
  at: string
  sun: SolarPosition
  clearsky_ghi_w_m2: number
  grid: IrradianceGridPoint[]
  zones: ZonePin[]
}

// Visitor network (ws_chat.py / routes_feedback.py)

export interface ChatMessage {
  type: 'message'
  id: number
  username: string
  role: string
  text: string
  created_at: string
  display_name: string
  avatar: string | null
  client_id: string | null
}

export interface ChatPresence {
  type: 'presence'
  count: number
  usernames: string[]
}

export interface ChatHistory {
  type: 'history'
  messages: ChatMessage[]
}

export type ChatEvent = ChatMessage | ChatPresence | ChatHistory

export interface FeedbackItem {
  id: number
  username: string
  role: string
  text: string
  created_at: string
}
