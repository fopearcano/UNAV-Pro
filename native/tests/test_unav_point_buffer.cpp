// SPDX-License-Identifier: MIT
//
// UNAV Pro — UnavPointBuffer unit tests (v0.9 prototype).
//
// Pure-stdlib C++17 tests. They do **not** depend on Cinema 4D, the
// Maxon SDK, or any third-party test framework — they use plain
// `assert()` so the v0.9 build harness can run them as part of
// `ctest` against the same Python-produced fixture files the
// Python tests cover.
//
// Compile (when v0.9's CMake harness lands):
//
//   cmake -S native -B native/build -DUNAV_NATIVE_BUILD=ON
//   cmake --build native/build --target test_unav_point_buffer
//   ./native/build/test_unav_point_buffer
//
// The fixture path defaults to `cache/binary/test.unav` (which the
// Python tests can write via `unav_pro.tests.test_binary_export`).
// Tests that need a fixture skip cleanly if it isn't present so a
// fresh checkout runs the structural tests without first running
// the Python pipeline.

#include "../include/unav_point_buffer.h"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>

using namespace unav;

namespace {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

bool fileExists(const std::string& path) {
  std::ifstream fh(path);
  return fh.good();
}

// Write a tiny synthetic v1 binary file the loader can parse. Used
// by the structural tests so they pass even on a fresh checkout
// where the Python fixture has not been generated.
//
// The file holds two points and one source. CRC32 below is computed
// on the fly via the header's helper (re-implemented here so the
// test is self-contained and does not pull in zlib).
std::uint32_t crc32(const std::uint8_t* data, std::size_t len) {
  static std::uint32_t table[256];
  static bool ready = false;
  if (!ready) {
    for (std::uint32_t i = 0; i < 256; ++i) {
      std::uint32_t c = i;
      for (int j = 0; j < 8; ++j) {
        c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
      }
      table[i] = c;
    }
    ready = true;
  }
  std::uint32_t crc = 0xFFFFFFFFu;
  for (std::size_t i = 0; i < len; ++i) {
    crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  }
  return crc ^ 0xFFFFFFFFu;
}

void appendUInt16LE(std::string& out, std::uint16_t v) {
  out.push_back(static_cast<char>(v & 0xFFu));
  out.push_back(static_cast<char>((v >> 8) & 0xFFu));
}
void appendUInt32LE(std::string& out, std::uint32_t v) {
  for (int i = 0; i < 4; ++i) out.push_back(static_cast<char>((v >> (i * 8)) & 0xFFu));
}
void appendDoubleLE(std::string& out, double v) {
  std::uint64_t bits;
  std::memcpy(&bits, &v, sizeof(bits));
  for (int i = 0; i < 8; ++i) out.push_back(static_cast<char>((bits >> (i * 8)) & 0xFFu));
}
void appendUInt64LE(std::string& out, std::uint64_t v) {
  for (int i = 0; i < 8; ++i) out.push_back(static_cast<char>((v >> (i * 8)) & 0xFFu));
}
void appendFloatLE(std::string& out, float v) {
  std::uint32_t bits;
  std::memcpy(&bits, &v, sizeof(bits));
  appendUInt32LE(out, bits);
}

std::string buildFixture() {
  std::string body;  // payload bytes (header[4:] + sources + points)
  // Header (after magic): version=1, flags=0, scale=1.0,
  //                       point_count=2, source_count=1,
  //                       header_extra=0, sidecar_len=0
  appendUInt16LE(body, 1);
  appendUInt16LE(body, 0);
  appendDoubleLE(body, 1.0);
  appendUInt32LE(body, 2);
  appendUInt32LE(body, 1);
  appendUInt32LE(body, 0);
  appendUInt16LE(body, 0);
  // Source table (1 entry).
  appendUInt32LE(body, 1);
  appendUInt16LE(body, 7);
  body += "Gaia DR";  // 7-byte name fragment
  // Point block (2 records, 52 bytes each).
  for (int i = 0; i < 2; ++i) {
    UnavPoint p{};
    p.x = static_cast<double>(i);
    p.y = -static_cast<double>(i);
    p.z = static_cast<double>(i * i);
    p.size = 1.0f;
    p.r = 0.5f; p.g = 0.5f; p.b = 0.5f;
    p.uid_hash = static_cast<std::uint64_t>(i + 1);
    p.source_id = 1;
    body.append(reinterpret_cast<const char*>(&p), sizeof(p));
  }
  // Compute CRC over the body.
  const std::uint32_t crc = crc32(
      reinterpret_cast<const std::uint8_t*>(body.data()), body.size());
  std::string file;
  file += "UNAV";
  file += body;
  file += "UEND";
  appendUInt32LE(file, crc);
  return file;
}

void writeFixture(const std::string& path) {
  const std::string blob = buildFixture();
  std::ofstream fh(path, std::ios::binary | std::ios::trunc);
  fh.write(blob.data(), static_cast<std::streamsize>(blob.size()));
}

void corruptByte(const std::string& path, std::size_t offset) {
  std::fstream fh(path, std::ios::binary | std::ios::in | std::ios::out);
  fh.seekg(0, std::ios::end);
  const auto size = fh.tellg();
  if (offset >= static_cast<std::size_t>(size)) return;
  fh.seekg(offset);
  char c;
  fh.read(&c, 1);
  c ^= 0xFF;
  fh.seekp(offset);
  fh.write(&c, 1);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void test_struct_layout_is_52_bytes() {
  static_assert(sizeof(UnavPoint) == 52,
                "UnavPoint must be 52 bytes packed");
  std::cout << "PASS struct_layout_is_52_bytes\n";
}

void test_buffer_starts_empty() {
  UnavPointBuffer buf;
  assert(buf.size() == 0);
  assert(buf.data() == nullptr);
  assert(buf.maxPoints() == UnavPointBuffer::kDefaultMaxPoints);
  std::cout << "PASS buffer_starts_empty\n";
}

void test_load_synthetic_fixture() {
  const std::string path = "test_fixture.unav";
  writeFixture(path);
  UnavPointBuffer buf;
  std::string err;
  const std::size_t n = buf.loadFromFile(path, &err);
  assert(n == 2);
  assert(buf.size() == 2);
  assert(buf.sources().size() == 1);
  assert(buf.lastLoadStats().point_count == 2);
  assert(buf.lastLoadStats().file_size_bytes ==
         buildFixture().size());
  std::cout << "PASS load_synthetic_fixture\n";
  std::remove(path.c_str());
}

void test_load_rejects_bad_magic() {
  const std::string path = "test_bad_magic.unav";
  writeFixture(path);
  corruptByte(path, 0);
  UnavPointBuffer buf;
  std::string err;
  const std::size_t n = buf.loadFromFile(path, &err);
  assert(n == 0);
  assert(buf.size() == 0);
  assert(err.find("magic") != std::string::npos);
  std::cout << "PASS load_rejects_bad_magic\n";
  std::remove(path.c_str());
}

void test_load_rejects_bad_crc() {
  const std::string path = "test_bad_crc.unav";
  writeFixture(path);
  // Flip a byte in the point block (well past the magic / version).
  corruptByte(path, 60);
  UnavPointBuffer buf;
  std::string err;
  const std::size_t n = buf.loadFromFile(path, &err);
  assert(n == 0);
  assert(err.find("CRC") != std::string::npos);
  std::cout << "PASS load_rejects_bad_crc\n";
  std::remove(path.c_str());
}

void test_max_points_caps_load() {
  const std::string path = "test_cap.unav";
  writeFixture(path);
  UnavPointBuffer buf(1);  // cap to 1
  std::string err;
  const std::size_t n = buf.loadFromFile(path, &err);
  assert(n == 1);
  assert(buf.size() == 1);
  // The warning is recorded via the error-out string.
  assert(err.find("warning") != std::string::npos);
  std::cout << "PASS max_points_caps_load\n";
  std::remove(path.c_str());
}

void test_clear_resets_state() {
  const std::string path = "test_clear.unav";
  writeFixture(path);
  UnavPointBuffer buf;
  std::string err;
  buf.loadFromFile(path, &err);
  assert(buf.size() == 2);
  buf.clear();
  assert(buf.size() == 0);
  assert(buf.lastLoadStats().point_count == 0);
  std::cout << "PASS clear_resets_state\n";
  std::remove(path.c_str());
}

void test_query_nearest_to_position() {
  UnavPointBuffer buf;
  UnavPoint a{}; a.x = 0; a.y = 0; a.z = 0; a.uid_hash = 1; a.source_id = 1;
  UnavPoint b{}; b.x = 10; b.y = 0; b.z = 0; b.uid_hash = 2; b.source_id = 1;
  buf.addPoint(a);
  buf.addPoint(b);
  const std::size_t hit = buf.queryNearestPointToPosition(1.0, 0.0, 0.0, 5.0);
  assert(hit == 0);
  // Out of range → no hit.
  const std::size_t miss = buf.queryNearestPointToPosition(100.0, 0.0, 0.0, 1.0);
  assert(miss == UnavPointBuffer::kInvalidIndex);
  std::cout << "PASS query_nearest_to_position\n";
}

void test_query_nearest_to_ray_skips_behind_origin() {
  UnavPointBuffer buf;
  UnavPoint front{}; front.x = 5; front.y = 0; front.z = 0;
  UnavPoint behind{}; behind.x = -5; behind.y = 0; behind.z = 0;
  buf.addPoint(front);
  buf.addPoint(behind);
  // Ray at origin pointing +X. The behind-point is t < 0; skipped.
  const std::size_t hit = buf.queryNearestPointToRay(
      0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 100.0);
  assert(hit == 0);
  std::cout << "PASS query_nearest_to_ray_skips_behind_origin\n";
}

void test_python_fixture_if_available() {
  // Optional: load the Python-produced fixture under
  // `cache/binary/test.unav` when present. The Python test
  // `test_binary_export.py::test_round_trip_three_points`
  // produces a similar file under a tmp_path which is not
  // available outside pytest, so this test only runs when an
  // explicit fixture is dropped here.
  const std::string path = "cache/binary/test.unav";
  if (!fileExists(path)) {
    std::cout << "SKIP python_fixture_if_available (no fixture)\n";
    return;
  }
  UnavPointBuffer buf;
  std::string err;
  const std::size_t n = buf.loadFromFile(path, &err);
  assert(n > 0);
  std::cout << "PASS python_fixture_if_available (" << n << " points)\n";
}

}  // namespace

int main() {
  test_struct_layout_is_52_bytes();
  test_buffer_starts_empty();
  test_load_synthetic_fixture();
  test_load_rejects_bad_magic();
  test_load_rejects_bad_crc();
  test_max_points_caps_load();
  test_clear_resets_state();
  test_query_nearest_to_position();
  test_query_nearest_to_ray_skips_behind_origin();
  test_python_fixture_if_available();
  std::cout << "All v0.9 native tests passed.\n";
  return 0;
}
