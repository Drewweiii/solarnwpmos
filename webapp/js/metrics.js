// Performance indices, matching performance_index.m / performance_index_pv.m
// (RMSE, MAE, MAPE, MBE, nRMSE normalized to installed capacity).

export function performanceIndex(predicted, measured, installCapKw) {
  const n = predicted.length;
  let sqErr = 0;
  let absErr = 0;
  let sumErr = 0;
  let mapeSum = 0;
  let mapeCount = 0;

  for (let i = 0; i < n; i++) {
    const err = predicted[i] - measured[i];
    sqErr += err * err;
    absErr += Math.abs(err);
    sumErr += err;
    if (measured[i] !== 0) {
      mapeSum += Math.abs(err / measured[i]);
      mapeCount++;
    }
  }

  const rmse = Math.sqrt(sqErr / n);
  const mae = absErr / n;
  const mbe = sumErr / n;
  const mape = mapeCount ? (mapeSum / mapeCount) * 100 : NaN;
  const nrmseCap = installCapKw ? (rmse * 100) / installCapKw : NaN;

  return { rmse, mae, mape, mbe, nrmseCap, n };
}
