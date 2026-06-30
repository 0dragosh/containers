const fs = require("fs");
const semver = require("semver");

function calver(now = new Date()) {
  return `${now.getUTCFullYear()}.${now.getUTCMonth() + 1}.${now.getUTCDate()}`;
}

function normalizeSemverCandidate(version) {
  return version.replace(/^v/, "").replace(/^(\d+)\.(\d+)-/, "$1.$2.0-");
}

function computeVersions(upstreamVersion, now = new Date()) {
  const normalizedVersion = normalizeSemverCandidate(upstreamVersion);
  const parsedSemver = semver.parse(normalizedVersion, { loose: true });
  const isValidSemver = parsedSemver !== null;
  const isStableSemver = isValidSemver && parsedSemver.prerelease.length === 0;

  return {
    isValidSemver: String(isValidSemver),
    isStableSemver: String(isStableSemver),
    semantic: isValidSemver ? parsedSemver.version : calver(now),
    raw: isValidSemver ? upstreamVersion.replace(/^v/, "") : upstreamVersion,
    upstream: upstreamVersion,
  };
}

function writeOutputs(outputs) {
  const outputNames = {
    isValidSemver: "is-valid-semver",
    isStableSemver: "is-stable-semver",
    semantic: "semantic",
    raw: "raw",
    upstream: "upstream",
  };
  const lines = Object.entries(outputs).map(
    ([key, value]) => `${outputNames[key]}=${value}`,
  );

  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `${lines.join("\n")}\n`);
    return;
  }

  console.log(JSON.stringify(outputs, null, 2));
}

if (require.main === module) {
  const upstreamVersion = process.argv[2];
  if (!upstreamVersion) {
    throw new Error("Usage: node versions.js <upstream-version>");
  }

  writeOutputs(computeVersions(upstreamVersion));
}

module.exports = {
  computeVersions,
};
