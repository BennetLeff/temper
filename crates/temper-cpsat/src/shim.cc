// Bytes in, bytes out. The ONLY C++ in the design: everything above this is
// Rust, everything below is the solver, which is already native.
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>

#include "ortools/sat/cp_model.pb.h"
#include "ortools/sat/cp_model_solver.h"
#include "ortools/sat/sat_parameters.pb.h"

extern "C" {

// 0 = ok. On success *out is malloc'd and must be released with
// temper_cpsat_free. Non-zero means the request did not parse.
int temper_cpsat_solve(const uint8_t *model_buf, size_t model_len,
                       const uint8_t *params_buf, size_t params_len,
                       uint8_t **out_buf, size_t *out_len) {
  operations_research::sat::CpModelProto model;
  if (!model.ParseFromArray(model_buf, static_cast<int>(model_len))) return 1;

  operations_research::sat::SatParameters params;
  if (params_len > 0 &&
      !params.ParseFromArray(params_buf, static_cast<int>(params_len)))
    return 2;

  const operations_research::sat::CpSolverResponse resp =
      operations_research::sat::SolveWithParameters(model, params);

  std::string encoded;
  if (!resp.SerializeToString(&encoded)) return 3;

  *out_len = encoded.size();
  *out_buf = static_cast<uint8_t *>(std::malloc(encoded.size()));
  if (*out_buf == nullptr) return 4;
  std::memcpy(*out_buf, encoded.data(), encoded.size());
  return 0;
}

void temper_cpsat_free(uint8_t *buf) { std::free(buf); }

}  // extern "C"
