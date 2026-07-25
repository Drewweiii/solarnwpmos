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

// Public facts about the host LNG terminal (Map Ta Phut Terminal 2 / Nong Fab)
// the solar array sits on - sourced, not measured by this project. Surfaced
// read-only in the "About this facility" card. All fields optional/nullable
// since the backend defaults them to None when the YAML omits the block.
export interface LngTerminal {
  // Identity
  official_name: string
  also_known_as: string
  is_thailand_second_onshore_terminal: boolean
  owner: string
  epc_contractors: string
  owners_engineer: string
  location: string
  // Capacity & storage
  regas_capacity_mmtpa: number | null
  peak_capacity_mmtpa: number | null
  storage_tank_count: number | null
  storage_tank_capacity_m3: number | null
  storage_tank_type: string
  storage_claim: string
  // Marine / jetty
  jetty_length_km_public: number | null
  jetty_length_km_user_stated: number | null
  trestle_length_km: number | null
  jetty_claim: string
  lng_carrier_min_m3: number | null
  lng_carrier_max_m3: number | null
  // Project & investment
  contract_awarded_year: number | null
  epc_contract_value_musd: number | null
  investment_cost_billion_thb: number | null
  operational_since_year: number | null
  first_cargo_date: string
  first_cargo_carrier: string
  first_cargo_origin: string
  // Land use
  land_area_total_ha: number | null
  land_area_terminal_ha: number | null
  land_area_office_ha: number | null
  // Sustainability
  cold_energy_reuse: boolean
  seawater_recycling: boolean
  landscape_award: string
  sources: string[]
}

export interface SiteInfo {
  name: string
  project_code: string
  facility_code: string
  street_address: string
  lng_terminal: LngTerminal | null
  // Facility average electrical demand (kW), user-stated real figure (~13.5 MW).
  // Drives the Energy Management panel's "% of facility load offset". null when
  // the backend omits it.
  facility_electrical_load_kw: number | null
  // Facility average annual electricity cost (THB/yr), user-stated (~300 MTHB).
  // Lets the panel show the solar output as an approximate baht/yr bill saving.
  facility_annual_electricity_cost_thb: number | null
}

export interface AssetRegistry {
  site?: SiteInfo
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

// 2026-07-18: gained the rest of the Songsiri 9-variable set (see
// CurrentConditionsResponse's own docstring) for ForecastPage's grouped
// variable graphs - `relative_humidity_pct`/`wind_speed_ms` are null in
// synthetic-fallback mode (the synthetic baseline never models them);
// `clearsky_ghi_w_m2`/`zenith_deg`/`cos_zenith` are always populated (pure
// astronomy, independent of data source).
export interface WeatherStripPoint {
  timestamp: string
  temp_c: number
  ssrd_w_m2: number
  // relative_humidity_pct/wind_speed_ms are deliberately null for future
  // timestamps even in real-data mode (2026-07-19 merge reconciliation) -
  // unlike ssrd/temp, neither was ever validated as a trained-model
  // regressor in this pipeline, so presenting them as "forecast" would
  // overstate confidence this project hasn't earned for them yet.
  // clearsky_ghi_w_m2/zenith_deg/cos_zenith are pure solar geometry (no
  // forecast needed) and are always populated, past or future.
  relative_humidity_pct: number | null
  wind_speed_ms: number | null
  clearsky_ghi_w_m2: number
  zenith_deg: number
  cos_zenith: number
  clear_sky_index: number | null
  // Marine/aerosol model inputs (2026-07-24). salt_soiling_index (0..1) is
  // derived (wind+humidity) so it's populated for future points too; aerosol
  // fields are the real reading nearest each point, or null where the CAMS
  // ingestion has no coverage (never the model's neutral fallback default).
  salt_soiling_index: number | null
  aod_550nm: number | null
  dust: number | null
  pm2_5: number | null
  pm10: number | null
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

// GET /weather/clouds - latest real Himawari cloud reading, site-wide (same
// "weather is site-wide" reasoning as WeatherStripResponse above). Drives
// Solar3DPage's drifting cloud layer (2026-07-18) - `available: false` (not
// an error) whenever no cloud row has ever been recorded yet or the latest
// one is too stale, see routes_weather.py's own docstring.
// motion_speed_kmh/motion_direction_deg are null whenever the underlying
// Himawari frame had no previous frame to diff motion against yet.
export interface CloudConditionsResponse {
  available: boolean
  observed_at: string | null
  cloud_opacity_pct: number | null
  motion_speed_kmh: number | null
  motion_direction_deg: number | null
}

// GET /weather/precipitation - latest real GFS precipitation (APCP) reading
// near "now", site-wide. Drives Solar3DPage's rain animation (2026-07-18 user
// request - Thailand-seasonal rain only, no snow). `available: false` when no
// row within routes_weather.py's near-term lead-hour window carries a real
// (non-null) precip_mm - see that route's own docstring for the accumulation-
// window honesty caveat behind the intensity bands.
export type PrecipitationIntensity = 'none' | 'light' | 'moderate' | 'heavy'

export interface PrecipitationConditionsResponse {
  available: boolean
  observed_at: string | null
  precip_mm: number | null
  intensity: PrecipitationIntensity | null
}

// GET /weather/conditions - real-time snapshot of the 9 solar-forecasting
// input variables from Songsiri's reference deck (I, RH, T, UV, WS, I_clr,
// cosθ, k-hat, I_wrf - see forecast/README.md's "Reference: Songsiri"
// section), added 2026-07-18 for ForecastPage's 3x3 variable table. `UV` is
// daily-resolution (NASA POWER), everything else is effectively real-time
// (next NWP poll, ~hourly) - `uv_observation_date` makes that different
// cadence explicit rather than implying UV updates as often as the rest.
// `forecast_irradiance_w_m2`/`forecast_valid_at` (I_wrf) are the NWP
// model's own near-future prediction, a genuinely different instant than
// `irradiance_w_m2` (I, the nearest-to-now reading) - see the route's own
// docstring for why both ultimately trace back to the same GFS source (no
// independent telemetry sensor exists at this site).
export interface CurrentConditionsResponse {
  available: boolean
  observed_at: string | null
  irradiance_w_m2: number | null
  temp_c: number | null
  relative_humidity_pct: number | null
  wind_speed_ms: number | null
  clearsky_ghi_w_m2: number | null
  zenith_deg: number | null
  cos_zenith: number | null
  clear_sky_index: number | null
  forecast_irradiance_w_m2: number | null
  forecast_valid_at: string | null
  uv_index: number | null
  uv_observation_date: string | null
  // Marine/aerosol model inputs (2026-07-24) - see WeatherStripPoint's note.
  salt_soiling_index: number | null
  aod_550nm: number | null
  dust: number | null
  pm2_5: number | null
  pm10: number | null
}

// GET /forecast/{zone}/feature-importance - relative importance of the
// hour-ahead model's features (2026-07-24), so the dashboard can show how much
// the new marine/aerosol inputs contribute. available:false + empty items when
// no tree-based model is trained yet (honest-empty, never a fabricated chart).
export interface FeatureImportanceItem {
  feature: string
  importance: number // 0..1, all items sum to ~1
  is_new: boolean // one of the 2026-07-24 marine/aerosol features
}

export interface FeatureImportanceResponse {
  available: boolean
  zone: string
  items: FeatureImportanceItem[]
  new_features_total: number | null
}

// GET /expansion - what each planned phase in config/assets.yaml actually buys
// (2026-07-25). `marginal_*` describe the phase itself rather than the running
// total, which is what an investment decision turns on. Everything is derived
// from real figures EXCEPT capex (still the documented ฿30,000/kWp placeholder),
// so `simple_payback_years` inherits that - `capex_note` says so.
export interface ExpansionScenario {
  label: string
  phase: string | null
  ac_capacity_kw: number
  dc_capacity_kwp: number
  annual_energy_kwh: number
  solar_offset_pct: number | null
  annual_bill_saving_thb: number | null
  marginal_ac_capacity_kw: number | null
  marginal_annual_energy_kwh: number | null
  marginal_bill_saving_thb: number | null
  marginal_energy_per_kwp: number | null
  capex_estimate_thb: number | null
  simple_payback_years: number | null
}

export interface ExpansionTarget {
  target_offset_pct: number
  required_dc_capacity_kwp: number
  times_current_capacity: number
}

export interface ExpansionResponse {
  available: boolean
  reason: string | null
  facility_load_kw: number | null
  implied_tariff_thb_per_kwh: number | null
  capex_per_kwp_thb: number
  scenarios: ExpansionScenario[]
  targets: ExpansionTarget[]
  capex_note: string
  method_note: string
}

// GET /diagnostics/feeds - one verdict per external data source (2026-07-25).
// `kind` matters: an 'observation' feed (satellite cloud, UV) is healthy while
// its newest row is RECENT, while a 'coverage' feed (NWP, aerosol - forecasts
// that legitimately run into the future) is healthy while its newest row still
// reaches FORWARD of now. A coverage feed that is merely "recent" has already
// run out of the forward window the model needs - that was the aerosol failure
// mode this endpoint exists to name.
export interface FeedHealth {
  name: string
  label: string
  kind: string
  status: string // 'ok' | 'stale' | 'missing'
  rows: number
  latest: string | null
  // Minutes into the PAST; negative for a coverage feed reaching into the future.
  age_minutes: number | null
  // Minutes FORWARD of now the feed reaches; null for observation feeds.
  lead_minutes: number | null
  limit_minutes: number
  detail: string
}

export interface FeedsResponse {
  overall_status: string
  checked_at: string
  feeds: FeedHealth[]
}

// GET /diagnostics/{zone}/anomalies - days whose expected energy fell well below
// the month's norm, with the likely weather driver RANKED (not asserted). Both
// the energy and the norm are model estimates and there is no metered output, so
// `basis_note` states that this never claims the array itself underperformed.
export interface OutputAnomaly {
  day: string
  energy_kwh: number
  norm_kwh: number
  ratio: number
  shortfall_kwh: number
  likely_cause: string // 'cloud' | 'rain' | 'soiling' | 'aerosol' | 'unknown'
  cause_detail: string
}

export interface AnomaliesResponse {
  available: boolean
  zone: string
  window_days: number
  reason: string | null
  days_assessed: number
  norm_kwh_per_day: number | null
  anomalies: OutputAnomaly[]
  basis_note: string
}

// GET /forecast/{zone}/verification - how good the forecasts this system has
// actually ISSUED turned out to be (2026-07-25). Distinct from `error`/
// `candidate_errors` elsewhere in this file, which are TRAINING hold-out errors
// measured while fitting the model. `skill_score` is against a persistence
// baseline: > 0 = the model genuinely adds information over "nothing changes",
// 0 = no better, < 0 = worse than doing nothing. null whenever too few pairs
// carried a persistence reference to compute it honestly.
export interface VerificationMetrics {
  n: number
  mae_kw: number
  rmse_kw: number
  // Positive = the forecast runs HIGH (optimistic) on average.
  mbe_kw: number
  nrmse_pct: number | null
  persistence_rmse_kw: number | null
  skill_score: number | null
}

export interface VerificationLeadMetrics {
  lead_bucket: string
  metrics: VerificationMetrics
}

export interface VerificationResponse {
  available: boolean
  zone: string
  horizon: string
  window_days: number
  reason: string | null
  ac_capacity_kw: number | null
  // Daylight-only is the headline (night hours are trivially correct and would
  // dilute every metric toward zero); all_hours is shown alongside it so the
  // difference is visible rather than hidden.
  daylight: VerificationMetrics | null
  all_hours: VerificationMetrics | null
  by_lead: VerificationLeadMetrics[]
  lead_time_note: string
  // States that the "actual" side is the physics estimate, not a meter - this
  // site has no metered generation at all.
  reference_note: string
}

// GET /soiling/{zone} - the Soiling & Cleaning Advisor (2026-07-25). How dirty
// the array is now, how fast it's getting dirtier, when rain last washed it,
// what the dirt costs, and roughly when a wash is worth scheduling - all derived
// from this site's own CAMS PM10/dust, GFS wind/humidity (salt-spray index) and
// GFS rainfall history via a Kimber/Coello-style model. `available: false`
// (with `reason`) whenever that history can't yet support an assessment: the
// route never invents a soiling level.
export interface SoilingResponse {
  available: boolean
  zone: string
  reason: string | null
  days_assessed: number
  current_loss_pct: number
  average_loss_pct: number
  current_daily_rate_pct: number
  // null = no cleaning rain anywhere in the window (unknown, NOT zero days).
  days_since_cleaning_rain: number | null
  cleaning_events: number
  // null = already past the trigger (wash now) or nothing accumulating.
  days_until_trigger: number | null
  cleaning_trigger_pct: number
  max_loss_pct: number
  annual_energy_lost_kwh: number | null
  annual_cost_lost_thb: number | null
  // 'measured-airquality-rainfall' once the advisor has replaced the loss
  // model's soiling placeholder, else 'literature-default'.
  loss_model_soiling_source: string
  loss_model_soiling_pct: number | null
  series_days: string[]
  series_loss_pct: number[]
}

// GET /weather/uv-history - every real daily UV reading this deployment has
// accumulated (NASA POWER), oldest first (2026-07-19). One point per real
// day - UV has no hourly resolution to plot (see CurrentConditionsResponse's
// own comment on uv_observation_date), so this is deliberately a short,
// possibly-empty list rather than an interpolated/faked time series.
export interface UvHistoryPoint {
  observation_date: string
  uv_index: number
}

export interface UvHistoryResponse {
  points: UvHistoryPoint[]
}

// GET /weather/uv-hourly-history - every real hourly UV reading this deployment
// has accumulated (Open-Meteo hourly=uv_index), oldest first (2026-07-22,
// roadmap item 5). Unlike the daily list above, this IS a genuine intraday
// curve (UV rising and falling with sun elevation). `observed_at` is tz-aware
// UTC ISO; the frontend renders it in ICT (Thailand-first display). A
// possibly-empty list, same honest-empty contract as every other real-history
// endpoint.
export interface UvHourlyHistoryPoint {
  observed_at: string
  uv_index: number
}

export interface UvHourlyHistoryResponse {
  points: UvHourlyHistoryPoint[]
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
// `estimated` (2026-07-18): true for a cold-start-backfilled physics
// estimate rather than a genuinely live-polled reading - see
// api/routes_performance.py's GeneratedPowerPoint docstring for why this
// matters (an estimated row can be the literal same number as a
// physics-baseline "Forecast" for that same hour, which looked like two
// independent signals agreeing perfectly).
export interface GeneratedPowerPoint {
  timestamp: string
  ac_kw: number
  estimated: boolean
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

/** A BOI holiday this project actually holds, for the /financial quick-set
 * buttons. Comes from the server so editing the figure in Settings moves the
 * button with it. */
export interface BoiPreset {
  label: string
  years: number
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
  boi_presets: BoiPreset[]
  /** Optional: an older API deploy (or a test fixture written before this
   * existed) simply omits it, and the panel renders nothing. Required would
   * force every existing caller to restate a field they know nothing about. */
  uncertainty?: FinancialUncertainty | null
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
  // Decorative only (2026-07-18) - low/medium-precision approximation, see
  // features/src/nongfab_features/moon.py's docstring. Always populated;
  // visibility (show only after sunset) is decided on the frontend.
  moon: SolarPosition
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

export interface MoonPathPoint {
  time: string
  azimuth_deg: number
  elevation_deg: number
}

export interface MoonPathResponse {
  zone: string
  date: string
  points: MoonPathPoint[]
  /** Lit fraction of the Moon's disc for that date, 0 (new) .. 1 (full) -
   * drives the phase-correct crescent marker + "% lit" label in the 3D view. */
  illumination: number
  /** True while the lit fraction is growing (new -> full), False shrinking -
   * decides which limb (east/west) the crescent's lit side faces. */
  waxing: boolean
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

// --- Savings & carbon summary (Energy Report bottom table) ----------------
// Per (zone, horizon) money/CO2/carbon figures. Mirrors the API's
// SavingsMetricsOut - see api/src/nongfab_api/green_savings.py for how each is
// derived and from which real reference document.
export interface SavingsMetrics {
  energy_kwh: number
  bill_saving_thb: number
  ugt1_units_kwh: number
  ugt1_saving_thb: number
  ugt2_units_kwh: number
  ugt2_saving_thb: number
  carbon_credit_units: number
  carbon_credit_value_thb: number
  trees_equivalent: number
  scope2_co2_avoided_kg: number
}

export interface SavingsPeriods {
  day: SavingsMetrics
  month: SavingsMetrics
  year: SavingsMetrics
  lifetime: SavingsMetrics
}

export interface ZoneSavings {
  zone: string
  label: string
  simulated: boolean
  dc_capacity_kwp: number
  periods: SavingsPeriods
}

export interface SavingsSummaryResponse {
  zones: ZoneSavings[]
  assumptions: Record<string, number | string>
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
  recipient_client_id: string | null
  // Echoed back only to the sender's own socket so the client can reconcile
  // the optimistic bubble it showed on send with this confirmed server copy
  // (see useChatSocket.ts). Absent on the recipient's copy and on history.
  client_temp_id?: string | null
}

// Sent by the server when handling a frame failed (e.g. the DB write raised).
// Carries `client_temp_id` when the failure was for a specific outgoing
// message, so the client can flip exactly that optimistic bubble to "failed"
// instead of leaving the visitor staring at a silent, stuck "sending".
export interface ChatErrorEvent {
  type: 'error'
  message?: string
  client_temp_id?: string | null
}

// One entry per currently-connected visitor (deduped by client_id - a
// browser with several tabs open only appears once). Not a public roster of
// "everyone who's ever visited" - only who is online right now, which is
// exactly what lets a client pick a private chat partner (ws_chat.py).
export interface OnlineUser {
  client_id: string
  display_name: string
  avatar: string | null
  role: string
}

export interface ChatOnlineUsers {
  type: 'online_users'
  users: OnlineUser[]
}

export type ChatEvent = ChatMessage | ChatOnlineUsers | ChatErrorEvent

export interface FeedbackItem {
  id: number
  username: string
  role: string
  text: string
  created_at: string
  /** The sender's self-chosen display name; null for pre-2026-07-19 rows,
   * where the admin view falls back to `username`. */
  display_name: string | null
}

// --- Editable system values (GET/PUT /settings, 2026-07-25) ---------------
// Mirrors routes_settings.py's SettingOut. Deliberately self-describing: the
// settings page renders every group from this metadata (label/unit/bounds/
// step/origin) rather than hardcoding a field per value, so adding a value
// backend-side needs no frontend change at all.
export interface SettingItem {
  key: string
  group: string
  group_label: string
  label: string
  unit: string
  default: number
  value: number
  minimum: number
  maximum: number
  step: number
  /** Where the shipped default came from - confirmed / as-built / placeholder
   * / literature / tuning. Surfaced so nobody edits a measured figure thinking
   * it's a guess, or trusts a guess thinking it was measured. */
  origin: string
  origin_label: string
  note: string
  /** Applied by the browser (hand control); stored server-side so an admin can
   * publish a shared default, but no backend calculation reads it. */
  frontend_only: boolean
  /** True when an admin has published a value for this key - drives the
   * per-field "reset to default" affordance. */
  overridden: boolean
  updated_at: string | null
  updated_by: string | null
}

export interface SettingsResponse {
  settings: SettingItem[]
  groups: Record<string, string>
  origins: Record<string, string>
  /** Whether THIS caller may publish a shared default (admin), or is limited
   * to trying values locally in their own browser. */
  can_publish: boolean
}

export interface SettingsUpdateResponse {
  updated: Record<string, number>
  settings: SettingItem[]
}

// GET /grid/today - the national power system from EGAT's own public feed
// (2026-07-25), so this site can be shown in the context of the grid it sits
// on. Every timestamp is ICT as EGAT publishes it (see api/egat_grid.py).
export interface GridPoint {
  at: string
  mw: number
  ambient_c: number | null
}

export interface GridPeak {
  label: string
  mw: number
  at: string | null
  ambient_c: number | null
}

export interface GridTodayResponse {
  available: boolean
  reason: string | null
  day: string | null
  actual: GridPoint[]
  plan: GridPoint[]
  peaks: GridPeak[]
  latest_mw: number | null
  latest_at: string | null
  latest_ambient_c: number | null
  /** Running maximum SO FAR today, not the day's final peak. */
  peak_so_far_mw: number | null
  peak_so_far_at: string | null
  plan_deviation_mw: number | null
  solar_window_start: string | null
  solar_window_end: string | null
  /** The headline finding: Thailand's annual peak lands after sunset, so PV
   * here cannot shave it. null when either time was unknown upstream. */
  annual_peak_after_sunset: boolean | null
  site_dc_capacity_kwp: number | null
  site_share_of_system_pct: number | null
  source_note: string
  comparison_note: string
}

/** One ICT hour of the national grid's modelled carbon intensity
 * (2026-07-25). `average` is what the running mix emits; `marginal` is what
 * the plant on the margin emits - the factor an extra solar kWh actually
 * displaces. See api/grid_carbon.py for which parts are measured and which
 * are modelled. */
export interface GridCarbonHour {
  hour: number
  load_mw: number
  average_kg_per_kwh: number
  marginal_kg_per_kwh: number
  marginal_fuel_key: string
  marginal_fuel_label: string
  samples: number
  /** Clear-sky AC energy for the whole site in this hour - the weighting, not
   * a measurement (this site has no generation meter). */
  site_generation_kwh: number
}

export interface GridCarbonMixShare {
  key: string
  label: string
  share_pct: number
  ef_kg_per_kwh: number
}

export interface GridCarbonResponse {
  available: boolean
  reason: string | null
  day: string | null
  hours: GridCarbonHour[]
  mix: GridCarbonMixShare[]
  /** 'annual' = EPPO's real but yearly-average split (the shipped default);
   * 'published' = somebody entered their own, ideally a monthly table. */
  mix_origin: string
  mix_note: string
  published_ef_kg_per_kwh: number | null
  solar_weighted_marginal_kg_per_kwh: number | null
  solar_weighted_average_kg_per_kwh: number | null
  /** How far the factor this array earns sits above (or below) the flat
   * published one, in percent. */
  marginal_uplift_pct: number | null
  method_note: string
  calibration_note: string
  marginal_note: string
  profile_note: string
}

// GET /sources - provenance + staleness watch over the four Thai agencies this
// site quotes (2026-07-25). Deliberately NOT a rate scraper: every Thai tariff
// announcement is a scanned image, so the figures are transcribed by hand and
// this endpoint's job is to notice when the agency publishes something new.
export interface QuotedValue {
  label: string
  value: string
  /** Where in the code the number lives, so a stale value can be found. */
  code_location: string
  note: string
}

export interface OfficialSourceItem {
  key: string
  agency: string
  agency_full: string
  page_url: string
  purpose: string
  quoted: QuotedValue[]
  watch_documents: boolean
  /** 'ok' | 'changed' | 'unreachable' */
  status: string
  detail: string
  documents_now: string[]
  added: string[]
  removed: string[]
}

export interface SourcesResponse {
  overall_status: string
  checked_at: string | null
  baseline_captured: string
  sources: OfficialSourceItem[]
  method_note: string
}

// POST /financial's uncertainty block (2026-07-25, project B). Two separate
// views on purpose: P50/P90 is year-to-year sun variability, the Monte Carlo
// spread is how unsure the money assumptions are. See api/uncertainty.py.
export interface ExceedanceYield {
  label: string
  exceedance: number
  annual_energy_kwh: number
}

export interface MetricPercentiles {
  metric: string
  p10: number | null
  p50: number | null
  p90: number | null
  mean: number | null
  /** Trials where the metric was undefined (no IRR root / never paid back). */
  undefined_trials: number
}

export interface FinancialUncertainty {
  available: boolean
  reason: string | null
  yield_levels: ExceedanceYield[]
  samples: number
  metrics: MetricPercentiles[]
  probability_npv_negative_pct: number
  probability_no_payback_pct: number
  method_note: string
}
