// Daily-step bias-correction Kalman filter, adapted from the paper's MOS+KF1a
// (run_model.m: run_kf_daily). The original state was a vector of fitted
// regression coefficients specific to the EE-building dataset; here the state
// is generalized to one additive bias term per hour-of-day, so the filter can
// run against any site's forecast/actual pair. Model:
//   z(t+1|h) = z(t|h) + w        (random walk bias per hour-of-day h)
//   y(t|h)   = z(t|h) + v        (observed residual = actual - raw forecast)

export class DailyBiasKalmanFilter {
  constructor({ numHours = 24, processNoise = 1e-4, measurementNoise = 0.02 } = {}) {
    this.numHours = numHours;
    this.Q = processNoise;
    this.R = measurementNoise;
    this.z = new Array(numHours).fill(0); // zhat(t|t): bias estimate per hour-of-day
    this.P = new Array(numHours).fill(1); // estimate variance per hour-of-day
  }

  // Bias-corrected forecast for a given hour-of-day, using the current (pre-update) estimate.
  correct(hourOfDay, rawForecastValue) {
    return rawForecastValue + this.z[hourOfDay];
  }

  // Called once a day's actual measurements are known: residual = actual - rawForecast, per hour-of-day.
  update(residualsByHour) {
    for (const [hourOfDay, residual] of residualsByHour) {
      // Time update (predict): random-walk state, variance grows by process noise.
      const pPred = this.P[hourOfDay] + this.Q;

      // Measurement update.
      const K = pPred / (pPred + this.R);
      this.z[hourOfDay] = this.z[hourOfDay] + K * (residual - this.z[hourOfDay]);
      this.P[hourOfDay] = (1 - K) * pPred;
    }
  }
}
