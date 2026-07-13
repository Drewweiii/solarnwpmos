// PV conversion model: NWP irradiance/temperature -> AC power.
// Generalizes the paper's site-specific linear regression (conversion.m:
// Phat = beta1*I + beta2*T + beta3*I*T) into a physical model driven by
// panel tilt/azimuth, cell-temperature derating and configurable system losses,
// so it works for any site rather than only the fitted 8kW/15kW EE-building plants.

import { solarPosition } from './solarPosition.js';

const toRad = (d) => (d * Math.PI) / 180;

// Isotropic-sky transposition of GHI/DNI/DHI onto the plane of array.
export function poaIrradiance({ ghi, dni, dhi }, { zenithDeg, azimuthDeg }, { tiltDeg, azimuthDeg: arrayAzimuthDeg, albedo = 0.2 }) {
  if (zenithDeg >= 90) return 0; // sun below horizon

  const zenithRad = toRad(zenithDeg);
  const tiltRad = toRad(tiltDeg);
  const aoiCos =
    Math.cos(zenithRad) * Math.cos(tiltRad) +
    Math.sin(zenithRad) * Math.sin(tiltRad) * Math.cos(toRad(azimuthDeg - arrayAzimuthDeg));

  const beam = Math.max(0, dni * aoiCos);
  const diffuse = dhi * (1 + Math.cos(tiltRad)) / 2;
  const ground = ghi * albedo * (1 - Math.cos(tiltRad)) / 2;

  return Math.max(0, beam + diffuse + ground);
}

export const DEFAULT_LOSSES = {
  temperatureCoeff: -0.004, // fraction per degC above 25 (typical c-Si)
  noct: 45, // deg C, nominal operating cell temperature
  shading: 0.05,
  soiling: 0.03,
  inverter: 0.03,
  mismatch: 0.02,
  dcWiring: 0.02,
};

export function nonTemperatureDerate(losses = DEFAULT_LOSSES) {
  return (
    (1 - losses.shading) *
    (1 - losses.soiling) *
    (1 - losses.inverter) *
    (1 - losses.mismatch) *
    (1 - losses.dcWiring)
  );
}

// Power output (kW) for one hourly sample.
export function pvPowerOutput({ poa, ambientTemp, capacityKw, losses = DEFAULT_LOSSES }) {
  if (poa <= 0) return 0;
  const cellTemp = ambientTemp + ((losses.noct - 20) / 800) * poa;
  const tempFactor = 1 + losses.temperatureCoeff * (cellTemp - 25);
  const derate = nonTemperatureDerate(losses);
  return Math.max(0, capacityKw * (poa / 1000) * tempFactor * derate);
}

// Convenience wrapper: forecast sample (from weather.js) -> predicted power (kW).
export function forecastToPower(sample, system) {
  const sun = solarPosition(sample.time, system.lat, system.lon);
  const poa = poaIrradiance(sample, sun, system);
  return pvPowerOutput({ poa, ambientTemp: sample.temp, capacityKw: system.capacityKw, losses: system.losses });
}
