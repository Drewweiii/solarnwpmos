// Energy Report: annual yield simulation + losses breakdown, in the style of
// the reference PVsyst/Aurora-style report (Annual Generation, Specific Yield,
// Performance Ratio, Losses Breakdown, Solar Access).

import { fetchHistoricalHourly } from './weather.js';
import { solarPosition } from './solarPosition.js';
import { poaIrradiance, pvPowerOutput, nonTemperatureDerate } from './pvModel.js';

export async function computeEnergyReport(system, { simulationDays = 365, moduleAreaM2 = 2.6, panelWattage = 630 } = {}) {
  const hourly = await fetchHistoricalHourly(system.lat, system.lon, simulationDays);

  let actualEnergyKwh = 0;
  let noTempLossEnergyKwh = 0;
  let referenceYieldHours = 0;

  for (const sample of hourly) {
    const sun = solarPosition(sample.time, system.lat, system.lon);
    if (sun.zenithDeg >= 90) continue;

    const poa = poaIrradiance(sample, sun, system);
    if (poa <= 0) continue;

    referenceYieldHours += poa / 1000;
    actualEnergyKwh += pvPowerOutput({ poa, ambientTemp: sample.temp, capacityKw: system.capacityKw, losses: system.losses });
    noTempLossEnergyKwh += system.capacityKw * (poa / 1000) * nonTemperatureDerate(system.losses);
  }

  // Scale to a full year in case the archive returned a shorter window.
  const sampledDays = hourly.length / 24;
  const scale = 365 / sampledDays;
  const annualEnergyKwh = actualEnergyKwh * scale;

  const idealEnergyKwh = referenceYieldHours * system.capacityKw; // unscaled, matches actualEnergyKwh
  const performanceRatio = idealEnergyKwh > 0 ? actualEnergyKwh / idealEnergyKwh : 0;
  const temperatureLossFraction = noTempLossEnergyKwh > 0 ? 1 - actualEnergyKwh / noTempLossEnergyKwh : 0;

  const specificYieldKwhPerKwp = annualEnergyKwh / system.capacityKw;

  const panelCount = Math.round((system.capacityKw * 1000) / panelWattage);
  const roofAreaM2 = panelCount * moduleAreaM2;

  const losses = system.losses;
  const lossesBreakdownPct = {
    temperature: temperatureLossFraction * 100,
    shading: losses.shading * 100,
    soiling: losses.soiling * 100,
    inverter: losses.inverter * 100,
    mismatch: losses.mismatch * 100,
    dcWiring: losses.dcWiring * 100,
  };
  const totalSystemLossPct = (1 - performanceRatio) * 100;
  const solarAccessPct = (1 - losses.shading) * 100;

  return {
    systemSummary: {
      capacityKw: system.capacityKw,
      panelCount,
      panelWattage,
      roofAreaM2,
    },
    annualGenerationMwh: annualEnergyKwh / 1000,
    specificYieldKwhPerKwp,
    performanceRatioPct: performanceRatio * 100,
    lossesBreakdownPct,
    totalSystemLossPct,
    solarAccessPct,
  };
}
