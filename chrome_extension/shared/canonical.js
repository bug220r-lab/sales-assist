/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const MAX_DEPTH = 20;
  const MAX_COLLECTION = 4096;
  const MAX_STRING = 4096;
  const MAX_DOCUMENT_BYTES = 524288;
  const encoder = new TextEncoder();

  class CanonicalContractError extends Error {
    constructor(code) {
      super(code);
      this.name = "CanonicalContractError";
      this.code = code;
    }
  }

  function fail(code) {
    throw new CanonicalContractError(code);
  }

  function assertUnicodeScalars(value) {
    for (let index = 0; index < value.length; index += 1) {
      const unit = value.charCodeAt(index);
      if (unit >= 0xd800 && unit <= 0xdbff) {
        if (index + 1 >= value.length) fail("JSON_UNICODE_INVALID");
        const next = value.charCodeAt(index + 1);
        if (next < 0xdc00 || next > 0xdfff) fail("JSON_UNICODE_INVALID");
        index += 1;
      } else if (unit >= 0xdc00 && unit <= 0xdfff) {
        fail("JSON_UNICODE_INVALID");
      }
    }
  }

  function encode(value, depth, active) {
    if (depth > MAX_DEPTH) fail("JSON_DEPTH_INVALID");
    if (value === null) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") {
      if (!Number.isSafeInteger(value)) fail("JSON_NUMBER_INVALID");
      return String(value);
    }
    if (typeof value === "string") {
      if (value.length > MAX_STRING) fail("JSON_STRING_INVALID");
      assertUnicodeScalars(value);
      return JSON.stringify(value);
    }
    if (typeof value !== "object") fail("JSON_TYPE_INVALID");
    if (active.has(value)) fail("JSON_CYCLE_INVALID");
    active.add(value);
    try {
      if (Array.isArray(value)) {
        if (value.length > MAX_COLLECTION) fail("JSON_COLLECTION_INVALID");
        return `[${value.map((item) => encode(item, depth + 1, active)).join(",")}]`;
      }
      const prototype = Object.getPrototypeOf(value);
      if (prototype !== Object.prototype && prototype !== null) {
        fail("JSON_OBJECT_INVALID");
      }
      const keys = Object.keys(value).sort();
      if (keys.length > MAX_COLLECTION) fail("JSON_COLLECTION_INVALID");
      return `{${keys.map((key) => {
        assertUnicodeScalars(key);
        return `${JSON.stringify(key)}:${encode(value[key], depth + 1, active)}`;
      }).join(",")}}`;
    } finally {
      active.delete(value);
    }
  }

  function canonicalStringify(value) {
    const text = encode(value, 0, new Set());
    if (encoder.encode(text).length > MAX_DOCUMENT_BYTES) {
      fail("JSON_DOCUMENT_TOO_LARGE");
    }
    return text;
  }

  function exactMembers(value, members, code = "JSON_MEMBERS_INVALID") {
    if (value === null || Array.isArray(value) || typeof value !== "object") fail(code);
    const actual = Object.keys(value).sort();
    const expected = [...members].sort();
    if (actual.length !== expected.length) fail(code);
    for (let index = 0; index < actual.length; index += 1) {
      if (actual[index] !== expected[index]) fail(code);
    }
    return value;
  }

  function parseCanonicalJson(text, expectedMembers = null) {
    if (typeof text !== "string" || encoder.encode(text).length > MAX_DOCUMENT_BYTES) {
      fail("JSON_DOCUMENT_INVALID");
    }
    let value;
    try {
      value = JSON.parse(text);
    } catch (_error) {
      fail("JSON_MALFORMED");
    }
    if (expectedMembers !== null) exactMembers(value, expectedMembers);
    if (canonicalStringify(value) !== text) fail("JSON_NOT_CANONICAL");
    return value;
  }

  async function sha256Hex(text) {
    if (typeof text !== "string") fail("HASH_INPUT_INVALID");
    const bytes = encoder.encode(text);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (item) => item.toString(16).padStart(2, "0")).join("");
  }

  const root = globalThis.SSA || (globalThis.SSA = {});
  root.Canonical = Object.freeze({
    CanonicalContractError,
    MAX_DOCUMENT_BYTES,
    canonicalStringify,
    exactMembers,
    parseCanonicalJson,
    sha256Hex
  });
})();
