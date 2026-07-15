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
}

export interface ForecastResponse {
  zone: string
  horizon: ForecastHorizon
  issued_at: string
  model_version: number
  points: ForecastPoint[]
}

export interface HourlyPoint {
  timestamp: string
  ac_kw: number
  ssrd_w_m2: number
  temp_c: number
}

export interface PerformanceResponse {
  zone: string
  simulated_zone: boolean
  ac_energy_kwh_today: number
  poa_irradiance_kwh_per_m2_today: number
  performance_ratio: number
  specific_yield_kwh_per_kwp_today: number
  loss_breakdown: Record<string, number>
  hourly: HourlyPoint[]
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

export interface EnergyReportResponse {
  zone: string
  simulated_zone: boolean
  system_summary: SystemSummary
  annual: AnnualSummary
  loss_breakdown_pct: Record<string, number>
  co2_saved_kg_per_year: number
  trees_equivalent_per_year: number
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
}

export interface IrradianceMapResponse {
  at: string
  sun: SolarPosition
  clearsky_ghi_w_m2: number
  grid: IrradianceGridPoint[]
  zones: ZonePin[]
}
