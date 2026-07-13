// Compact NOAA solar-position algorithm (~0.5 deg accuracy).
// Reused by the PV transposition model here and by the sun-path 3D view planned for a later phase.

const toRad = (d) => (d * Math.PI) / 180;
const toDeg = (r) => (r * 180) / Math.PI;

function julianDay(date) {
  return date.getTime() / 86400000 + 2440587.5;
}

// Returns { elevationDeg, zenithDeg, azimuthDeg } of the sun at `date` (UTC-aware) for lat/lon in degrees.
export function solarPosition(date, latDeg, lonDeg) {
  const jd = julianDay(date);
  const jc = (jd - 2451545) / 36525;

  const geomMeanLongSun = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360;
  const geomMeanAnomSun = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);
  const eccentEarthOrbit = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);

  const sunEqOfCtr =
    Math.sin(toRad(geomMeanAnomSun)) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
    Math.sin(toRad(2 * geomMeanAnomSun)) * (0.019993 - 0.000101 * jc) +
    Math.sin(toRad(3 * geomMeanAnomSun)) * 0.000289;

  const sunTrueLong = geomMeanLongSun + sunEqOfCtr;
  const meanObliqEcliptic = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60;
  const obliqCorr = meanObliqEcliptic + 0.00256 * Math.cos(toRad(125.04 - 1934.136 * jc));
  const sunAppLong = sunTrueLong - 0.00569 - 0.00478 * Math.sin(toRad(125.04 - 1934.136 * jc));
  const sunDeclin = toDeg(Math.asin(Math.sin(toRad(obliqCorr)) * Math.sin(toRad(sunAppLong))));

  const y = Math.tan(toRad(obliqCorr / 2)) ** 2;
  const eqOfTime =
    4 *
    toDeg(
      y * Math.sin(2 * toRad(geomMeanLongSun)) -
        2 * eccentEarthOrbit * Math.sin(toRad(geomMeanAnomSun)) +
        4 * eccentEarthOrbit * y * Math.sin(toRad(geomMeanAnomSun)) * Math.cos(2 * toRad(geomMeanLongSun)) -
        0.5 * y * y * Math.sin(4 * toRad(geomMeanLongSun)) -
        1.25 * eccentEarthOrbit * eccentEarthOrbit * Math.sin(2 * toRad(geomMeanAnomSun))
    );

  const minutesUtc = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const trueSolarTime = (minutesUtc + eqOfTime + 4 * lonDeg) % 1440;
  const hourAngle = trueSolarTime / 4 < 0 ? trueSolarTime / 4 + 180 : trueSolarTime / 4 - 180;

  const zenith = toDeg(
    Math.acos(
      Math.sin(toRad(latDeg)) * Math.sin(toRad(sunDeclin)) +
        Math.cos(toRad(latDeg)) * Math.cos(toRad(sunDeclin)) * Math.cos(toRad(hourAngle))
    )
  );

  // atan2-based (Meeus) azimuth: numerically stable even with the sun near zenith,
  // which the classic acos-based NOAA formula is not (it degenerates in the tropics).
  const hourAngleRad = toRad(hourAngle);
  const latRad = toRad(latDeg);
  const declinRad = toRad(sunDeclin);
  const azFromSouth = Math.atan2(
    Math.sin(hourAngleRad),
    Math.cos(hourAngleRad) * Math.sin(latRad) - Math.tan(declinRad) * Math.cos(latRad)
  );
  const azimuthDeg = (toDeg(azFromSouth) + 180 + 360) % 360;

  return {
    elevationDeg: 90 - zenith,
    zenithDeg: zenith,
    azimuthDeg,
  };
}
